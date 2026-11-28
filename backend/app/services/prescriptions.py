"""처방 작성·이력 서비스 (스펙 3.3 "처방 직접 작성", 3.2 단조 증가 보정, 이벤트 표).

처방은 확정 뒤 바꾸지 않는다(data-model 6절). 그래서 이 모듈에는 처방을 만들고 읽는 함수만
있고 고치거나 지우는 함수는 없다. 처방 행은 직접 작성과 추천 확정
(`recommendations.confirm_recommendation`) 모두 `insert_prescription_record`로 만든다.
서비스는 연결을 열거나 닫지 않고 커밋·발행하지 않는다. 이벤트는 `WriteResult.events`로 돌려준다.
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime

from app.events.bus import Event
from app.services.clock import next_timestamp
from app.services.item_rules import ItemEdit, validate_items
from app.services.patients import require_patient
from app.services.ports import RecommendationItem
from app.services.unit_of_work import WriteResult
from app.storage import recommendations as rec_store
from app.storage.recommendations import PrescriptionRecord

CONFIRMED_EVENT = "prescription.confirmed"
PRESCRIPTION_ID_PREFIX = "rx_"


def create_prescription(
    conn: sqlite3.Connection,
    patient_id: str,
    inputs: tuple[ItemEdit, ...],
    now: datetime,
) -> WriteResult[PrescriptionRecord]:
    """추천 없이 처방을 만든다(`recommendation_id = None`). 그 환자의 추천 카드는 건드리지 않는다.

    항목은 요청 순서대로 `added_by = doctor`, `evidence = ()`로 만든다. 없는 환자 →
    `PatientNotFoundError`, 빈 항목·항목 규칙 위반 → `ValueError`.
    """
    require_patient(conn, patient_id)
    items = tuple(edit.to_doctor_item() for edit in inputs)
    return insert_prescription_record(conn, patient_id, None, items, now)


def list_prescriptions(conn: sqlite3.Connection, patient_id: str) -> tuple[PrescriptionRecord, ...]:
    """그 환자의 처방을 확정 시각 내림차순으로 돌려준다. 없는 환자 → `PatientNotFoundError`."""
    require_patient(conn, patient_id)
    return rec_store.list_prescriptions(conn, patient_id)


def insert_prescription_record(
    conn: sqlite3.Connection,
    patient_id: str,
    recommendation_id: str | None,
    items: tuple[RecommendationItem, ...],
    now: datetime,
) -> WriteResult[PrescriptionRecord]:
    """처방 한 건을 넣고 `prescription.confirmed` 이벤트와 함께 돌려준다.

    처방 직접 작성(`create_prescription`)과 추천 확정이 함께 쓰는 서비스 계층 함수다. 환자 존재·
    카드 상태는 호출자가 먼저 확인한다.

    ID는 `rx_` + uuid4 hex. `confirmed_at`은 `now`와 그 환자 처방의 최대 `confirmed_at + 1µs` 중
    큰 값이다(시계 역행 보정). 빈 항목·항목 규칙 위반 → `ValueError`.
    """
    if not items:
        raise ValueError("처방 항목은 1개 이상이어야 한다")
    validate_items(items)
    _, confirmed_at = next_timestamp(now, rec_store.max_prescription_confirmed_at(conn, patient_id))
    record = PrescriptionRecord(
        prescription_id=f"{PRESCRIPTION_ID_PREFIX}{uuid.uuid4().hex}",
        patient_id=patient_id,
        recommendation_id=recommendation_id,
        items=items,
        confirmed_at=confirmed_at,
        status="confirmed",
    )
    rec_store.insert_prescription(
        conn,
        prescription_id=record.prescription_id,
        patient_id=record.patient_id,
        recommendation_id=record.recommendation_id,
        items=record.items,
        confirmed_at=record.confirmed_at,
    )
    event = Event(
        CONFIRMED_EVENT,
        {
            "prescription_id": record.prescription_id,
            "patient_id": record.patient_id,
            "recommendation_id": record.recommendation_id,
            "at": record.confirmed_at,
        },
    )
    return WriteResult(record, (event,))
