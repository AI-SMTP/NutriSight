"""추천 카드 조회·수정 서비스 테스트 (스펙 3.2 "같은 서비스 함수", 3.3 병합 규칙, 3.4 낙관적 잠금).

빈 스키마 DB에 `rows.insert_*`로 환자·카드를 직접 넣고, 쓰기는 `run_in_db(mode="write")`로
감싸 실제 트랜잭션 경계에서 확인한다.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import ANY, Mock

import pytest

from app.events.bus import Event
from app.services import recommendations as service
from app.services import unit_of_work
from app.services.clock import format_app_timestamp
from app.services.ports import (
    AddedBy,
    EvidenceRef,
    ModifiedBy,
    PatientDataError,
    PatientNotFoundError,
    PrescriptionType,
    RecommendationCard,
    RecommendationItem,
    RecommendationNotEditableError,
    RecommendationNotFoundError,
)
from app.services.recommendations import (
    ItemEdit,
    StaleRecommendationError,
    current_card,
    edit_by_doctor,
    merge_doctor_edit,
    save_items,
)
from app.services.unit_of_work import WriteResult, run_in_db
from app.storage import recommendations as rec_store
from app.storage.codec import items_to_json
from app.storage.db import connect
from app.storage.recommendations import select_card
from tests.storage.items import AGENT_ITEM, DOCTOR_ITEM
from tests.storage.rows import PATIENT_ID, insert_patient, insert_recommendation, insert_row

CARD_ID = "R0001"
THREAD_ID = "T0001"
STORED_AT = "2026-11-23T12:00:00.000000"  # insert_recommendation 기본 시각
NOW = datetime(2026, 12, 5, 9, 0, 0, 123456)


@pytest.fixture
def card_db(db_path: Path) -> Path:
    """환자 NS07, 대화 하나, 항목 2개(`rx1` 에이전트, `rx2` 의사)인 `active` 카드 R0001."""
    with connect(db_path) as conn:
        insert_patient(conn)
        insert_row(
            conn,
            "chat_threads",
            {"thread_id": THREAD_ID, "patient_id": PATIENT_ID, "created_at": STORED_AT},
        )
        insert_recommendation(conn, items=items_to_json((AGENT_ITEM, DOCTOR_ITEM)))
    return db_path


def _read(db: Path, recommendation_id: str = CARD_ID) -> RecommendationCard:
    with connect(db) as conn:
        card = select_card(conn, recommendation_id)
    assert card is not None
    return card


@contextmanager
def assert_card_unchanged(db: Path, exc_type: type[BaseException]) -> Iterator[None]:
    """블록이 `exc_type`을 던지고, 그 뒤에도 카드가 블록 전과 같은지 확인한다."""
    before = _read(db)
    with pytest.raises(exc_type):
        yield
    assert _read(db) == before


def _set_status(db: Path, status: str) -> None:
    with connect(db) as conn:
        conn.execute(
            "UPDATE recommendations SET status = ? WHERE recommendation_id = ?", (status, CARD_ID)
        )


def _save(
    db: Path,
    items: tuple[RecommendationItem, ...],
    *,
    recommendation_id: str = CARD_ID,
    modified_by: ModifiedBy = ModifiedBy.AGENT,
    thread_id: str | None = None,
    expected_updated_at: str | None = None,
    now: datetime = NOW,
) -> WriteResult[RecommendationCard]:
    return run_in_db(
        db,
        lambda conn: save_items(
            conn, recommendation_id, items, modified_by, thread_id, expected_updated_at, now
        ),
        mode="write",
    )


def _edit(
    db: Path,
    inputs: tuple[ItemEdit, ...],
    *,
    expected_updated_at: str = STORED_AT,
    recommendation_id: str = CARD_ID,
    now: datetime = NOW,
) -> WriteResult[RecommendationCard]:
    return run_in_db(
        db,
        lambda conn: edit_by_doctor(conn, recommendation_id, inputs, expected_updated_at, now),
        mode="write",
    )


def _edit_of(item: RecommendationItem, **changes: object) -> ItemEdit:
    base = ItemEdit(
        item_id=item.item_id,
        type=item.type,
        title=item.title,
        detail=item.detail,
        duration_days=item.duration_days,
        review_date=item.review_date,
    )
    return replace(base, **changes)


NEW_AGENT_ITEM = RecommendationItem(
    item_id="ons1",
    type=PrescriptionType.ONS,
    title="경구영양보충 1일 1팩",
    detail="",
    duration_days=14,
    review_date=None,
    added_by=AddedBy.AGENT,
    evidence=(EvidenceRef(doc_id="espen_geriatrics", section="R25"),),
)


NEW_EDIT = ItemEdit("new1", PrescriptionType.OTHER, "기타", "", None, None)
NEW_EDIT_ITEM = RecommendationItem(
    "new1", PrescriptionType.OTHER, "기타", "", None, None, AddedBy.DOCTOR, ()
)


# ---- merge_doctor_edit ---------------------------------------------------------


def test_merge_existing_item_updates_editable_fields_and_keeps_type_added_by_evidence() -> None:
    edit = _edit_of(
        AGENT_ITEM,
        type=PrescriptionType.OTHER,  # 요청의 type이 달라도 무시한다
        title="식사 강화 14일",
        detail="간식 포함",
        duration_days=14,
        review_date=date(2026, 12, 19),
    )

    (merged,) = merge_doctor_edit((AGENT_ITEM, DOCTOR_ITEM), (edit,))

    assert merged == replace(
        AGENT_ITEM,
        title="식사 강화 14일",
        detail="간식 포함",
        duration_days=14,
        review_date=date(2026, 12, 19),
    )


def test_merge_new_item_is_added_by_doctor_without_evidence() -> None:
    edit = ItemEdit(
        item_id="new1",
        type=PrescriptionType.SNACK_ADDITION,
        title="오후 간식",
        detail="요거트",
        duration_days=None,
        review_date=None,
    )

    (merged,) = merge_doctor_edit((AGENT_ITEM,), (edit,))

    assert merged == RecommendationItem(
        item_id="new1",
        type=PrescriptionType.SNACK_ADDITION,
        title="오후 간식",
        detail="요거트",
        duration_days=None,
        review_date=None,
        added_by=AddedBy.DOCTOR,
        evidence=(),
    )


def test_merge_drops_missing_items_and_follows_request_order() -> None:
    merged = merge_doctor_edit(
        (AGENT_ITEM, DOCTOR_ITEM, NEW_AGENT_ITEM), (NEW_EDIT, _edit_of(DOCTOR_ITEM))
    )

    assert [item.item_id for item in merged] == ["new1", DOCTOR_ITEM.item_id]
    assert merged[1] == DOCTOR_ITEM


def test_merge_empty_inputs_returns_empty_tuple() -> None:
    assert merge_doctor_edit((AGENT_ITEM,), ()) == ()


# ---- save_items: 성공 ------------------------------------------------------------


def test_save_items_stores_given_items_as_is(card_db: Path) -> None:
    items = (NEW_AGENT_ITEM, DOCTOR_ITEM)

    result = _save(card_db, items)

    stored = _read(card_db)
    assert stored.items == items  # added_by = agent·근거 있는 항목도 그대로
    assert stored.last_modified_by is ModifiedBy.AGENT
    assert stored.thread_id is None
    assert result.value == stored


def test_save_items_by_chat_sets_thread_id(card_db: Path) -> None:
    _save(card_db, (AGENT_ITEM,), modified_by=ModifiedBy.CHAT, thread_id=THREAD_ID)

    stored = _read(card_db)
    assert stored.last_modified_by is ModifiedBy.CHAT
    assert stored.thread_id == THREAD_ID


def test_save_items_keeps_other_fields(card_db: Path) -> None:
    before = _read(card_db)

    after = _save(card_db, (NEW_AGENT_ITEM,)).value

    for name in ("recommendation_id", "patient_id", "alert_id", "cautions", "created_at", "status"):
        assert getattr(after, name) == getattr(before, name), name


def test_save_items_sets_updated_at_to_clock_value(card_db: Path) -> None:
    result = _save(card_db, (AGENT_ITEM,))

    assert result.value.updated_at == NOW
    assert _read(card_db).updated_at == NOW


def test_save_items_updated_at_increases_when_clock_goes_back(card_db: Path) -> None:
    first = _save(card_db, (AGENT_ITEM,), now=NOW).value

    result = _save(card_db, (DOCTOR_ITEM,), now=NOW - timedelta(seconds=10))
    second = result.value

    assert second.updated_at > first.updated_at
    assert second.updated_at == first.updated_at + timedelta(microseconds=1)
    assert result.events[0].data["at"] == format_app_timestamp(second.updated_at)


def test_save_items_returns_updated_event(card_db: Path) -> None:
    result = _save(card_db, (AGENT_ITEM,), modified_by=ModifiedBy.CHAT, thread_id=THREAD_ID)

    assert result.events == (
        Event(
            "recommendation.updated",
            {
                "recommendation_id": CARD_ID,
                "patient_id": PATIENT_ID,
                "modified_by": "chat",
                "thread_id": THREAD_ID,
                "at": "2026-12-05T09:00:00.123456",
            },
        ),
    )


def test_save_items_with_matching_expected_updated_at_succeeds(card_db: Path) -> None:
    _save(card_db, (NEW_AGENT_ITEM,), expected_updated_at=STORED_AT)

    assert _read(card_db).items == (NEW_AGENT_ITEM,)


def test_save_items_without_expected_updated_at_skips_comparison(card_db: Path) -> None:
    _save(card_db, (AGENT_ITEM,))  # updated_at이 바뀐 뒤에도

    _save(card_db, (NEW_AGENT_ITEM,), expected_updated_at=None, now=NOW + timedelta(seconds=1))

    assert _read(card_db).items == (NEW_AGENT_ITEM,)


# ---- save_items: 실패 ------------------------------------------------------------


@pytest.mark.parametrize(
    ("modified_by", "thread_id"),
    [
        (ModifiedBy.CHAT, None),
        (ModifiedBy.CHAT, ""),
        (ModifiedBy.AGENT, THREAD_ID),
        (ModifiedBy.DOCTOR, THREAD_ID),
    ],
    ids=["chat_without_thread", "chat_empty_thread", "agent_with_thread", "doctor_with_thread"],
)
def test_save_items_thread_id_rule_violation_raises_value_error(
    card_db: Path, modified_by: ModifiedBy, thread_id: str | None
) -> None:
    with assert_card_unchanged(card_db, ValueError):
        _save(card_db, (NEW_AGENT_ITEM,), modified_by=modified_by, thread_id=thread_id)


@pytest.mark.parametrize(
    "items",
    [
        (AGENT_ITEM, replace(DOCTOR_ITEM, item_id=AGENT_ITEM.item_id)),
        (replace(AGENT_ITEM, title=""),),
        (replace(AGENT_ITEM, item_id="bad id"),),
        (replace(AGENT_ITEM, evidence=(EvidenceRef(doc_id="", section="R1"),)),),
    ],
    ids=["duplicate_item_id", "empty_title", "bad_item_id", "empty_doc_id"],
)
def test_save_items_item_rule_violation_raises_value_error(
    card_db: Path, items: tuple[RecommendationItem, ...]
) -> None:

    with assert_card_unchanged(card_db, ValueError):
        _save(card_db, items)


def test_save_items_unknown_card_raises_not_found(card_db: Path) -> None:
    with pytest.raises(RecommendationNotFoundError):
        _save(card_db, (AGENT_ITEM,), recommendation_id="R9999")


@pytest.mark.parametrize("status", ["confirmed", "superseded", "failed"])
@pytest.mark.parametrize("expected", [None, STORED_AT, "2026-01-01T00:00:00.000000"])
def test_save_items_non_active_card_raises_not_editable(
    card_db: Path, status: str, expected: str | None
) -> None:
    _set_status(card_db, status)

    with assert_card_unchanged(card_db, RecommendationNotEditableError):
        _save(card_db, (NEW_AGENT_ITEM,), expected_updated_at=expected)


def test_save_items_mismatched_expected_updated_at_raises_stale(card_db: Path) -> None:

    with assert_card_unchanged(card_db, StaleRecommendationError):
        _save(card_db, (NEW_AGENT_ITEM,), expected_updated_at="2026-11-23T12:00:00.000001")


def test_save_items_zero_rows_without_expected_on_active_card_raises_runtime_error(
    card_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 기대 시각 없이 active 카드인데 0행이면 불변식 위반이다(stale로 보고하지 않는다).
    monkeypatch.setattr(rec_store, "update_card_items", lambda *args, **kwargs: 0)

    with pytest.raises(RuntimeError):
        _save(card_db, (NEW_AGENT_ITEM,), expected_updated_at=None)


def test_stale_error_is_patient_data_error() -> None:
    assert issubclass(StaleRecommendationError, PatientDataError)


# ---- edit_by_doctor --------------------------------------------------------------


def test_edit_by_doctor_merges_and_saves_through_save_items(
    card_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spy = Mock(wraps=service.save_items)
    monkeypatch.setattr(service, "save_items", spy)
    inputs = (_edit_of(AGENT_ITEM, title="식사 강화 14일", type=PrescriptionType.ONS), NEW_EDIT)

    result = _edit(card_db, inputs)

    expected_items = (replace(AGENT_ITEM, title="식사 강화 14일"), NEW_EDIT_ITEM)
    spy.assert_called_once_with(
        ANY, CARD_ID, expected_items, ModifiedBy.DOCTOR, None, STORED_AT, NOW
    )
    assert result.value.items == expected_items
    assert result.value.last_modified_by is ModifiedBy.DOCTOR
    assert _read(card_db).items == expected_items
    assert [event.name for event in result.events] == ["recommendation.updated"]


def test_edit_by_doctor_after_chat_clears_thread_id(card_db: Path) -> None:
    chat = _save(card_db, (AGENT_ITEM,), modified_by=ModifiedBy.CHAT, thread_id=THREAD_ID).value

    _edit(
        card_db,
        (_edit_of(AGENT_ITEM),),
        expected_updated_at=format_app_timestamp(chat.updated_at),
        now=NOW + timedelta(seconds=1),
    )

    stored = _read(card_db)
    assert stored.last_modified_by is ModifiedBy.DOCTOR
    assert stored.thread_id is None


def test_edit_by_doctor_unknown_card_raises_not_found(card_db: Path) -> None:
    with pytest.raises(RecommendationNotFoundError):
        _edit(card_db, (_edit_of(AGENT_ITEM),), recommendation_id="R9999")


def test_edit_by_doctor_confirmed_card_raises_not_editable(card_db: Path) -> None:
    _set_status(card_db, "confirmed")

    with assert_card_unchanged(card_db, RecommendationNotEditableError):
        _edit(card_db, (_edit_of(AGENT_ITEM, title="수정"),))


def test_edit_by_doctor_stale_leaves_card(card_db: Path) -> None:

    with assert_card_unchanged(card_db, StaleRecommendationError):
        _edit(card_db, (_edit_of(AGENT_ITEM, title="x"),), expected_updated_at="2020-01-01T00:00")


def test_edit_by_doctor_after_clock_goes_back_rejects_old_value_and_accepts_new(
    card_db: Path,
) -> None:
    first = _edit(card_db, (_edit_of(AGENT_ITEM, title="첫 수정"),)).value
    first_at = format_app_timestamp(first.updated_at)

    second = _edit(
        card_db,
        (_edit_of(AGENT_ITEM, title="둘째 수정"),),
        expected_updated_at=first_at,
        now=NOW - timedelta(seconds=10),
    ).value
    assert second.updated_at > first.updated_at

    with pytest.raises(StaleRecommendationError):
        _edit(card_db, (_edit_of(AGENT_ITEM, title="옛 값"),), expected_updated_at=first_at)
    _edit(
        card_db,
        (_edit_of(AGENT_ITEM, title="셋째 수정"),),
        expected_updated_at=format_app_timestamp(second.updated_at),
    )
    assert _read(card_db).items[0].title == "셋째 수정"


def test_edit_by_doctor_runs_single_begin(card_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    statements: list[str] = []
    real_connect = unit_of_work.connect

    @contextmanager
    def tracing_connect(path: Path) -> Iterator[sqlite3.Connection]:
        with real_connect(path) as conn:
            conn.set_trace_callback(statements.append)
            yield conn

    monkeypatch.setattr(unit_of_work, "connect", tracing_connect)

    _edit(card_db, (_edit_of(AGENT_ITEM, title="수정"),))

    begins = [s.strip() for s in statements if s.strip().upper().startswith("BEGIN")]
    assert begins == ["BEGIN IMMEDIATE"]
    assert _read(card_db).items[0].title == "수정"


def test_edit_by_doctor_store_failure_leaves_card(
    card_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:

    def boom(*args: object, **kwargs: object) -> int:
        raise sqlite3.OperationalError("저장 실패")

    monkeypatch.setattr(rec_store, "update_card_items", boom)

    with assert_card_unchanged(card_db, sqlite3.OperationalError):
        _edit(card_db, (_edit_of(AGENT_ITEM, title="수정"),))


# ---- current_card ----------------------------------------------------------------


def test_current_card_unknown_patient_raises(card_db: Path) -> None:
    with connect(card_db) as conn, pytest.raises(PatientNotFoundError):
        current_card(conn, "NS99")


def test_current_card_without_cards_returns_none(db_path: Path) -> None:
    with connect(db_path) as conn:
        insert_patient(conn)
        assert current_card(conn, PATIENT_ID) is None


def test_current_card_returns_latest_open_card(card_db: Path) -> None:
    with connect(card_db) as conn:
        insert_recommendation(
            conn,
            recommendation_id="R0002",
            status="failed",
            created_at="2026-11-24T12:00:00.000000",
            updated_at="2026-11-24T12:00:00.000000",
        )
        insert_recommendation(
            conn,
            recommendation_id="R0003",
            status="confirmed",
            created_at="2026-11-25T12:00:00.000000",
            updated_at="2026-11-25T12:00:00.000000",
        )
        card = current_card(conn, PATIENT_ID)

    assert card is not None
    assert card.recommendation_id == "R0002"
