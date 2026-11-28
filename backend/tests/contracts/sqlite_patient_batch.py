"""`SqlitePatientData` 계약 테스트 배치 적재 (스펙 3.8 "계약 테스트", 스펙 T1 §3.4).

빈 스키마 DB에 `FakePatientData`의 공개 상수와 같은 값을 넣는다.

- `seed_meta.demo_date`, 환자 NS01~NS04
- `DAILY_INTAKES`의 날짜마다 끼니 3개의 `meal_plans`, 기록·미기록·금식 끼니 수대로
  `meal_orders`, 같은 값의 `daily_intakes` 행. 발주 없는 날(11-22)은 아무것도 넣지 않는다.
- `ALERTS_BY_DAY`의 판정을 `alerts`로
- 카드의 `alert_id` 외래 키용 판정 행(`CARD_ALERT_DAY`, 수준 `none`)
- 카드(시각은 시간대 없는 앱 저장 형식 문자열)와 `chat_threads` 한 행
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from datetime import date, datetime, time
from pathlib import Path

from app.nutrition.types import AlertResult, DailyIntake
from app.services import fake_patient_data as fake
from app.services.clock import format_app_timestamp
from app.services.ports import RecommendationCard
from app.storage import recommendations as rec_store
from app.storage.codec import evidence_to_json, format_basis_period, nutrients_to_json
from app.storage.db import connect
from tests.storage.rows import (
    insert_alert,
    insert_meal_order,
    insert_meal_plan,
    insert_patient,
    insert_row,
)

CHAT_THREAD_ID = "thread-ns01"
DEMO_DATE = fake.SUMMARY_ON
# 카드 판정 행의 날짜. NS01의 요약 판정에는 영향 없음. NS02·NS03은 이 행(none)이 최신 판정이
# 되어 Fake(None)와 다르다. 계약은 NS04만 판정 없음을 요구한다.
CARD_ALERT_DAY = date(2026, 11, 1)
_MEALS = ("breakfast", "lunch", "dinner")
_DIET_TYPE = "general"


def _app_timestamp(value: datetime) -> str:
    """시간대를 떼고 앱 저장 형식(마이크로초 6자리) 문자열로 바꾼다."""
    return format_app_timestamp(value.replace(tzinfo=None))


def _day_start(day: date) -> str:
    return format_app_timestamp(datetime.combine(day, time()))


def _insert_meal_plans(conn: sqlite3.Connection, day: date) -> None:
    for meal in _MEALS:
        insert_meal_plan(
            conn,
            meal_plan_id=f"{day.isoformat()}_{meal}_{_DIET_TYPE}",
            date=day.isoformat(),
            meal=meal,
            diet_type=_DIET_TYPE,
        )


def _order_states(row: DailyIntake) -> list[tuple[str, str]]:
    """끼니 순서대로 (order_status, record_status). 기록 → 미기록 → 금식 순으로 배정한다."""
    return (
        [("ordered", "recorded")] * row.recorded_meals
        + [("ordered", "not_recorded")] * row.unrecorded_meals
        + [("npo", "not_recorded")] * row.npo_meals
    )


def _insert_day(conn: sqlite3.Connection, patient_id: str, row: DailyIntake) -> None:
    day = row.on.isoformat()
    states = _order_states(row)
    if len(states) != len(_MEALS):
        raise ValueError(f"끼니 수가 3이 아니다: {patient_id} {day}")

    def per_meal(total: float | None, is_recorded: bool) -> float | None:
        # 하루 값을 기록된 끼니에 똑같이 나눈다. 기록되지 않은 끼니는 추정값이 없다.
        return (total or 0.0) / row.recorded_meals if is_recorded else None

    for meal, (order_status, record_status) in zip(_MEALS, states, strict=True):
        is_recorded = record_status == "recorded"
        insert_meal_order(
            conn,
            meal_order_id=f"{patient_id}_{day}_{meal}",
            patient_id=patient_id,
            meal_plan_id=f"{day}_{meal}_{_DIET_TYPE}",
            order_status=order_status,
            record_status=record_status,
            energy_kcal_est=per_meal(row.energy_kcal, is_recorded),
            protein_g_est=per_meal(row.protein_g, is_recorded),
        )
    insert_row(
        conn,
        "daily_intakes",
        {
            "patient_id": patient_id,
            "date": day,
            "energy_kcal": row.energy_kcal,
            "protein_g": row.protein_g,
            "energy_pct": row.energy_pct,
            "protein_pct": row.protein_pct,
            "recorded_meals": row.recorded_meals,
            "unrecorded_meals": row.unrecorded_meals,
            "npo_meals": row.npo_meals,
        },
    )


def _insert_judgement(
    conn: sqlite3.Connection, patient_id: str, day: date, result: AlertResult
) -> None:
    insert_alert(
        conn,
        alert_id=f"alert-{patient_id}-{day.isoformat()}",
        patient_id=patient_id,
        evaluated_at=_day_start(day),
        level=str(result.level),
        basis_period=format_basis_period(result.period_start, result.period_end),
        basis_values=evidence_to_json(result.evidence),
        nutrients=nutrients_to_json(result.nutrients),
        unrecorded_meals=result.unrecorded_meals,
    )


def _insert_card(conn: sqlite3.Connection, card: RecommendationCard) -> None:
    if card.alert_id is not None:
        insert_alert(
            conn,
            alert_id=card.alert_id,
            patient_id=card.patient_id,
            evaluated_at=_day_start(CARD_ALERT_DAY),
            level="none",
            basis_period=None,
            basis_values="[]",
            nutrients="[]",
            unrecorded_meals=0,
        )
    rec_store.insert_card(
        conn,
        recommendation_id=card.recommendation_id,
        patient_id=card.patient_id,
        alert_id=card.alert_id,
        items=card.items,
        cautions=card.cautions,
        last_modified_by=card.last_modified_by,
        thread_id=card.thread_id,
        created_at=_app_timestamp(card.created_at),
        updated_at=_app_timestamp(card.updated_at),
        status=card.status,
    )


def load_patient_batch(db_path: Path, cards: Iterable[RecommendationCard]) -> None:
    """빈 스키마 `db_path`에 계약 배치를 넣는다. `cards`는 `default_cards()` 등."""
    with connect(db_path) as conn:
        insert_row(conn, "seed_meta", {"key": "demo_date", "value": DEMO_DATE.isoformat()})
        for patient_id in fake.PATIENT_IDS:
            insert_patient(conn, patient_id=patient_id, display_name=patient_id)
        # 배식 계획은 환자와 무관하게 날짜마다 한 번만 넣는다.
        plan_days = sorted({row.on for rows in fake.DAILY_INTAKES.values() for row in rows})
        for day in plan_days:
            _insert_meal_plans(conn, day)
        for patient_id, rows in fake.DAILY_INTAKES.items():
            for row in rows:
                _insert_day(conn, patient_id, row)
        for patient_id, pairs in fake.ALERTS_BY_DAY.items():
            for day, result in pairs:
                _insert_judgement(conn, patient_id, day, result)
        insert_row(
            conn,
            "chat_threads",
            {
                "thread_id": CHAT_THREAD_ID,
                "patient_id": fake.PATIENT_WITH_ACTIVE,
                "created_at": _day_start(DEMO_DATE),
            },
        )
        for card in cards:
            _insert_card(conn, card)
