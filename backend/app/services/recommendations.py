"""추천 카드 조회·수정 서비스 (스펙 3.2 "같은 서비스 함수", 3.3 병합 규칙, 3.4 낙관적 잠금).

모든 카드 수정은 `save_items`를 거친다. PATCH 경로(`edit_by_doctor`)는 현재 카드를 읽어
`merge_doctor_edit`로 항목을 만든 뒤 `save_items`를 부르고, 포트 경로는 병합 없이 부른다.
서비스는 연결을 열거나 닫지 않고 커밋·발행하지 않는다. 이벤트는 `WriteResult.events`로 돌려준다.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, replace
from datetime import date, datetime

from app.events.bus import Event
from app.services.clock import bump_after, format_app_timestamp
from app.services.item_rules import check_thread_id, validate_items
from app.services.patients import require_patient
from app.services.ports import (
    AddedBy,
    ModifiedBy,
    PatientDataError,
    PrescriptionType,
    RecommendationCard,
    RecommendationItem,
    RecommendationNotEditableError,
    RecommendationNotFoundError,
    RecommendationStatus,
)
from app.services.unit_of_work import WriteResult
from app.storage import recommendations as rec_store

UPDATED_EVENT = "recommendation.updated"


class StaleRecommendationError(PatientDataError):
    """`expected_updated_at`이 저장된 `updated_at`과 다르다(다른 수정이 먼저 커밋됐다)."""


@dataclass(frozen=True)
class ItemEdit:
    """의사가 보낸 항목 한 개 (`ItemInput`). `added_by`·`evidence`는 받지 않는다."""

    item_id: str
    type: PrescriptionType
    title: str
    detail: str
    duration_days: int | None
    review_date: date | None


def current_card(conn: sqlite3.Connection, patient_id: str) -> RecommendationCard | None:
    """그 환자의 현재 카드(`active`·`failed` 중 가장 늦은 것). 없는 환자면 `PatientNotFoundError`.

    없으면 `None`.
    """
    require_patient(conn, patient_id)
    return rec_store.select_current_card(conn, patient_id)


def merge_doctor_edit(
    current_items: tuple[RecommendationItem, ...], inputs: tuple[ItemEdit, ...]
) -> tuple[RecommendationItem, ...]:
    """의사 편집을 현재 항목에 병합한다. 요청 순서가 새 순서이고 빠진 항목은 삭제된다.

    기존 `item_id`는 제목·설명·기간·재평가일만 바꾸고 `type`·`added_by`·`evidence`를 유지한다.
    새 `item_id`는 `added_by = doctor`, `evidence = ()`로 만든다.
    """
    by_id = {item.item_id: item for item in current_items}
    return tuple(_merge_one(by_id.get(edit.item_id), edit) for edit in inputs)


def _merge_one(existing: RecommendationItem | None, edit: ItemEdit) -> RecommendationItem:
    base = existing or RecommendationItem(
        item_id=edit.item_id,
        type=edit.type,
        title=edit.title,
        detail=edit.detail,
        duration_days=edit.duration_days,
        review_date=edit.review_date,
        added_by=AddedBy.DOCTOR,
        evidence=(),
    )
    return replace(
        base,
        title=edit.title,
        detail=edit.detail,
        duration_days=edit.duration_days,
        review_date=edit.review_date,
    )


def _require_card(conn: sqlite3.Connection, recommendation_id: str) -> RecommendationCard:
    card = rec_store.select_card(conn, recommendation_id)
    if card is None:
        raise RecommendationNotFoundError(f"추천 카드가 없다: {recommendation_id}")
    return card


def _raise_unchanged(
    conn: sqlite3.Connection, recommendation_id: str, expected_updated_at: str | None
) -> None:
    """영향 행이 0일 때 카드를 다시 읽어 원인(없음·`not_editable`·`stale`)에 맞는 예외를 던진다.

    `stale`은 기대 시각이 있을 때만이다. 기대 시각 없이 active인데 0행이면 `RuntimeError`.
    """
    card = _require_card(conn, recommendation_id)
    if card.status is not RecommendationStatus.ACTIVE:
        raise RecommendationNotEditableError(
            f"active가 아닌 카드는 고칠 수 없다: {recommendation_id} ({card.status.value})"
        )
    if expected_updated_at is None:
        # 같은 쓰기 트랜잭션에서 읽은 active 카드가 가드 없이 0행일 수는 없다.
        raise RuntimeError(f"active 카드 수정이 0행이다(불변식 위반): {recommendation_id}")
    raise StaleRecommendationError(
        f"카드가 이미 바뀌었다: {recommendation_id} (기대 {expected_updated_at})"
    )


def save_items(
    conn: sqlite3.Connection,
    recommendation_id: str,
    items: tuple[RecommendationItem, ...],
    modified_by: ModifiedBy,
    thread_id: str | None,
    expected_updated_at: str | None,
    now: datetime,
) -> WriteResult[RecommendationCard]:
    """받은 `items`를 그대로 저장하고 `recommendation.updated` 이벤트와 함께 카드를 돌려준다.

    `thread_id` 규칙·항목 규칙 위반 → `ValueError`, 카드 없음 → `RecommendationNotFoundError`,
    `active`가 아님 → `RecommendationNotEditableError`, `expected_updated_at`(저장 문자열과 그대로
    비교, `None`이면 비교 안 함) 불일치 → `StaleRecommendationError`.
    `updated_at`은 `now`와 기존 `updated_at + 1µs` 중 큰 값이다(시계 역행 보정).
    """
    check_thread_id(modified_by, thread_id)
    validate_items(items)
    before = _require_card(conn, recommendation_id)
    updated_at = format_app_timestamp(bump_after(now, before.updated_at))
    changed = rec_store.update_card_items(
        conn,
        recommendation_id,
        items=items,
        modified_by=modified_by,
        thread_id=thread_id,
        updated_at=updated_at,
        expected_updated_at=expected_updated_at,
    )
    if changed == 0:
        _raise_unchanged(conn, recommendation_id, expected_updated_at)
    card = _require_card(conn, recommendation_id)
    event = Event(
        UPDATED_EVENT,
        {
            "recommendation_id": card.recommendation_id,
            "patient_id": card.patient_id,
            "modified_by": modified_by.value,
            "thread_id": thread_id,
            "at": updated_at,
        },
    )
    return WriteResult(card, (event,))


def edit_by_doctor(
    conn: sqlite3.Connection,
    recommendation_id: str,
    inputs: tuple[ItemEdit, ...],
    expected_updated_at: str,
    now: datetime,
) -> WriteResult[RecommendationCard]:
    """PATCH 경로. 현재 카드를 읽어 병합한 항목을 `save_items`로 저장한다(같은 트랜잭션)."""
    card = _require_card(conn, recommendation_id)
    items = merge_doctor_edit(card.items, inputs)
    return save_items(
        conn, recommendation_id, items, ModifiedBy.DOCTOR, None, expected_updated_at, now
    )
