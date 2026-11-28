"""시드 대상 조회 함수 테스트 (스펙 3.5).

fixture는 환자 2명·2일 데이터를 SQL로 직접 넣는다. 시드 적재 코드와 독립이다.
"""

from __future__ import annotations

import dataclasses
import sqlite3
from collections.abc import Iterator
from datetime import date, datetime
from pathlib import Path

import pytest

from app.intake.types import QualityIssue, SlotStatus
from app.nutrition.types import (
    AlertLevel,
    MealType,
    Nutrient,
    NutrientEvidence,
    OrderStatus,
    RecordStatus,
    Sex,
    TargetSource,
)
from app.storage.codec import (
    evidence_to_json,
    nutrients_to_json,
    quality_issues_to_json,
    strings_to_json,
)
from app.storage.db import connect
from app.storage.queries import (
    demo_timestamp,
    get_demo_date,
    get_latest_alert,
    get_meal_plan,
    get_patient,
    get_patient_history,
    list_alerts,
    list_daily_intakes,
    list_meal_orders,
    list_patients,
)
from app.storage.records import (
    AlertRow,
    AssessmentRow,
    DailyIntakeRow,
    MealOrder,
    MealPlan,
    MealPlanSlot,
    Patient,
    PatientHistory,
    SlotIntakeRow,
    TargetRow,
    WeightRow,
)
from tests.storage.rows import (
    insert_alert,
    insert_assessment,
    insert_meal_order,
    insert_meal_plan,
    insert_patient,
    insert_row,
    insert_slot,
    insert_slot_intake,
)

DAY1 = "2026-11-28"
DAY2 = "2026-11-29"
EVIDENCE = (
    NutrientEvidence(nutrient=Nutrient.ENERGY, avg_pct=70.0, low_days_streak=0),
    NutrientEvidence(nutrient=Nutrient.PROTEIN, avg_pct=None, low_days_streak=2),
)
NO_MEAL = {
    "diet_category": None,
    "diet_code": None,
    "order_from": None,
    "order_note": None,
    "energy_kcal_est": None,
    "protein_g_est": None,
}


def _plan_id(day: str, meal: str) -> str:
    return f"{day}_{meal}_general"


def _insert_plan(conn: sqlite3.Connection, day: str, meal: str) -> None:
    """6칸 배식 계획. DAY2 점심 slot_5만 미배식 칸이다. 칸은 일부러 역순으로 넣는다."""
    plan_id = _plan_id(day, meal)
    insert_meal_plan(conn, meal_plan_id=plan_id, date=day, meal=meal)
    dish_types = ("rice", "soup", "main", "side", "side", "kimchi")
    for index in range(6, 0, -1):
        unserved = day == DAY2 and meal == "lunch" and index == 5
        insert_slot(
            conn,
            meal_plan_id=plan_id,
            slot_id=f"slot_{index}",
            position=f"위치 {index}",
            dish_type=dish_types[index - 1],
            menu_name=None if unserved else f"메뉴 {index}",
            served_g=0 if unserved else 100.0,
            energy_kcal=0 if unserved else 50.0 * index,
            protein_g=0 if unserved else 1.5 * index,
        )


def _insert_order(
    conn: sqlite3.Connection, patient_id: str, day: str, meal: str, **overrides: object
) -> str:
    order_id = f"{patient_id}_{day}_{meal}"
    insert_meal_order(
        conn,
        meal_order_id=order_id,
        patient_id=patient_id,
        meal_plan_id=_plan_id(day, meal),
        order_from=f"{DAY1} breakfast",
        energy_kcal_est=500.0,
        protein_g_est=20.0,
        **overrides,
    )
    return order_id


def _insert_patients(conn: sqlite3.Connection) -> None:
    # patient_id 순서 검증을 위해 NS02를 먼저 넣는다.
    for patient_id, sex, conditions, room, height in (
        ("NS02", "female", ("당뇨", "고혈압"), None, None),
        ("NS01", "male", ("고혈압",), "301호", 166.0),
    ):
        insert_patient(
            conn,
            patient_id=patient_id,
            display_name=patient_id,
            room=room,
            sex=sex,
            birth_year=1953,
            height_cm=height,
            conditions=strings_to_json(conditions),
            observation_start=DAY1,
        )


def _insert_history(conn: sqlite3.Connection) -> None:
    # 날짜 오름차순 검증을 위해 늦은 날짜를 먼저 넣는다.
    for patient_id, measured_on, weight in (
        ("NS01", "2026-11-20", 62.5),
        ("NS01", "2026-10-21", 63.0),
        ("NS02", "2026-11-01", 50.0),
    ):
        insert_row(
            conn,
            "patient_weights",
            {"patient_id": patient_id, "measured_on": measured_on, "weight_kg": weight},
        )
    for effective_from, energy, source, note in (
        (DAY2, 1700.0, "espen_weight", None),
        (DAY1, 1800.0, "team_set", "모의 진료팀 설정"),
    ):
        insert_row(
            conn,
            "patient_targets",
            {
                "patient_id": "NS01",
                "effective_from": effective_from,
                "energy_kcal": energy,
                "protein_g": 65.0,
                "source": source,
                "note": note,
            },
        )
    for assessed_on, kind, result, score in (
        (DAY2, "mna_sf", None, 9.0),
        (DAY1, "swallowing", "normal", None),
        (DAY1, "chewing", "normal", None),
    ):
        insert_assessment(
            conn,
            patient_id="NS01",
            assessed_on=assessed_on,
            kind=kind,
            result=result,
            score=score,
            note=None,
        )


def _insert_meals(conn: sqlite3.Connection) -> None:
    # 끼니 정렬 검증을 위해 저녁 → 아침 → 점심 순서, 늦은 날짜부터 넣는다.
    for day in (DAY2, DAY1):
        for meal in ("dinner", "breakfast", "lunch"):
            _insert_plan(conn, day, meal)
    for day in (DAY2, DAY1):
        for meal in ("dinner", "breakfast", "lunch"):
            if day == DAY2 and meal == "dinner":
                # 금식 발주도 record_status는 not_recorded다(스펙 4절).
                insert_meal_order(
                    conn,
                    meal_order_id=f"NS01_{day}_{meal}",
                    patient_id="NS01",
                    meal_plan_id=_plan_id(day, meal),
                    order_status="npo",
                    record_status="not_recorded",
                    **NO_MEAL,
                )
                continue
            order_id = _insert_order(conn, "NS01", day, meal)
            slots = [f"slot_{i}" for i in (3, 1, 2, 4, 5, 6)]
            if day == DAY2 and meal == "lunch":
                slots.remove("slot_5")
            for slot_id in slots:
                insert_slot_intake(conn, meal_order_id=order_id, slot_id=slot_id)
            _insert_order(conn, "NS02", day, meal, record_status="not_recorded")
    order_id = f"NS01_{DAY1}_breakfast"
    conn.execute(
        "UPDATE slot_intakes SET intake_fraction_est = NULL, status = 'not_determinable', "
        "quality_issues = ? WHERE meal_order_id = ? AND slot_id = 'slot_2'",
        (quality_issues_to_json((QualityIssue.BLUR, QualityIssue.OCCLUDED)), order_id),
    )
    conn.execute("UPDATE meal_orders SET incomplete = 1 WHERE meal_order_id = ?", (order_id,))


def _insert_daily_and_alerts(conn: sqlite3.Connection) -> None:
    for day, energy, pct in ((DAY2, None, None), (DAY1, 1500.0, 83.3)):
        insert_row(
            conn,
            "daily_intakes",
            {
                "patient_id": "NS01",
                "date": day,
                "energy_kcal": energy,
                "protein_g": None if energy is None else 55.0,
                "energy_pct": pct,
                "protein_pct": None if pct is None else 84.6,
                "recorded_meals": 0 if energy is None else 3,
                "unrecorded_meals": 2 if energy is None else 0,
                "npo_meals": 1 if energy is None else 0,
            },
        )
    evidence = evidence_to_json(EVIDENCE)
    both = nutrients_to_json((Nutrient.ENERGY, Nutrient.PROTEIN))
    for alert_id, evaluated_at, level, nutrients, period, values in (
        ("alert_c", f"{DAY2}T10:00:00", "caution", '["energy"]', f"{DAY1}~{DAY2}", evidence),
        ("alert_b", f"{DAY1}T23:59:59", "none", "[]", None, None),
        ("alert_a", f"{DAY1}T23:59:59", "warning", both, None, "[]"),
        ("alert_z", "2026-11-30T00:00:00", "none", "[]", None, "[]"),
    ):
        insert_alert(
            conn,
            alert_id=alert_id,
            patient_id="NS01",
            evaluated_at=evaluated_at,
            level=level,
            basis_period=period,
            basis_values=values,
            nutrients=nutrients,
            unrecorded_meals=1,
        )
    insert_alert(
        conn,
        alert_id="alert_other",
        patient_id="NS02",
        evaluated_at=f"{DAY1}T23:59:59",
        level="none",
        basis_period=None,
        nutrients="[]",
        unrecorded_meals=3,
    )


@pytest.fixture
def conn(db_path: Path) -> Iterator[sqlite3.Connection]:
    """환자 2명(NS01·NS02)·2일(DAY1·DAY2) 데이터를 넣은 연결."""
    with connect(db_path) as connection:
        insert_row(connection, "seed_meta", {"key": "demo_date", "value": "2026-12-05"})
        _insert_patients(connection)
        _insert_history(connection)
        _insert_meals(connection)
        _insert_daily_and_alerts(connection)
        connection.commit()
        yield connection


# 시연일 --------------------------------------------------------------------


def test_get_demo_date_reads_seed_meta(conn: sqlite3.Connection) -> None:
    assert get_demo_date(conn) == date(2026, 12, 5)


def test_get_demo_date_raises_when_missing(db_path: Path) -> None:
    with connect(db_path) as empty, pytest.raises(LookupError, match="demo_date"):
        get_demo_date(empty)


def test_get_demo_date_raises_when_value_is_null(db_path: Path) -> None:
    with connect(db_path) as conn:
        insert_row(conn, "seed_meta", {"key": "demo_date", "value": None})
        with pytest.raises(LookupError, match="demo_date"):
            get_demo_date(conn)


def test_demo_timestamp_combines_demo_date_and_now_time() -> None:
    result = demo_timestamp(date(2026, 12, 5), datetime(2026, 11, 27, 10, 0, 0))
    assert result == "2026-12-05T10:00:00"


def test_demo_timestamp_drops_microseconds() -> None:
    result = demo_timestamp(date(2026, 12, 5), datetime(2026, 11, 27, 9, 5, 7, 123456))
    assert result == "2026-12-05T09:05:07"


# 환자 ----------------------------------------------------------------------


def test_list_patients_ordered_by_patient_id(conn: sqlite3.Connection) -> None:
    patients = list_patients(conn)
    assert isinstance(patients, tuple)
    assert [p.patient_id for p in patients] == ["NS01", "NS02"]


def test_list_patients_parses_fields(conn: sqlite3.Connection) -> None:
    ns01, ns02 = list_patients(conn)
    assert ns01 == Patient(
        patient_id="NS01",
        display_name="NS01",
        room="301호",
        sex=Sex.MALE,
        birth_year=1953,
        height_cm=pytest.approx(166.0),
        default_diet_type="general",
        conditions=("고혈압",),
        diet_restrictions="",
        ckd_dialysis="none",
        observation_start=date(2026, 11, 28),
        data_source="mock",
    )
    assert ns02.conditions == ("당뇨", "고혈압")
    assert ns02.room is None
    assert ns02.height_cm is None
    assert isinstance(ns02.sex, Sex)
    assert ns02.sex is Sex.FEMALE


def test_get_patient_returns_record(conn: sqlite3.Connection) -> None:
    patient = get_patient(conn, "NS02")
    assert patient is not None
    assert patient.patient_id == "NS02"
    assert patient.conditions == ("당뇨", "고혈압")


def test_get_patient_returns_none_when_missing(conn: sqlite3.Connection) -> None:
    assert get_patient(conn, "NS99") is None


# 환자 이력 -----------------------------------------------------------------


def test_get_patient_history_sorted_by_date(conn: sqlite3.Connection) -> None:
    history = get_patient_history(conn, "NS01")
    assert isinstance(history, PatientHistory)
    assert history.patient_id == "NS01"
    assert history.weights == (
        WeightRow(measured_on=date(2026, 10, 21), weight_kg=pytest.approx(63.0)),
        WeightRow(measured_on=date(2026, 11, 20), weight_kg=pytest.approx(62.5)),
    )
    assert [t.effective_from for t in history.targets] == [date(2026, 11, 28), date(2026, 11, 29)]
    assert history.targets[0] == TargetRow(
        effective_from=date(2026, 11, 28),
        energy_kcal=pytest.approx(1800.0),
        protein_g=pytest.approx(65.0),
        source=TargetSource.TEAM_SET,
        note="모의 진료팀 설정",
    )
    assert history.targets[1].source is TargetSource.ESPEN_WEIGHT
    assert history.targets[1].note is None
    assert [(a.assessed_on, a.kind) for a in history.assessments] == [
        (date(2026, 11, 28), "chewing"),
        (date(2026, 11, 28), "swallowing"),
        (date(2026, 11, 29), "mna_sf"),
    ]
    assert history.assessments[2] == AssessmentRow(
        assessed_on=date(2026, 11, 29), kind="mna_sf", result=None, score=9.0, note=None
    )


def test_get_patient_history_only_for_that_patient(conn: sqlite3.Connection) -> None:
    history = get_patient_history(conn, "NS02")
    assert [w.weight_kg for w in history.weights] == [pytest.approx(50.0)]
    assert history.targets == ()
    assert history.assessments == ()


def test_get_patient_history_empty_for_unknown_patient(conn: sqlite3.Connection) -> None:
    assert get_patient_history(conn, "NS99") == PatientHistory(
        patient_id="NS99", weights=(), targets=(), assessments=()
    )


# 배식 계획 -----------------------------------------------------------------


def test_get_meal_plan_returns_six_slots_in_slot_order(conn: sqlite3.Connection) -> None:
    plan = get_meal_plan(conn, date(2026, 11, 28), MealType.LUNCH)
    assert isinstance(plan, MealPlan)
    assert plan.meal_plan_id == "2026-11-28_lunch_general"
    assert plan.on == date(2026, 11, 28)
    assert plan.meal is MealType.LUNCH
    assert plan.diet_type == "general"
    assert plan.baseline_photo_id is None
    assert isinstance(plan.slots, tuple)
    assert [s.slot_id for s in plan.slots] == [f"slot_{i}" for i in range(1, 7)]
    assert plan.slots[2] == MealPlanSlot(
        slot_id="slot_3",
        position="위치 3",
        dish_type="main",
        menu_name="메뉴 3",
        served_g=pytest.approx(100.0),
        energy_kcal=pytest.approx(150.0),
        protein_g=pytest.approx(4.5),
    )


def test_get_meal_plan_unserved_slot_has_no_menu(conn: sqlite3.Connection) -> None:
    plan = get_meal_plan(conn, date(2026, 11, 29), MealType.LUNCH, diet_type="general")
    assert plan is not None
    slot_5 = plan.slots[4]
    assert slot_5.slot_id == "slot_5"
    assert slot_5.menu_name is None
    assert slot_5.served_g == pytest.approx(0.0)


def test_get_meal_plan_returns_none_when_missing(conn: sqlite3.Connection) -> None:
    assert get_meal_plan(conn, date(2026, 12, 1), MealType.LUNCH) is None
    assert get_meal_plan(conn, date(2026, 11, 28), MealType.LUNCH, diet_type="soft") is None


# 발주 ----------------------------------------------------------------------


def test_list_meal_orders_sorted_by_date_and_meal(conn: sqlite3.Connection) -> None:
    orders = list_meal_orders(conn, "NS01", date(2026, 11, 28), date(2026, 11, 29))
    assert isinstance(orders, tuple)
    assert [(o.on, o.meal) for o in orders] == [
        (date(2026, 11, 28), MealType.BREAKFAST),
        (date(2026, 11, 28), MealType.LUNCH),
        (date(2026, 11, 28), MealType.DINNER),
        (date(2026, 11, 29), MealType.BREAKFAST),
        (date(2026, 11, 29), MealType.LUNCH),
        (date(2026, 11, 29), MealType.DINNER),
    ]
    assert all(o.patient_id == "NS01" for o in orders)


def test_list_meal_orders_filters_period_inclusive(conn: sqlite3.Connection) -> None:
    only_day2 = list_meal_orders(conn, "NS01", date(2026, 11, 29), date(2026, 11, 29))
    assert {o.on for o in only_day2} == {date(2026, 11, 29)}
    assert len(only_day2) == 3
    assert list_meal_orders(conn, "NS01", date(2026, 11, 30), date(2026, 12, 5)) == ()


def test_list_meal_orders_parses_order_fields(conn: sqlite3.Connection) -> None:
    orders = list_meal_orders(conn, "NS01", date(2026, 11, 28), date(2026, 11, 28))
    breakfast = orders[0]
    assert isinstance(breakfast, MealOrder)
    assert breakfast.meal_order_id == "NS01_2026-11-28_breakfast"
    assert breakfast.meal_plan_id == "2026-11-28_breakfast_general"
    assert breakfast.order_status is OrderStatus.ORDERED
    assert breakfast.record_status is RecordStatus.RECORDED
    assert breakfast.order_from == "2026-11-28 breakfast"
    assert breakfast.diet_category == "상식"
    assert breakfast.energy_kcal_est == pytest.approx(500.0)
    assert breakfast.protein_g_est == pytest.approx(20.0)
    assert breakfast.incomplete is True
    assert orders[1].incomplete is False
    assert breakfast.staff_zero_reason is None
    assert breakfast.post_photo_id is None
    assert breakfast.data_source == "mock"


def test_list_meal_orders_npo_is_not_recorded(conn: sqlite3.Connection) -> None:
    orders = list_meal_orders(conn, "NS01", date(2026, 11, 29), date(2026, 11, 29))
    npo = orders[2]
    assert npo.order_status is OrderStatus.NPO
    assert npo.record_status is RecordStatus.NOT_RECORDED
    assert npo.energy_kcal_est is None
    assert npo.protein_g_est is None
    assert npo.order_from is None
    assert npo.slot_intakes == ()


def test_list_meal_orders_includes_slot_intakes(conn: sqlite3.Connection) -> None:
    orders = list_meal_orders(conn, "NS01", date(2026, 11, 28), date(2026, 11, 29))
    breakfast = orders[0]
    assert isinstance(breakfast.slot_intakes, tuple)
    assert [s.slot_id for s in breakfast.slot_intakes] == [f"slot_{i}" for i in range(1, 7)]
    assert breakfast.slot_intakes[0] == SlotIntakeRow(
        slot_id="slot_1",
        intake_fraction_est=pytest.approx(0.5),
        status=SlotStatus.ESTIMATED,
        quality_issues=(),
        estimate_basis="mock",
    )
    slot_2 = breakfast.slot_intakes[1]
    assert slot_2.intake_fraction_est is None
    assert slot_2.status is SlotStatus.NOT_DETERMINABLE
    assert slot_2.quality_issues == (QualityIssue.BLUR, QualityIssue.OCCLUDED)
    assert all(isinstance(q, QualityIssue) for q in slot_2.quality_issues)
    day2_lunch = orders[4]
    served = ["slot_1", "slot_2", "slot_3", "slot_4", "slot_6"]
    assert [s.slot_id for s in day2_lunch.slot_intakes] == served


def test_list_meal_orders_only_for_that_patient(conn: sqlite3.Connection) -> None:
    orders = list_meal_orders(conn, "NS02", date(2026, 11, 28), date(2026, 11, 29))
    assert len(orders) == 5
    assert all(o.patient_id == "NS02" for o in orders)
    assert all(o.record_status is RecordStatus.NOT_RECORDED for o in orders)
    assert all(o.slot_intakes == () for o in orders)


# 일별 섭취 -----------------------------------------------------------------


def test_list_daily_intakes_sorted_by_date(conn: sqlite3.Connection) -> None:
    rows = list_daily_intakes(conn, "NS01", date(2026, 11, 28), date(2026, 11, 29))
    assert isinstance(rows, tuple)
    assert rows[0] == DailyIntakeRow(
        patient_id="NS01",
        on=date(2026, 11, 28),
        energy_kcal=pytest.approx(1500.0),
        protein_g=pytest.approx(55.0),
        energy_pct=pytest.approx(83.3),
        protein_pct=pytest.approx(84.6),
        recorded_meals=3,
        unrecorded_meals=0,
        npo_meals=0,
    )
    assert rows[1].on == date(2026, 11, 29)


def test_list_daily_intakes_null_amounts_are_none(conn: sqlite3.Connection) -> None:
    (row,) = list_daily_intakes(conn, "NS01", date(2026, 11, 29), date(2026, 11, 29))
    assert row.energy_kcal is None
    assert row.protein_g is None
    assert row.energy_pct is None
    assert row.protein_pct is None
    assert (row.recorded_meals, row.unrecorded_meals, row.npo_meals) == (0, 2, 1)


def test_list_daily_intakes_empty_outside_period(conn: sqlite3.Connection) -> None:
    assert list_daily_intakes(conn, "NS01", date(2026, 12, 1), date(2026, 12, 5)) == ()
    assert list_daily_intakes(conn, "NS02", date(2026, 11, 28), date(2026, 11, 29)) == ()


# 경고 ----------------------------------------------------------------------


def test_list_alerts_sorted_by_evaluated_at_then_alert_id(conn: sqlite3.Connection) -> None:
    alerts = list_alerts(conn, "NS01", date(2026, 11, 28), date(2026, 11, 29))
    assert isinstance(alerts, tuple)
    assert [a.alert_id for a in alerts] == ["alert_a", "alert_b", "alert_c"]
    # 같은 evaluated_at 두 행은 alert_id 순이다.
    assert alerts[0].evaluated_at == alerts[1].evaluated_at == "2026-11-28T23:59:59"


def test_list_alerts_period_uses_date_part_of_evaluated_at(conn: sqlite3.Connection) -> None:
    day2 = list_alerts(conn, "NS01", date(2026, 11, 29), date(2026, 11, 29))
    assert [a.alert_id for a in day2] == ["alert_c"]
    day3 = list_alerts(conn, "NS01", date(2026, 11, 30), date(2026, 11, 30))
    assert [a.alert_id for a in day3] == ["alert_z"]
    day1 = list_alerts(conn, "NS01", date(2026, 11, 28), date(2026, 11, 28))
    assert [a.alert_id for a in day1] == ["alert_a", "alert_b"]


def test_list_alerts_only_for_that_patient(conn: sqlite3.Connection) -> None:
    alerts = list_alerts(conn, "NS02", date(2026, 11, 28), date(2026, 11, 30))
    assert [a.alert_id for a in alerts] == ["alert_other"]


def test_list_alerts_parses_nutrients_and_basis_values(conn: sqlite3.Connection) -> None:
    alerts = list_alerts(conn, "NS01", date(2026, 11, 28), date(2026, 11, 29))
    caution = alerts[2]
    assert caution == AlertRow(
        alert_id="alert_c",
        patient_id="NS01",
        evaluated_at="2026-11-29T10:00:00",
        level=AlertLevel.CAUTION,
        basis_period="2026-11-28~2026-11-29",
        basis_values=EVIDENCE,
        nutrients=(Nutrient.ENERGY,),
        unrecorded_meals=1,
    )
    assert isinstance(caution.level, AlertLevel)
    assert all(isinstance(e.nutrient, Nutrient) for e in caution.basis_values)
    warning = alerts[0]
    assert warning.level is AlertLevel.WARNING
    assert warning.nutrients == (Nutrient.ENERGY, Nutrient.PROTEIN)
    assert all(isinstance(n, Nutrient) for n in warning.nutrients)
    assert warning.basis_values == ()
    assert warning.basis_period is None


def test_list_alerts_null_basis_values_is_empty_tuple(conn: sqlite3.Connection) -> None:
    alerts = list_alerts(conn, "NS01", date(2026, 11, 28), date(2026, 11, 28))
    none_alert = alerts[1]
    assert none_alert.level is AlertLevel.NONE
    assert none_alert.basis_values == ()
    assert none_alert.nutrients == ()


def test_get_latest_alert_picks_latest_on_or_before_day(conn: sqlite3.Connection) -> None:
    latest = get_latest_alert(conn, "NS01", date(2026, 11, 29))
    assert latest == list_alerts(conn, "NS01", date(2026, 11, 28), date(2026, 11, 29))[-1]
    assert latest is not None and latest.alert_id == "alert_c"
    # 같은 evaluated_at이면 alert_id가 큰 것이다.
    same_time = get_latest_alert(conn, "NS01", date(2026, 11, 28))
    assert same_time is not None and same_time.alert_id == "alert_b"
    assert get_latest_alert(conn, "NS02", date(2026, 12, 31)) is not None


def test_get_latest_alert_returns_none_without_judgement(conn: sqlite3.Connection) -> None:
    assert get_latest_alert(conn, "NS01", date(2026, 11, 27)) is None
    assert get_latest_alert(conn, "NS99", date(2026, 12, 31)) is None


# 레코드 --------------------------------------------------------------------


def _one_of_each(conn: sqlite3.Connection) -> dict[str, object]:
    """레코드 타입마다 조회 결과 인스턴스 하나."""
    history = get_patient_history(conn, "NS01")
    plan = get_meal_plan(conn, date(2026, 11, 28), MealType.BREAKFAST)
    assert plan is not None
    order = list_meal_orders(conn, "NS01", date(2026, 11, 28), date(2026, 11, 28))[0]
    period = (conn, "NS01", date(2026, 11, 28), date(2026, 11, 29))
    return {
        "Patient": list_patients(conn)[0],
        "WeightRow": history.weights[0],
        "TargetRow": history.targets[0],
        "AssessmentRow": history.assessments[0],
        "PatientHistory": history,
        "MealPlanSlot": plan.slots[0],
        "MealPlan": plan,
        "SlotIntakeRow": order.slot_intakes[0],
        "MealOrder": order,
        "DailyIntakeRow": list_daily_intakes(*period)[0],
        "AlertRow": list_alerts(*period)[0],
    }


RECORD_TYPES: dict[str, type] = {
    "Patient": Patient,
    "WeightRow": WeightRow,
    "TargetRow": TargetRow,
    "AssessmentRow": AssessmentRow,
    "PatientHistory": PatientHistory,
    "MealPlanSlot": MealPlanSlot,
    "MealPlan": MealPlan,
    "SlotIntakeRow": SlotIntakeRow,
    "MealOrder": MealOrder,
    "DailyIntakeRow": DailyIntakeRow,
    "AlertRow": AlertRow,
}


@pytest.mark.parametrize("name", list(RECORD_TYPES))
def test_record_field_assignment_raises(conn: sqlite3.Connection, name: str) -> None:
    record = _one_of_each(conn)[name]
    assert isinstance(record, RECORD_TYPES[name])
    first_field = dataclasses.fields(record)[0].name
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(record, first_field, None)
