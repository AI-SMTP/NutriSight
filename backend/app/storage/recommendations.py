"""추천 카드·처방 읽기·쓰기 SQL (`docs/data-model.md` 6절).

SQL만 둔다. 항목 JSON 인코딩은 `app.storage.codec`, 항목 규칙 검사·커밋·이벤트 발행·
시각 생성은 서비스가 맡는다.
시각 열은 저장 문자열(`YYYY-MM-DDTHH:MM:SS.ffffff`)로 받아 그대로 쓰고, 카드로 읽을 때만
`parse_app_timestamp`로 `datetime`으로 바꾼다. 수정 함수는 영향 행 수를 돌려주며, 0일 때
원인(없음·상태·시각 불일치)을 가리는 일은 호출자 몫이다.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Literal

from app.services.clock import parse_app_timestamp
from app.services.ports import (
    ModifiedBy,
    RecommendationCard,
    RecommendationItem,
    RecommendationStatus,
)
from app.storage.codec import (
    items_from_json,
    items_to_json,
    strings_from_json,
    strings_to_json,
)

_CARD_COLUMNS = (
    "recommendation_id, patient_id, alert_id, items, cautions, last_modified_by, thread_id, "
    "created_at, updated_at, status"
)
_PRESCRIPTION_COLUMNS = (
    "prescription_id, patient_id, recommendation_id, items, confirmed_at, status"
)


@dataclass(frozen=True)
class PrescriptionRecord:
    """처방 한 건 (`prescriptions`). 시각은 저장 문자열 그대로다."""

    prescription_id: str
    patient_id: str
    recommendation_id: str | None  # 추천 없이 작성했으면 None
    items: tuple[RecommendationItem, ...]
    confirmed_at: str
    status: Literal["confirmed"]


# 카드 ----------------------------------------------------------------------


def _card_from_row(row: sqlite3.Row) -> RecommendationCard:
    return RecommendationCard(
        recommendation_id=row["recommendation_id"],
        patient_id=row["patient_id"],
        alert_id=row["alert_id"],
        items=items_from_json(row["items"]),
        cautions=strings_from_json(row["cautions"]),
        last_modified_by=ModifiedBy(row["last_modified_by"]),
        thread_id=row["thread_id"],
        created_at=parse_app_timestamp(row["created_at"]),
        updated_at=parse_app_timestamp(row["updated_at"]),
        status=RecommendationStatus(row["status"]),
    )


def select_card(conn: sqlite3.Connection, recommendation_id: str) -> RecommendationCard | None:
    """ID로 카드를 읽는다. 상태와 관계없다. 없으면 `None`."""
    row = conn.execute(
        f"SELECT {_CARD_COLUMNS} FROM recommendations WHERE recommendation_id = ?",
        (recommendation_id,),
    ).fetchone()
    return _card_from_row(row) if row is not None else None


def select_current_card(conn: sqlite3.Connection, patient_id: str) -> RecommendationCard | None:
    """그 환자의 `active`·`failed` 카드 중 `created_at`이 가장 늦은 것(같으면 ID가 큰 것)."""
    row = conn.execute(
        f"SELECT {_CARD_COLUMNS} FROM recommendations "
        "WHERE patient_id = ? AND status IN ('active', 'failed') "
        "ORDER BY created_at DESC, recommendation_id DESC LIMIT 1",
        (patient_id,),
    ).fetchone()
    return _card_from_row(row) if row is not None else None


def insert_card(
    conn: sqlite3.Connection,
    *,
    recommendation_id: str,
    patient_id: str,
    alert_id: str | None,
    items: tuple[RecommendationItem, ...],
    cautions: tuple[str, ...],
    last_modified_by: ModifiedBy,
    thread_id: str | None,
    created_at: str,
    updated_at: str,
    status: RecommendationStatus,
) -> None:
    """카드 한 장을 넣는다."""
    conn.execute(
        f"INSERT INTO recommendations ({_CARD_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            recommendation_id,
            patient_id,
            alert_id,
            items_to_json(items),
            strings_to_json(cautions),
            str(last_modified_by),
            thread_id,
            created_at,
            updated_at,
            str(status),
        ),
    )


def _active_guard(expected_updated_at: str | None) -> tuple[str, tuple[str, ...]]:
    """`active` 조건과, 기대 시각이 있으면 `updated_at` 비교 조건을 만든다."""
    if expected_updated_at is None:
        return "status = 'active'", ()
    return "status = 'active' AND updated_at = ?", (expected_updated_at,)


def update_card_items(
    conn: sqlite3.Connection,
    recommendation_id: str,
    *,
    items: tuple[RecommendationItem, ...],
    modified_by: ModifiedBy,
    thread_id: str | None,
    updated_at: str,
    expected_updated_at: str | None = None,
) -> int:
    """`active` 카드의 항목·수정 주체·대화 ID·수정 시각을 바꾸고 영향 행 수를 돌려준다.

    `expected_updated_at`이 있으면 저장된 `updated_at`과 같을 때만 바꾼다(낙관적 잠금).
    """
    guard, guard_args = _active_guard(expected_updated_at)
    cursor = conn.execute(
        "UPDATE recommendations SET items = ?, last_modified_by = ?, thread_id = ?, "
        f"updated_at = ? WHERE recommendation_id = ? AND {guard}",
        (items_to_json(items), str(modified_by), thread_id, updated_at, recommendation_id)
        + guard_args,
    )
    return cursor.rowcount


def set_card_confirmed(
    conn: sqlite3.Connection,
    recommendation_id: str,
    *,
    updated_at: str,
    expected_updated_at: str | None = None,
) -> int:
    """`active` 카드를 `confirmed`로 바꾸고 `updated_at`을 갱신한다. 영향 행 수를 돌려준다."""
    guard, guard_args = _active_guard(expected_updated_at)
    cursor = conn.execute(
        "UPDATE recommendations SET status = 'confirmed', updated_at = ? "
        f"WHERE recommendation_id = ? AND {guard}",
        (updated_at, recommendation_id) + guard_args,
    )
    return cursor.rowcount


def supersede_open_cards(conn: sqlite3.Connection, patient_id: str) -> int:
    """그 환자의 `active`·`failed` 카드를 `superseded`로 바꾼다. `confirmed`는 그대로다."""
    cursor = conn.execute(
        "UPDATE recommendations SET status = 'superseded' "
        "WHERE patient_id = ? AND status IN ('active', 'failed')",
        (patient_id,),
    )
    return cursor.rowcount


def max_card_created_at(conn: sqlite3.Connection, patient_id: str) -> str | None:
    """그 환자의 모든 카드(상태 무관) 중 최대 `created_at`. 카드가 없으면 `None`."""
    row = conn.execute(
        "SELECT MAX(created_at) AS value FROM recommendations WHERE patient_id = ?",
        (patient_id,),
    ).fetchone()
    return row["value"]


# 처방 ----------------------------------------------------------------------


def _prescription_from_row(row: sqlite3.Row) -> PrescriptionRecord:
    return PrescriptionRecord(
        prescription_id=row["prescription_id"],
        patient_id=row["patient_id"],
        recommendation_id=row["recommendation_id"],
        items=items_from_json(row["items"]),
        confirmed_at=row["confirmed_at"],
        status=row["status"],
    )


def insert_prescription(
    conn: sqlite3.Connection,
    *,
    prescription_id: str,
    patient_id: str,
    recommendation_id: str | None,
    items: tuple[RecommendationItem, ...],
    confirmed_at: str,
) -> None:
    """처방 한 건을 `confirmed` 상태로 넣는다."""
    conn.execute(
        f"INSERT INTO prescriptions ({_PRESCRIPTION_COLUMNS}) VALUES (?, ?, ?, ?, ?, 'confirmed')",
        (prescription_id, patient_id, recommendation_id, items_to_json(items), confirmed_at),
    )


def list_prescriptions(conn: sqlite3.Connection, patient_id: str) -> tuple[PrescriptionRecord, ...]:
    """그 환자의 처방을 `confirmed_at` 내림차순(같으면 ID 내림차순)으로."""
    rows = conn.execute(
        f"SELECT {_PRESCRIPTION_COLUMNS} FROM prescriptions WHERE patient_id = ? "
        "ORDER BY confirmed_at DESC, prescription_id DESC",
        (patient_id,),
    ).fetchall()
    return tuple(_prescription_from_row(row) for row in rows)


def max_prescription_confirmed_at(conn: sqlite3.Connection, patient_id: str) -> str | None:
    """그 환자 처방의 최대 `confirmed_at`. 처방이 없으면 `None`."""
    row = conn.execute(
        "SELECT MAX(confirmed_at) AS value FROM prescriptions WHERE patient_id = ?",
        (patient_id,),
    ).fetchone()
    return row["value"]
