"""추천 카드 조회·수정·확정 서비스 (스펙 3.2 "같은 서비스 함수", 3.3 병합·확정, 3.4 낙관적 잠금).

모든 카드 항목 수정은 `save_items`를 거친다. PATCH 경로(`edit_by_doctor`)는 현재 카드를 읽어
`merge_doctor_edit`로 항목을 만든 뒤 `save_items`를 부르고, 포트 경로는 병합 없이 부른다.
확정(`confirm_recommendation`)은 고른 항목으로 처방을 만들고 같은 트랜잭션에서 카드를
`confirmed`로 바꾼다. 수정·확정의 0행 원인 판정은 `_raise_unchanged` 하나가 맡는다.
서비스는 연결을 열거나 닫지 않고 커밋·발행하지 않는다. 이벤트는 `WriteResult.events`로 돌려준다.
`ItemEdit`는 `item_rules`에 있고 기존 import를 위해 이 모듈에서도 그대로 쓸 수 있다.
"""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import datetime

from app.events.bus import Event
from app.services import prescriptions as rx_service
from app.services.clock import bump_after, format_app_timestamp
from app.services.item_rules import ItemEdit, check_thread_id, validate_items
from app.services.patients import require_patient
from app.services.ports import (
    ModifiedBy,
    PatientDataError,
    RecommendationCard,
    RecommendationItem,
    RecommendationNotEditableError,
    RecommendationNotFoundError,
    RecommendationStatus,
)
from app.services.unit_of_work import WriteResult
from app.storage import recommendations as rec_store
from app.storage.recommendations import PrescriptionRecord

UPDATED_EVENT = "recommendation.updated"


class StaleRecommendationError(PatientDataError):
    """`expected_updated_at`이 저장된 `updated_at`과 다르다(다른 수정이 먼저 커밋됐다)."""


class UnknownItemError(ValueError):
    """확정 요청의 `item_id`가 카드에 없다."""


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
    if existing is None:
        return edit.to_doctor_item()
    return replace(
        existing,
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
    conn: sqlite3.Connection,
    recommendation_id: str,
    expected_updated_at: str | None,
    action: str,
) -> None:
    """active 가드 UPDATE의 영향 행이 0일 때 카드를 다시 읽어 원인에 맞는 예외를 던진다.

    없음 → `RecommendationNotFoundError`, active 아님 → `RecommendationNotEditableError`,
    기대 시각 불일치 → `StaleRecommendationError`. `stale`은 기대 시각이 있을 때만이고, 기대 시각
    없이 active인데 0행이면 `RuntimeError`다. `action`(예: "수정", "확정")은 메시지에만 쓴다.
    """
    card = _require_card(conn, recommendation_id)
    if card.status is not RecommendationStatus.ACTIVE:
        raise RecommendationNotEditableError(
            f"active가 아닌 카드는 {action}할 수 없다: {recommendation_id} ({card.status.value})"
        )
    if expected_updated_at is None:
        # 같은 쓰기 트랜잭션에서 읽은 active 카드가 가드 없이 0행일 수는 없다.
        raise RuntimeError(f"active 카드 {action}이 0행이다(불변식 위반): {recommendation_id}")
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
        _raise_unchanged(conn, recommendation_id, expected_updated_at, "수정")
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


def confirm_recommendation(
    conn: sqlite3.Connection,
    recommendation_id: str,
    item_ids: tuple[str, ...],
    expected_updated_at: str | None,
    now: datetime,
) -> WriteResult[PrescriptionRecord]:
    """고른 항목으로 처방을 만들고 같은 트랜잭션에서 카드를 `confirmed`로 바꾼다.

    처방 항목은 `item_ids` 순서가 아니라 카드 순서대로 복사하고, 중복 ID는 한 번만 넣는다.
    고르지 않은 항목은 카드에 남는다. 오류 판정 순서: 빈 `item_ids` → `ValueError`, 카드 없음 →
    `RecommendationNotFoundError`, active 아님 → `RecommendationNotEditableError`, 기대 시각
    불일치 → `StaleRecommendationError`(이 셋은 `save_items`와 같은 규칙), 카드에 없는 ID →
    `UnknownItemError`. 없는 ID는 카드 상태를 바꾼 뒤 검사하지만 같은 쓰기 트랜잭션이라 예외로
    롤백되어 카드는 active·기존 `updated_at`으로 남는다. 카드 `updated_at`은 `now`와 기존
    `updated_at + 1µs` 중 큰 값이다. 이벤트는 `prescription.confirmed` 하나다.
    """
    if not item_ids:
        raise ValueError("확정할 item_id가 1개 이상이어야 한다")
    card = _require_card(conn, recommendation_id)
    updated_at = format_app_timestamp(bump_after(now, card.updated_at))
    changed = rec_store.set_card_confirmed(
        conn,
        recommendation_id,
        updated_at=updated_at,
        expected_updated_at=expected_updated_at,
    )
    if changed == 0:
        _raise_unchanged(conn, recommendation_id, expected_updated_at, "확정")
    selected = _select_items(card, item_ids)
    return rx_service.insert_prescription_record(
        conn, card.patient_id, recommendation_id, selected, now
    )


def _select_items(
    card: RecommendationCard, item_ids: tuple[str, ...]
) -> tuple[RecommendationItem, ...]:
    """`item_ids`에 든 항목을 카드 순서대로 고른다. 카드에 없는 ID → `UnknownItemError`."""
    wanted = set(item_ids)
    unknown = wanted - {item.item_id for item in card.items}
    if unknown:
        raise UnknownItemError(f"카드에 없는 item_id: {sorted(unknown)}")
    return tuple(item for item in card.items if item.item_id in wanted)
