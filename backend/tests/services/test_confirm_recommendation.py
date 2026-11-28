"""추천 확정 서비스 테스트 (스펙 3.3 "확정", 3.4 낙관적 잠금, 이벤트 표).

`card_db`(conftest)의 카드 R0001 항목을 3개(`rx1`·`rx2`·`ons1`)로 바꿔 쓰고, 확정은
`run_in_db(mode="write")`로 감싸 실제 트랜잭션 경계에서 확인한다.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from app.events.bus import Event
from app.services.ports import (
    AddedBy,
    EvidenceRef,
    PrescriptionType,
    RecommendationItem,
    RecommendationNotEditableError,
    RecommendationNotFoundError,
    RecommendationStatus,
)
from app.services.recommendations import (
    StaleRecommendationError,
    UnknownItemError,
    confirm_recommendation,
)
from app.services.unit_of_work import WriteResult, run_in_db
from app.storage import recommendations as rec_store
from app.storage.codec import items_to_json
from app.storage.db import connect
from app.storage.recommendations import PrescriptionRecord
from tests.services.cards import (
    CARD_ID,
    NOW,
    NOW_TEXT,
    STORED_AT,
    assert_card_unchanged,
    insert_rx,
    read_card,
    set_status,
)
from tests.storage.items import AGENT_ITEM, DOCTOR_ITEM
from tests.storage.rows import PATIENT_ID

ONS_ITEM = RecommendationItem(
    item_id="ons1",
    type=PrescriptionType.ONS,
    title="경구영양보충 1일 1팩",
    detail="",
    duration_days=14,
    review_date=None,
    added_by=AddedBy.AGENT,
    evidence=(EvidenceRef(doc_id="espen_geriatrics", section="R25"),),
)
CARD_ITEMS = (AGENT_ITEM, DOCTOR_ITEM, ONS_ITEM)


@pytest.fixture
def confirm_db(card_db: Path) -> Path:
    """카드 R0001의 항목이 `rx1`(에이전트)·`rx2`(의사)·`ons1`(에이전트) 순서인 DB."""
    with connect(card_db) as conn:
        conn.execute(
            "UPDATE recommendations SET items = ? WHERE recommendation_id = ?",
            (items_to_json(CARD_ITEMS), CARD_ID),
        )
    return card_db


def _confirm(
    db: Path,
    item_ids: tuple[str, ...],
    *,
    recommendation_id: str = CARD_ID,
    expected_updated_at: str | None = STORED_AT,
    now: datetime = NOW,
) -> WriteResult[PrescriptionRecord]:
    return run_in_db(
        db,
        lambda conn: confirm_recommendation(
            conn, recommendation_id, item_ids, expected_updated_at, now
        ),
        mode="write",
    )


def _prescriptions(db: Path) -> tuple[PrescriptionRecord, ...]:
    with connect(db) as conn:
        return rec_store.list_prescriptions(conn, PATIENT_ID)


# ---- 성공 ------------------------------------------------------------------------


def test_confirm_copies_selected_items_in_card_order(confirm_db: Path) -> None:
    result = _confirm(confirm_db, ("ons1", "rx1"))  # 요청 순서는 카드 순서와 반대

    record = result.value
    assert record.items == (AGENT_ITEM, ONS_ITEM)  # added_by·evidence까지 그대로 복사
    assert record.recommendation_id == CARD_ID
    assert record.patient_id == PATIENT_ID
    assert record.confirmed_at == NOW_TEXT
    assert record.status == "confirmed"
    assert _prescriptions(confirm_db) == (record,)


def test_confirm_marks_card_confirmed_and_keeps_unselected_items(confirm_db: Path) -> None:
    before = read_card(confirm_db)

    _confirm(confirm_db, ("rx2",))

    after = read_card(confirm_db)
    assert after.status is RecommendationStatus.CONFIRMED
    assert after.updated_at == NOW
    assert after.items == CARD_ITEMS  # 고르지 않은 항목도 카드에 남는다
    for name in ("patient_id", "alert_id", "cautions", "last_modified_by", "created_at"):
        assert getattr(after, name) == getattr(before, name), name


def test_confirm_card_updated_at_increases_when_clock_goes_back(confirm_db: Path) -> None:
    _confirm(confirm_db, ("rx1",), now=datetime(2026, 11, 1))

    assert read_card(confirm_db).updated_at == datetime(2026, 11, 23, 12, 0, 0, 1)


def test_confirm_confirmed_at_bumps_after_latest_prescription(confirm_db: Path) -> None:
    insert_rx(confirm_db, "rx_later", "2026-12-05T10:00:00.000000")

    result = _confirm(confirm_db, ("rx1",), now=NOW)

    assert result.value.confirmed_at == "2026-12-05T10:00:00.000001"
    assert _prescriptions(confirm_db)[0] == result.value


def test_confirm_returns_prescription_confirmed_event(confirm_db: Path) -> None:
    result = _confirm(confirm_db, ("rx1",))

    assert result.events == (
        Event(
            "prescription.confirmed",
            {
                "prescription_id": result.value.prescription_id,
                "patient_id": PATIENT_ID,
                "recommendation_id": CARD_ID,
                "at": NOW_TEXT,
            },
        ),
    )


def test_confirm_without_expected_updated_at_skips_comparison(confirm_db: Path) -> None:
    _confirm(confirm_db, ("rx1",), expected_updated_at=None)

    assert read_card(confirm_db).status is RecommendationStatus.CONFIRMED


def test_confirm_twice_raises_not_editable(confirm_db: Path) -> None:
    _confirm(confirm_db, ("rx1",))
    confirmed_at = read_card(confirm_db).updated_at.isoformat(timespec="microseconds")

    with assert_card_unchanged(confirm_db, RecommendationNotEditableError):
        _confirm(confirm_db, ("rx1",), expected_updated_at=confirmed_at)
    assert len(_prescriptions(confirm_db)) == 1


# ---- 실패 ------------------------------------------------------------------------


@pytest.mark.parametrize("item_ids", [("nope",), ("rx1", "nope")], ids=["only", "mixed"])
def test_confirm_unknown_item_id_raises_and_leaves_card(
    confirm_db: Path, item_ids: tuple[str, ...]
) -> None:
    with assert_card_unchanged(confirm_db, UnknownItemError):
        _confirm(confirm_db, item_ids)
    assert _prescriptions(confirm_db) == ()


def test_confirm_empty_item_ids_raises_value_error(confirm_db: Path) -> None:
    before = read_card(confirm_db)

    with pytest.raises(ValueError, match="1개 이상") as exc_info:
        _confirm(confirm_db, ())

    assert type(exc_info.value) is ValueError  # UnknownItemError가 아니다
    assert read_card(confirm_db) == before
    assert _prescriptions(confirm_db) == ()


@pytest.mark.parametrize(
    ("status", "expected", "error"),
    [
        ("confirmed", STORED_AT, RecommendationNotEditableError),
        ("active", "2026-11-23T12:00:00.000001", StaleRecommendationError),
    ],
    ids=["not_editable", "stale"],
)
def test_confirm_card_state_error_wins_over_unknown_item(
    confirm_db: Path, status: str, expected: str, error: type[Exception]
) -> None:
    # 판정 순서: 빈 목록 → 없음 → active 아님 → stale → 없는 ID.
    set_status(confirm_db, status)

    with assert_card_unchanged(confirm_db, error):
        _confirm(confirm_db, ("nope",), expected_updated_at=expected)
    assert _prescriptions(confirm_db) == ()


def test_confirm_duplicate_item_ids_copy_item_once(confirm_db: Path) -> None:
    result = _confirm(confirm_db, ("rx1", "rx1"))

    assert result.value.items == (AGENT_ITEM,)


def test_confirm_unknown_card_raises_not_found(confirm_db: Path) -> None:
    with pytest.raises(RecommendationNotFoundError):
        _confirm(confirm_db, ("rx1",), recommendation_id="R9999")


@pytest.mark.parametrize("status", ["confirmed", "superseded", "failed"])
@pytest.mark.parametrize("expected", [None, STORED_AT, "2026-01-01T00:00:00.000000"])
def test_confirm_non_active_card_raises_not_editable(
    confirm_db: Path, status: str, expected: str | None
) -> None:
    set_status(confirm_db, status)

    with assert_card_unchanged(confirm_db, RecommendationNotEditableError):
        _confirm(confirm_db, ("rx1",), expected_updated_at=expected)
    assert _prescriptions(confirm_db) == ()


def test_confirm_mismatched_expected_updated_at_raises_stale(confirm_db: Path) -> None:
    with assert_card_unchanged(confirm_db, StaleRecommendationError):
        _confirm(confirm_db, ("rx1",), expected_updated_at="2026-11-23T12:00:00.000001")
    assert _prescriptions(confirm_db) == ()


def test_confirm_zero_rows_without_expected_on_active_card_raises_runtime_error(
    confirm_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(rec_store, "set_card_confirmed", lambda *args, **kwargs: 0)

    with pytest.raises(RuntimeError):
        _confirm(confirm_db, ("rx1",), expected_updated_at=None)


def test_confirm_prescription_insert_failure_keeps_card_active(
    confirm_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*args: object, **kwargs: object) -> None:
        raise sqlite3.OperationalError("처방 저장 실패")

    monkeypatch.setattr(rec_store, "insert_prescription", boom)

    with assert_card_unchanged(confirm_db, sqlite3.OperationalError):
        _confirm(confirm_db, ("rx1",))
    assert read_card(confirm_db).status is RecommendationStatus.ACTIVE
    monkeypatch.undo()
    assert _prescriptions(confirm_db) == ()
