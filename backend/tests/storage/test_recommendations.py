"""추천 카드·처방 저장소 SQL 테스트 (`docs/data-model.md` 6절).

빈 스키마 DB에 `rows.insert_*`로 환자·판정·카드를 직접 넣는다. 규칙 검사·커밋·발행은
서비스 몫이라 여기서는 SQL 결과만 확인한다. 항목 JSON 코덱 테스트는 `test_codec.py`에 있다.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import pytest

from app.services.ports import ModifiedBy, RecommendationCard, RecommendationStatus
from app.storage.codec import items_to_json
from app.storage.db import connect
from app.storage.recommendations import (
    PrescriptionRecord,
    insert_card,
    insert_prescription,
    list_prescriptions,
    max_card_created_at,
    max_prescription_confirmed_at,
    select_card,
    select_current_card,
    set_card_confirmed,
    supersede_open_cards,
    update_card_items,
)
from tests.storage.items import AGENT_ITEM, DOCTOR_ITEM
from tests.storage.rows import PATIENT_ID, insert_alert, insert_patient, insert_recommendation

OTHER_PATIENT = "NS03"
T1 = "2026-11-23T12:00:00.000000"
T2 = "2026-11-23T12:00:00.000001"


@pytest.fixture
def conn(db_path: Path) -> Iterator[sqlite3.Connection]:
    """환자 NS07·NS03과 판정 A0001이 있는 연결."""
    with connect(db_path) as c:
        insert_patient(c)
        insert_patient(c, patient_id=OTHER_PATIENT, display_name="NS03")
        insert_alert(c)
        yield c


def _row(conn: sqlite3.Connection, recommendation_id: str) -> sqlite3.Row:
    """저장된 카드 행을 그대로 읽는다(시각·JSON 문자열 확인용)."""
    return conn.execute(
        "SELECT * FROM recommendations WHERE recommendation_id = ?", (recommendation_id,)
    ).fetchone()


def _status(conn: sqlite3.Connection, recommendation_id: str) -> str:
    return _row(conn, recommendation_id)["status"]


def _insert(conn: sqlite3.Connection, recommendation_id: str, **overrides: object) -> None:
    insert_recommendation(conn, recommendation_id=recommendation_id, **overrides)


# 카드 삽입·조회 ----------------------------------------------------------------


def test_insert_card_then_select_card_returns_typed_card(conn):
    insert_card(
        conn,
        recommendation_id="rec_a",
        patient_id=PATIENT_ID,
        alert_id="A0001",
        items=(AGENT_ITEM,),
        cautions=("체중 기록이 없습니다.",),
        last_modified_by=ModifiedBy.AGENT,
        thread_id=None,
        created_at=T1,
        updated_at=T2,
        status=RecommendationStatus.ACTIVE,
    )

    card = select_card(conn, "rec_a")

    assert card == RecommendationCard(
        recommendation_id="rec_a",
        patient_id=PATIENT_ID,
        alert_id="A0001",
        items=(AGENT_ITEM,),
        cautions=("체중 기록이 없습니다.",),
        last_modified_by=ModifiedBy.AGENT,
        thread_id=None,
        created_at=datetime(2026, 11, 23, 12, 0, 0),
        updated_at=datetime(2026, 11, 23, 12, 0, 0, 1),
        status=RecommendationStatus.ACTIVE,
    )
    assert type(card.last_modified_by) is ModifiedBy
    assert type(card.status) is RecommendationStatus
    row = _row(conn, "rec_a")
    assert (row["created_at"], row["updated_at"]) == (T1, T2)
    assert row["cautions"] == '["체중 기록이 없습니다."]'


def test_select_card_missing_returns_none(conn):
    assert select_card(conn, "rec_missing") is None


def test_select_current_card_none_without_candidates(conn):
    _insert(conn, "R1", status="superseded", created_at="2026-11-25T00:00:00.000000")
    _insert(conn, "R2", status="confirmed", created_at="2026-11-26T00:00:00.000000")
    _insert(conn, "R3", patient_id=OTHER_PATIENT, created_at="2026-11-27T00:00:00.000000")

    assert select_current_card(conn, PATIENT_ID) is None


def test_select_current_card_picks_latest_active_or_failed(conn):
    _insert(conn, "R1", status="active", created_at="2026-11-24T00:00:00.000000")
    _insert(conn, "R2", status="failed", created_at="2026-11-25T00:00:00.000000")
    _insert(conn, "R3", status="confirmed", created_at="2026-11-26T00:00:00.000000")
    _insert(conn, "R4", status="superseded", created_at="2026-11-27T00:00:00.000000")
    _insert(conn, "R5", patient_id=OTHER_PATIENT, created_at="2026-11-28T00:00:00.000000")

    card = select_current_card(conn, PATIENT_ID)

    assert card is not None
    assert card.recommendation_id == "R2"
    assert card.status is RecommendationStatus.FAILED


def test_select_current_card_tie_breaks_on_larger_id(conn):
    # 삽입 순서와 ID 순서를 엇갈려 rowid 순 결과가 우연히 맞지 않게 한다.
    _insert(conn, "rec_b", created_at="2026-11-25T00:00:00.000000")
    _insert(conn, "rec_c", created_at="2026-11-25T00:00:00.000000")
    _insert(conn, "rec_a", created_at="2026-11-25T00:00:00.000000")

    card = select_current_card(conn, PATIENT_ID)

    assert card is not None
    assert card.recommendation_id == "rec_c"


# 카드 수정 -------------------------------------------------------------------


def _update(conn, recommendation_id="R1", **overrides):
    args = {
        "items": (AGENT_ITEM, DOCTOR_ITEM),
        "modified_by": ModifiedBy.DOCTOR,
        "thread_id": None,
        "updated_at": T2,
    }
    return update_card_items(conn, recommendation_id, **{**args, **overrides})


def test_update_card_items_changes_only_edit_columns(conn):
    _insert(conn, "R1", updated_at=T1, created_at=T1, alert_id="A0001", cautions='["주의"]')

    assert _update(conn) == 1

    card = select_card(conn, "R1")
    assert card.items == (AGENT_ITEM, DOCTOR_ITEM)
    assert card.last_modified_by is ModifiedBy.DOCTOR
    assert card.thread_id is None
    assert card.updated_at == datetime(2026, 11, 23, 12, 0, 0, 1)
    assert card.created_at == datetime(2026, 11, 23, 12, 0, 0)
    assert card.alert_id == "A0001"
    assert card.cautions == ("주의",)
    assert card.status is RecommendationStatus.ACTIVE


def test_update_card_items_writes_thread_id(conn):
    conn.execute(
        "INSERT INTO chat_threads (thread_id, patient_id, created_at) VALUES (?, ?, ?)",
        ("th1", PATIENT_ID, T1),
    )
    _insert(conn, "R1")

    assert _update(conn, modified_by=ModifiedBy.CHAT, thread_id="th1") == 1

    card = select_card(conn, "R1")
    assert card.thread_id == "th1"
    assert card.last_modified_by is ModifiedBy.CHAT


NON_ACTIVE = ["superseded", "confirmed", "failed"]


@pytest.mark.parametrize("expected", [None, T1])
@pytest.mark.parametrize("status", NON_ACTIVE)
def test_update_card_items_skips_non_active(conn, status, expected):
    # 저장값과 같은 기대 시각을 줘도 상태 조건이 따로 막아야 한다.
    _insert(conn, "R1", status=status, items="[]", updated_at=T1)

    assert _update(conn, expected_updated_at=expected) == 0
    row = _row(conn, "R1")
    assert (row["items"], row["updated_at"], row["status"]) == ("[]", T1, status)


def test_update_card_items_missing_card_returns_zero(conn):
    assert _update(conn, "rec_missing") == 0


@pytest.mark.parametrize("expected", [None, T1])
def test_update_card_items_with_matching_or_no_expected(conn, expected):
    _insert(conn, "R1", updated_at=T1)

    assert _update(conn, expected_updated_at=expected) == 1
    assert select_card(conn, "R1").items == (AGENT_ITEM, DOCTOR_ITEM)


def test_update_card_items_with_stale_expected_updated_at(conn):
    _insert(conn, "R1", updated_at=T1, items="[]")

    assert _update(conn, expected_updated_at=T2) == 0
    row = _row(conn, "R1")
    assert (row["items"], row["updated_at"]) == ("[]", T1)


def test_update_card_items_touches_only_target_card(conn):
    _insert(conn, "R1", items="[]")
    _insert(conn, "R2", items="[]")

    _update(conn, "R1")

    assert select_card(conn, "R2").items == ()


# 대체·확정 ------------------------------------------------------------------


def test_supersede_open_cards_only_active_and_failed_of_patient(conn):
    _insert(conn, "R1", status="active")
    _insert(conn, "R2", status="failed")
    _insert(conn, "R3", status="confirmed")
    _insert(conn, "R4", status="superseded")
    _insert(conn, "R5", patient_id=OTHER_PATIENT, status="active")

    assert supersede_open_cards(conn, PATIENT_ID) == 2

    assert _status(conn, "R1") == "superseded"
    assert _status(conn, "R2") == "superseded"
    assert _status(conn, "R3") == "confirmed"
    assert _status(conn, "R4") == "superseded"
    assert _status(conn, "R5") == "active"


def test_supersede_open_cards_keeps_updated_at(conn):
    _insert(conn, "R1", updated_at=T1)

    supersede_open_cards(conn, PATIENT_ID)

    assert _row(conn, "R1")["updated_at"] == T1


@pytest.mark.parametrize("expected", [None, T1])
def test_set_card_confirmed_marks_active_card(conn, expected):
    _insert(conn, "R1", updated_at=T1, last_modified_by="agent")

    assert set_card_confirmed(conn, "R1", updated_at=T2, expected_updated_at=expected) == 1

    card = select_card(conn, "R1")
    assert card.status is RecommendationStatus.CONFIRMED
    assert card.updated_at == datetime(2026, 11, 23, 12, 0, 0, 1)
    assert card.last_modified_by is ModifiedBy.AGENT


def test_set_card_confirmed_rejects_stale_and_missing(conn):
    _insert(conn, "R1", updated_at=T1)

    assert set_card_confirmed(conn, "R1", updated_at=T2, expected_updated_at=T2) == 0
    assert set_card_confirmed(conn, "rec_missing", updated_at=T2) == 0
    row = _row(conn, "R1")
    assert (row["updated_at"], row["status"]) == (T1, "active")


@pytest.mark.parametrize("expected", [None, T1])
@pytest.mark.parametrize("status", NON_ACTIVE)
def test_set_card_confirmed_skips_non_active(conn, status, expected):
    _insert(conn, "R1", status=status, updated_at=T1)

    assert set_card_confirmed(conn, "R1", updated_at=T2, expected_updated_at=expected) == 0
    row = _row(conn, "R1")
    assert (row["updated_at"], row["status"]) == (T1, status)


# 처방 ----------------------------------------------------------------------


def test_insert_prescription_and_list_newest_first(conn):
    _insert(conn, "R1")
    insert_prescription(
        conn,
        prescription_id="rx_a",
        patient_id=PATIENT_ID,
        recommendation_id="R1",
        items=(AGENT_ITEM,),
        confirmed_at=T1,
    )
    insert_prescription(
        conn,
        prescription_id="rx_b",
        patient_id=PATIENT_ID,
        recommendation_id=None,
        items=(DOCTOR_ITEM,),
        confirmed_at=T2,
    )
    insert_prescription(
        conn,
        prescription_id="rx_c",
        patient_id=OTHER_PATIENT,
        recommendation_id=None,
        items=(DOCTOR_ITEM,),
        confirmed_at="2026-11-30T00:00:00.000000",
    )

    records = list_prescriptions(conn, PATIENT_ID)

    assert records == (
        PrescriptionRecord(
            prescription_id="rx_b",
            patient_id=PATIENT_ID,
            recommendation_id=None,
            items=(DOCTOR_ITEM,),
            confirmed_at=T2,
            status="confirmed",
        ),
        PrescriptionRecord(
            prescription_id="rx_a",
            patient_id=PATIENT_ID,
            recommendation_id="R1",
            items=(AGENT_ITEM,),
            confirmed_at=T1,
            status="confirmed",
        ),
    )
    raw = conn.execute("SELECT items FROM prescriptions WHERE prescription_id = 'rx_a'").fetchone()
    assert raw["items"] == items_to_json((AGENT_ITEM,))


def test_list_prescriptions_empty(conn):
    assert list_prescriptions(conn, PATIENT_ID) == ()


# 최대 시각 -------------------------------------------------------------------


def test_max_card_created_at(conn):
    assert max_card_created_at(conn, PATIENT_ID) is None

    _insert(conn, "R1", status="superseded", created_at="2026-11-25T00:00:00.000000")
    _insert(conn, "R2", status="confirmed", created_at="2026-11-26T00:00:00.000000")
    _insert(conn, "R3", created_at="2026-11-24T00:00:00.000000")
    _insert(conn, "R4", patient_id=OTHER_PATIENT, created_at="2026-11-30T00:00:00.000000")

    # 상태와 관계없이 그 환자의 모든 카드 중 최대값이다.
    assert max_card_created_at(conn, PATIENT_ID) == "2026-11-26T00:00:00.000000"


def test_max_prescription_confirmed_at(conn):
    assert max_prescription_confirmed_at(conn, PATIENT_ID) is None

    for rx_id, patient_id, at in [
        ("rx_a", PATIENT_ID, T2),
        ("rx_b", PATIENT_ID, T1),
        ("rx_c", OTHER_PATIENT, "2026-11-30T00:00:00.000000"),
    ]:
        insert_prescription(
            conn,
            prescription_id=rx_id,
            patient_id=patient_id,
            recommendation_id=None,
            items=(),
            confirmed_at=at,
        )

    assert max_prescription_confirmed_at(conn, PATIENT_ID) == T2


@pytest.mark.parametrize("column", ["created_at", "updated_at"])
def test_select_card_rejects_non_app_timestamp(conn, column):
    # 형식 규칙 자체는 `test_clock.py`의 `parse_app_timestamp` 테스트가 다룬다.
    _insert(conn, "R1", **{column: "2026-11-23T12:00:00"})

    with pytest.raises(ValueError, match="앱 시각 형식"):
        select_card(conn, "R1")
