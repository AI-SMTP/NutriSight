"""처방 작성·이력 서비스 테스트 (스펙 3.3 "처방 직접 작성", 3.2 단조 증가 보정, 이벤트 표).

빈 스키마 DB에 환자·카드를 직접 넣고, 쓰기는 `run_in_db(mode="write")`로 감싸 실제 트랜잭션
경계에서 확인한다.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from app.events.bus import Event
from app.services.item_rules import ItemEdit
from app.services.ports import (
    AddedBy,
    PatientNotFoundError,
    PrescriptionType,
    RecommendationItem,
)
from app.services.prescriptions import create_prescription, list_prescriptions
from app.services.unit_of_work import WriteResult, run_in_db
from app.storage import recommendations as rec_store
from app.storage.db import connect
from app.storage.recommendations import PrescriptionRecord
from tests.services.cards import NOW, NOW_TEXT, insert_rx, read_card
from tests.storage.rows import PATIENT_ID, insert_patient

OTHER_PATIENT = "NS08"
RX_ID = re.compile(r"^rx_[0-9a-f]{32}$")

ONS_EDIT = ItemEdit("ons1", PrescriptionType.ONS, "경구영양보충 1일 1팩", "", 14, None)
REVIEW_EDIT = ItemEdit(
    "rv1", PrescriptionType.MONITORING_REVIEW, "재평가", "체중 확인", None, date(2026, 12, 12)
)
# 위 두 입력을 의사 항목으로 저장한 기대값(`added_by = doctor`, 근거 없음).
ONS_ITEM = RecommendationItem(
    item_id="ons1",
    type=PrescriptionType.ONS,
    title="경구영양보충 1일 1팩",
    detail="",
    duration_days=14,
    review_date=None,
    added_by=AddedBy.DOCTOR,
    evidence=(),
)
REVIEW_ITEM = RecommendationItem(
    item_id="rv1",
    type=PrescriptionType.MONITORING_REVIEW,
    title="재평가",
    detail="체중 확인",
    duration_days=None,
    review_date=date(2026, 12, 12),
    added_by=AddedBy.DOCTOR,
    evidence=(),
)


@pytest.fixture
def patient_db(db_path: Path) -> Path:
    """환자 NS07·NS08만 있는 DB."""
    with connect(db_path) as conn:
        insert_patient(conn)
        insert_patient(conn, patient_id=OTHER_PATIENT, display_name=OTHER_PATIENT)
    return db_path


def _create(
    db: Path,
    inputs: tuple[ItemEdit, ...],
    *,
    patient_id: str = PATIENT_ID,
    now: datetime = NOW,
) -> WriteResult[PrescriptionRecord]:
    return run_in_db(
        db, lambda conn: create_prescription(conn, patient_id, inputs, now), mode="write"
    )


def _list(db: Path, patient_id: str = PATIENT_ID) -> tuple[PrescriptionRecord, ...]:
    return run_in_db(db, lambda conn: list_prescriptions(conn, patient_id), mode="read")


# ---- create_prescription: 성공 -------------------------------------------------


def test_create_prescription_stores_doctor_items_without_recommendation(patient_db: Path) -> None:
    result = _create(patient_db, (ONS_EDIT, REVIEW_EDIT))

    record = result.value
    assert record == PrescriptionRecord(
        prescription_id=record.prescription_id,
        patient_id=PATIENT_ID,
        recommendation_id=None,
        items=(ONS_ITEM, REVIEW_ITEM),  # 요청 순서, 의사 항목·근거 없음
        confirmed_at=NOW_TEXT,
        status="confirmed",
    )
    assert _list(patient_db) == (record,)


def test_create_prescription_id_is_rx_plus_uuid_hex(patient_db: Path) -> None:
    first = _create(patient_db, (ONS_EDIT,)).value
    second = _create(patient_db, (ONS_EDIT,), now=NOW + timedelta(seconds=1)).value

    assert RX_ID.match(first.prescription_id)
    assert RX_ID.match(second.prescription_id)
    assert first.prescription_id != second.prescription_id


def test_create_prescription_returns_confirmed_event(patient_db: Path) -> None:
    result = _create(patient_db, (ONS_EDIT,))

    assert result.events == (
        Event(
            "prescription.confirmed",
            {
                "prescription_id": result.value.prescription_id,
                "patient_id": PATIENT_ID,
                "recommendation_id": None,
                "at": NOW_TEXT,
            },
        ),
    )


def test_create_prescription_leaves_recommendation_card(card_db: Path) -> None:
    before = read_card(card_db)

    _create(card_db, (ONS_EDIT,))

    assert read_card(card_db) == before


# ---- create_prescription: confirmed_at 단조 보정 --------------------------------


def test_create_prescription_confirmed_at_bumps_after_latest_of_patient(patient_db: Path) -> None:
    # 시계가 기존 처방보다 늦으면 시계 값, 이르면 기존 최대 + 1µs.
    insert_rx(patient_db, "rx_old", "2026-12-05T09:00:05.000000")
    insert_rx(patient_db, "rx_older", "2026-12-04T09:00:00.000000")

    result = _create(patient_db, (ONS_EDIT,), now=NOW)

    assert result.value.confirmed_at == "2026-12-05T09:00:05.000001"
    assert result.events[0].data["at"] == "2026-12-05T09:00:05.000001"
    assert _list(patient_db)[0].prescription_id == result.value.prescription_id


def test_create_prescription_ignores_other_patients_prescriptions(patient_db: Path) -> None:
    insert_rx(patient_db, "rx_other", "2026-12-06T00:00:00.000000", patient_id=OTHER_PATIENT)

    assert _create(patient_db, (ONS_EDIT,), now=NOW).value.confirmed_at == NOW_TEXT


def test_create_prescription_when_clock_goes_back_keeps_order(patient_db: Path) -> None:
    first = _create(patient_db, (ONS_EDIT,), now=NOW).value

    second = _create(patient_db, (REVIEW_EDIT,), now=NOW - timedelta(seconds=10)).value

    assert second.confirmed_at > first.confirmed_at
    assert _list(patient_db) == (second, first)


# ---- create_prescription: 실패 -------------------------------------------------


def test_create_prescription_unknown_patient_raises(patient_db: Path) -> None:
    with pytest.raises(PatientNotFoundError):
        _create(patient_db, (ONS_EDIT,), patient_id="NS99")


@pytest.mark.parametrize(
    "inputs",
    [
        (),
        (ONS_EDIT, ONS_EDIT),
        (ItemEdit("bad id", PrescriptionType.ONS, "x", "", None, None),),
        (ItemEdit("e1", PrescriptionType.ONS, "", "", None, None),),
        (ItemEdit("e1", PrescriptionType.ONS, "x", "", 0, None),),
    ],
    ids=["empty", "duplicate_item_id", "bad_item_id", "empty_title", "zero_duration"],
)
def test_create_prescription_invalid_items_raise_value_error(
    patient_db: Path, inputs: tuple[ItemEdit, ...]
) -> None:
    with pytest.raises(ValueError):
        _create(patient_db, inputs)

    assert _list(patient_db) == ()


def test_create_prescription_store_failure_leaves_nothing(
    patient_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*args: object, **kwargs: object) -> None:
        raise sqlite3.OperationalError("저장 실패")

    monkeypatch.setattr(rec_store, "insert_prescription", boom)

    with pytest.raises(sqlite3.OperationalError):
        _create(patient_db, (ONS_EDIT,))
    monkeypatch.undo()
    assert _list(patient_db) == ()


# ---- list_prescriptions ----------------------------------------------------------


def test_list_prescriptions_newest_first(patient_db: Path) -> None:
    insert_rx(patient_db, "rx_a", "2026-12-03T09:00:00.000000")
    insert_rx(patient_db, "rx_c", "2026-12-05T09:00:00.000000")
    insert_rx(patient_db, "rx_b", "2026-12-04T09:00:00.000000")
    insert_rx(patient_db, "rx_x", "2026-12-06T09:00:00.000000", patient_id=OTHER_PATIENT)

    assert [r.prescription_id for r in _list(patient_db)] == ["rx_c", "rx_b", "rx_a"]


def test_list_prescriptions_without_prescriptions_returns_empty(patient_db: Path) -> None:
    assert _list(patient_db) == ()


def test_list_prescriptions_unknown_patient_raises(patient_db: Path) -> None:
    with pytest.raises(PatientNotFoundError):
        _list(patient_db, "NS99")
