"""일별 섭취·섭취 요약·경고 조회 서비스 테스트 (스펙 3.8 일별 섭취 규칙, 3.3 응답 모델)."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import pytest

from app.nutrition.fake import FakeNutritionEngine
from app.nutrition.types import (
    AlertLevel,
    DailyIntake,
    DailyTarget,
    MealRecord,
    Nutrient,
    NutrientEvidence,
    PatientProfile,
    TargetRecord,
    TargetSource,
    WeightRecord,
)
from app.services.patients import (
    alert_to_result,
    daily_rows,
    intake_summary,
    latest_alert,
    left_menus,
    list_patients_with_alert,
)
from app.services.ports import PatientNotFoundError
from app.storage import queries
from app.storage.db import connect
from app.storage.records import AlertRow
from tests.storage.demo import DEMO
from tests.storage.rows import (
    insert_alert,
    insert_meal_order,
    insert_meal_plan,
    insert_patient,
    insert_row,
)


@dataclass
class DayTargetEngine(FakeNutritionEngine):
    """날짜마다 다른 목표를 주고 호출을 기록하는 엔진."""

    target_calls: list[tuple[PatientProfile, tuple, tuple, date]] = field(default_factory=list)
    intake_calls: list[tuple[date, tuple[MealRecord, ...]]] = field(default_factory=list)

    def daily_target(
        self,
        profile: PatientProfile,
        targets: tuple[TargetRecord, ...],
        weights: tuple[WeightRecord, ...],
        on: date,
    ) -> DailyTarget:
        self.target_calls.append((profile, targets, weights, on))
        return DailyTarget(1000.0 + on.day, 40.0 + on.day, TargetSource.TEAM_SET)

    def daily_intake(
        self, on: date, meals: tuple[MealRecord, ...], target: DailyTarget
    ) -> DailyIntake:
        self.intake_calls.append((on, meals))
        return super().daily_intake(on, meals, target)


def _count(conn: sqlite3.Connection, table: str) -> int:
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def _d0_unrecorded(conn: sqlite3.Connection, patient_id: str) -> tuple[int, int]:
    """시드 D0 발주의 (미기록 일반 발주 수, 금식·취소 수)."""
    row = conn.execute(
        "SELECT SUM(o.order_status = 'ordered' AND o.record_status = 'not_recorded') AS u, "
        "SUM(o.order_status <> 'ordered') AS n FROM meal_orders AS o "
        "JOIN meal_plans AS p ON p.meal_plan_id = o.meal_plan_id "
        "WHERE o.patient_id = ? AND p.date = ?",
        (patient_id, DEMO.isoformat()),
    ).fetchone()
    return row["u"], row["n"]


# daily_rows ----------------------------------------------------------------


@pytest.mark.parametrize("patient_id", ["NS01", "NS03", "NS10"])
def test_daily_rows_seed_d0_is_computed_row(
    service_db: Path, engine: FakeNutritionEngine, fake_target: DailyTarget, patient_id: str
) -> None:
    with connect(service_db) as conn:
        assert queries.list_daily_intakes(conn, patient_id, DEMO, DEMO) == ()
        unrecorded, npo = _d0_unrecorded(conn, patient_id)
        rows = daily_rows(conn, engine, patient_id, DEMO - timedelta(days=13), DEMO)

    assert rows[-1] == DailyIntake(
        on=DEMO,
        energy_kcal=None,
        protein_g=None,
        energy_pct=None,
        protein_pct=None,
        recorded_meals=0,
        unrecorded_meals=unrecorded,
        npo_meals=npo,
        target=fake_target,
    )
    assert unrecorded > 0


def test_daily_rows_seed_stored_days_match_daily_intakes(
    service_db: Path, engine: FakeNutritionEngine, fake_target: DailyTarget
) -> None:
    start = DEMO - timedelta(days=13)
    with connect(service_db) as conn:
        stored = queries.list_daily_intakes(conn, "NS01", start, DEMO)
        rows = daily_rows(conn, engine, "NS01", start, DEMO)

    assert len(stored) == 7
    # 발주가 있는 날은 2026-11-28 ~ D0 (8일). 그 앞 날은 발주가 없어 빠진다.
    assert [r.on for r in rows] == [DEMO - timedelta(days=n) for n in range(7, -1, -1)]
    as_rows = [
        (
            r.on,
            r.energy_kcal,
            r.protein_g,
            r.energy_pct,
            r.protein_pct,
            r.recorded_meals,
            r.unrecorded_meals,
            r.npo_meals,
        )
        for r in rows[:-1]
    ]
    assert as_rows == [
        (
            s.on,
            s.energy_kcal,
            s.protein_g,
            s.energy_pct,
            s.protein_pct,
            s.recorded_meals,
            s.unrecorded_meals,
            s.npo_meals,
        )
        for s in stored
    ]
    assert all(r.target == fake_target for r in rows)


def test_daily_rows_target_is_engine_target_of_each_day(service_db: Path) -> None:
    engine = DayTargetEngine()
    start = DEMO - timedelta(days=2)
    with connect(service_db) as conn:
        rows = daily_rows(conn, engine, "NS03", start, DEMO)
        patient = queries.get_patient(conn, "NS03")
        history = queries.get_patient_history(conn, "NS03")

    assert [r.target for r in rows] == [
        DailyTarget(1000.0 + d.day, 40.0 + d.day, TargetSource.TEAM_SET)
        for d in (start, start + timedelta(days=1), DEMO)
    ]
    assert patient is not None
    profile, targets, weights, _ = engine.target_calls[0]
    assert profile == PatientProfile(sex=patient.sex, birth_year=patient.birth_year)
    assert targets == tuple(
        TargetRecord(t.effective_from, t.energy_kcal, t.protein_g, t.source)
        for t in history.targets
    )
    assert weights == tuple(WeightRecord(w.measured_on, w.weight_kg) for w in history.weights)
    # 저장된 행이 있는 날은 엔진으로 다시 계산하지 않는다. D0만 계산한다.
    assert [on for on, _ in engine.intake_calls] == [DEMO]


def test_daily_rows_computed_day_passes_meals_in_meal_order(service_db: Path) -> None:
    engine = DayTargetEngine()
    with connect(service_db) as conn:
        daily_rows(conn, engine, "NS01", DEMO, DEMO)
        orders = queries.list_meal_orders(conn, "NS01", DEMO, DEMO)

    assert engine.intake_calls == [
        (
            DEMO,
            tuple(
                MealRecord(
                    o.meal, o.order_status, o.record_status, o.energy_kcal_est, o.protein_g_est
                )
                for o in orders
            ),
        )
    ]
    assert [m.meal.value for m in engine.intake_calls[0][1]] == ["breakfast", "lunch", "dinner"]


def test_daily_rows_does_not_write_daily_intakes(
    service_db: Path, engine: FakeNutritionEngine
) -> None:
    with connect(service_db) as conn:
        before = _count(conn, "daily_intakes")
    with connect(service_db) as conn:
        daily_rows(conn, engine, "NS01", DEMO - timedelta(days=59), DEMO)
        intake_summary(conn, engine, "NS02", 14, DEMO)
    with connect(service_db) as conn:
        assert _count(conn, "daily_intakes") == before


def _daily_row(conn: sqlite3.Connection, day: str, **overrides: object) -> None:
    row = {
        "patient_id": "NS07",
        "date": day,
        "energy_kcal": 900.0,
        "protein_g": 30.0,
        "energy_pct": 60.0,
        "protein_pct": 54.5,
        "recorded_meals": 2,
        "unrecorded_meals": 1,
        "npo_meals": 0,
    }
    insert_row(conn, "daily_intakes", {**row, **overrides})


def test_daily_rows_skips_days_without_orders_even_with_stored_row(
    db_path: Path, engine: FakeNutritionEngine
) -> None:
    with connect(db_path) as conn:
        insert_patient(conn)
        insert_meal_plan(conn)  # 2026-11-23 점심
        insert_meal_order(conn)
        _daily_row(conn, "2026-11-23")
        _daily_row(conn, "2026-11-24")  # 발주 없는 날의 행
        rows = daily_rows(conn, engine, "NS07", date(2026, 11, 22), date(2026, 11, 25))

    assert [r.on for r in rows] == [date(2026, 11, 23)]
    assert rows[0].energy_kcal == pytest.approx(900.0)
    assert rows[0].recorded_meals == 2


def test_daily_rows_ignores_other_patients_orders(
    db_path: Path, engine: FakeNutritionEngine
) -> None:
    with connect(db_path) as conn:
        insert_patient(conn)
        insert_patient(conn, patient_id="NS08", display_name="NS08")
        insert_meal_plan(conn)
        insert_meal_order(conn, meal_order_id="NS08_lunch", patient_id="NS08")
        rows = daily_rows(conn, engine, "NS07", date(2026, 11, 22), date(2026, 11, 25))

    assert rows == ()


def test_daily_rows_computed_day_without_stored_row(
    db_path: Path, engine: FakeNutritionEngine
) -> None:
    with connect(db_path) as conn:
        insert_patient(conn)
        insert_meal_plan(conn)
        insert_meal_order(conn, energy_kcal_est=500.0, protein_g_est=20.0)
        rows = daily_rows(conn, engine, "NS07", date(2026, 11, 23), date(2026, 11, 23))

    assert len(rows) == 1
    assert rows[0].recorded_meals == 1
    assert rows[0].energy_kcal == pytest.approx(500.0)
    assert rows[0].energy_pct == pytest.approx(500.0 * 3 / 1500.0 * 100.0)


# 경고 ----------------------------------------------------------------------


def test_alert_to_result_parses_period_and_evidence() -> None:
    row = AlertRow(
        alert_id="A1",
        patient_id="NS07",
        evaluated_at="2026-11-23T00:00:00",
        level=AlertLevel.WARNING,
        basis_period="2026-11-17~2026-11-23",
        basis_values=(NutrientEvidence(Nutrient.PROTEIN, 45.0, 5),),
        nutrients=(Nutrient.PROTEIN,),
        unrecorded_meals=2,
    )

    result = alert_to_result(row)

    assert result.level is AlertLevel.WARNING
    assert result.nutrients == (Nutrient.PROTEIN,)
    assert result.period_start == date(2026, 11, 17)
    assert result.period_end == date(2026, 11, 23)
    assert result.evidence == (NutrientEvidence(Nutrient.PROTEIN, 45.0, 5),)
    assert result.unrecorded_meals == 2


def test_alert_to_result_without_period_has_no_dates() -> None:
    row = AlertRow("A1", "NS07", "2026-11-23T00:00:00", AlertLevel.NONE, None, (), (), 0)

    result = alert_to_result(row)

    assert (result.period_start, result.period_end) == (None, None)


def test_latest_alert_picks_latest_on_or_before_day(db_path: Path) -> None:
    with connect(db_path) as conn:
        insert_patient(conn)
        insert_alert(conn, alert_id="A1", evaluated_at="2026-11-22T23:59:59", level="warning")
        insert_alert(conn, alert_id="A2", evaluated_at="2026-11-23T09:00:00", level="none")
        insert_alert(conn, alert_id="A3", evaluated_at="2026-11-23T09:00:00", level="caution")
        insert_alert(conn, alert_id="A4", evaluated_at="2026-11-24T00:00:00", level="warning")

        on_23 = latest_alert(conn, "NS07", date(2026, 11, 23))
        on_22 = latest_alert(conn, "NS07", date(2026, 11, 22))
        on_21 = latest_alert(conn, "NS07", date(2026, 11, 21))

    assert on_23 is not None and on_23.alert_id == "A3"
    assert on_22 is not None and on_22.alert_id == "A1"
    assert on_21 is None


# intake_summary ------------------------------------------------------------


def test_intake_summary_combines_daily_alert_and_left_menus(
    service_db: Path, engine: FakeNutritionEngine
) -> None:
    on = DEMO - timedelta(days=1)
    with connect(service_db) as conn:
        insert_alert(
            conn,
            alert_id="later",
            patient_id="NS03",
            evaluated_at=f"{DEMO.isoformat()}T09:00:00",
            level="warning",
        )
        summary = intake_summary(conn, engine, "NS03", 14, on)
        start = on - timedelta(days=13)
        expected_daily = daily_rows(conn, engine, "NS03", start, on)
        expected_menus = left_menus(conn, "NS03", start, on)

    assert (summary.patient_id, summary.period_start, summary.period_end) == ("NS03", start, on)
    assert summary.daily == expected_daily
    assert summary.frequently_left_menus == expected_menus
    assert summary.frequently_left_menus != ()
    # 시드의 D-1 판정(none)이 on 이하 최신이다. 시연일 판정은 on 뒤라 쓰지 않는다.
    assert summary.alert is not None
    assert summary.alert.level is AlertLevel.NONE


def test_intake_summary_without_judgement_has_no_alert(
    db_path: Path, engine: FakeNutritionEngine
) -> None:
    with connect(db_path) as conn:
        insert_patient(conn)
        summary = intake_summary(conn, engine, "NS07", 1, date(2026, 11, 23))

    assert summary.alert is None
    assert summary.period_start == summary.period_end == date(2026, 11, 23)
    assert summary.daily == ()


def test_intake_summary_unknown_patient_raises(db_path: Path, engine: FakeNutritionEngine) -> None:
    with connect(db_path) as conn, pytest.raises(PatientNotFoundError):
        intake_summary(conn, engine, "NS99", 14, date(2026, 11, 23))


@pytest.mark.parametrize("days", [0, -1])
def test_intake_summary_days_below_one_raises(
    service_db: Path, engine: FakeNutritionEngine, days: int
) -> None:
    with connect(service_db) as conn, pytest.raises(ValueError):
        intake_summary(conn, engine, "NS01", days, DEMO)


# list_patients_with_alert --------------------------------------------------


def test_list_patients_with_alert_seed_has_ten_patients_in_order(service_db: Path) -> None:
    with connect(service_db) as conn:
        entries = list_patients_with_alert(conn)

    assert [e.patient_id for e in entries] == [f"NS{n:02d}" for n in range(1, 11)]
    assert all(e.alert_level is AlertLevel.NONE and e.alert_nutrients == () for e in entries)
    assert entries[0].display_name and entries[0].room


def test_list_patients_with_alert_uses_latest_judgement_up_to_demo_date(service_db: Path) -> None:
    with connect(service_db) as conn:
        insert_alert(
            conn,
            alert_id="ns03-d0",
            patient_id="NS03",
            evaluated_at=f"{DEMO.isoformat()}T09:00:00",
            level="caution",
            nutrients='["energy", "protein"]',
        )
        insert_alert(
            conn,
            alert_id="ns04-future",
            patient_id="NS04",
            evaluated_at=f"{(DEMO + timedelta(days=1)).isoformat()}T09:00:00",
            level="warning",
        )
        entries = {e.patient_id: e for e in list_patients_with_alert(conn)}

    assert entries["NS03"].alert_level is AlertLevel.CAUTION
    assert entries["NS03"].alert_nutrients == (Nutrient.ENERGY, Nutrient.PROTEIN)
    assert entries["NS04"].alert_level is AlertLevel.NONE


def test_list_patients_with_alert_without_judgement_is_none(db_path: Path) -> None:
    with connect(db_path) as conn:
        insert_row(conn, "seed_meta", {"key": "demo_date", "value": "2026-11-23"})
        insert_patient(conn)
        entries = list_patients_with_alert(conn)

    assert len(entries) == 1
    assert entries[0].alert_level is None
    assert entries[0].alert_nutrients == ()
