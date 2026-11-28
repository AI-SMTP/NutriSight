"""환자 요약 `patient_detail`과 섭취 추이 `intake_trend` 테스트 (스펙 3.3 응답 모델)."""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pytest

from app.nutrition.fake import FakeNutritionEngine
from app.nutrition.types import (
    DailyTarget,
    PatientProfile,
    Sex,
    TargetRecord,
    TargetSource,
    WeightRecord,
)
from app.services.patients import (
    PrescriptionMark,
    TargetView,
    WeightChange,
    daily_rows,
    intake_trend,
    patient_detail,
)
from app.services.ports import PatientNotFoundError
from app.storage.db import connect
from app.storage.records import AssessmentRow, WeightRow
from tests.storage.demo import DEMO
from tests.storage.rows import insert_assessment, insert_patient, insert_row


class TeamSetEngine(FakeNutritionEngine):
    """항상 `team_set` 목표를 주는 엔진."""

    def daily_target(
        self,
        profile: PatientProfile,
        targets: tuple[TargetRecord, ...],
        weights: tuple[WeightRecord, ...],
        on: date,
    ) -> DailyTarget:
        return DailyTarget(1700.0, 60.0, TargetSource.TEAM_SET)


def _weight(conn: sqlite3.Connection, patient_id: str, day: date, kg: float) -> None:
    insert_row(
        conn,
        "patient_weights",
        {"patient_id": patient_id, "measured_on": day.isoformat(), "weight_kg": kg},
    )


def _target(conn: sqlite3.Connection, day: date, source: str = "team_set") -> None:
    insert_row(
        conn,
        "patient_targets",
        {
            "patient_id": "NS03",
            "effective_from": day.isoformat(),
            "energy_kcal": 1700.0,
            "protein_g": 60.0,
            "source": source,
            "note": None,
        },
    )


def _empty_patient_db(db_path: Path, **patient: object) -> None:
    with connect(db_path) as conn:
        insert_row(conn, "seed_meta", {"key": "demo_date", "value": DEMO.isoformat()})
        insert_patient(conn, **patient)


# patient_detail ------------------------------------------------------------


def test_patient_detail_seed_basic_fields_and_weight(
    service_db: Path, engine: FakeNutritionEngine, fake_target: DailyTarget
) -> None:
    with connect(service_db) as conn:
        detail = patient_detail(conn, engine, "NS03")

    assert detail.patient_id == "NS03"
    assert detail.sex is Sex.MALE
    assert detail.conditions == ("만성폐쇄성폐질환",)
    assert detail.ckd_dialysis == "none"
    assert detail.age == DEMO.year - 1945
    assert detail.height_cm == pytest.approx(163.0)
    assert detail.latest_weight == WeightRow(date(2026, 11, 28), 56.0)
    # D-30(11-05) 이전 가장 가까운 측정은 10-28의 60 kg이다.
    assert detail.weight_change_30d == WeightChange(
        kg=pytest.approx(-4.0), pct=pytest.approx(-4.0 / 60.0 * 100.0)
    )
    assert detail.bmi == pytest.approx(56.0 / 1.63**2)
    assert detail.target == TargetView(
        fake_target.energy_kcal, fake_target.protein_g, fake_target.source, None
    )


def test_patient_detail_baseline_is_closest_on_or_before_thirty_days(
    service_db: Path, engine: FakeNutritionEngine
) -> None:
    with connect(service_db) as conn:
        _weight(conn, "NS03", DEMO - timedelta(days=30), 58.0)  # 포함 경계
        _weight(conn, "NS03", DEMO - timedelta(days=29), 70.0)  # 30일 안이라 기준이 아니다
        _weight(conn, "NS03", DEMO, 55.0)
        _weight(conn, "NS03", DEMO + timedelta(days=1), 99.0)  # 시연일 뒤는 쓰지 않는다
        detail = patient_detail(conn, engine, "NS03")

    assert detail.latest_weight == WeightRow(DEMO, 55.0)
    assert detail.weight_change_30d == WeightChange(
        kg=pytest.approx(-3.0), pct=pytest.approx(-3.0 / 58.0 * 100.0)
    )


def test_patient_detail_without_old_weight_has_no_change(
    db_path: Path, engine: FakeNutritionEngine
) -> None:
    _empty_patient_db(db_path)
    with connect(db_path) as conn:
        _weight(conn, "NS07", DEMO - timedelta(days=29), 50.0)
        detail = patient_detail(conn, engine, "NS07")

    assert detail.latest_weight == WeightRow(DEMO - timedelta(days=29), 50.0)
    assert detail.weight_change_30d is None
    assert detail.bmi == pytest.approx(50.0 / 1.54**2)


def test_patient_detail_without_weight_or_height_has_no_bmi(
    db_path: Path, engine: FakeNutritionEngine
) -> None:
    _empty_patient_db(db_path, height_cm=None)
    with connect(db_path) as conn:
        no_weight = patient_detail(conn, engine, "NS07")
        _weight(conn, "NS07", DEMO, 50.0)
        no_height = patient_detail(conn, engine, "NS07")

    assert no_weight.latest_weight is None
    assert no_weight.weight_change_30d is None
    assert no_weight.bmi is None
    assert no_height.bmi is None
    assert no_height.height_cm is None


def test_patient_detail_team_set_target_has_effective_from(service_db: Path) -> None:
    with connect(service_db) as conn:
        _target(conn, DEMO - timedelta(days=2))
        _target(conn, DEMO - timedelta(days=1), source="kdri")
        _target(conn, DEMO + timedelta(days=1))  # 아직 적용 전
        detail = patient_detail(conn, TeamSetEngine(), "NS03")

    assert detail.target == TargetView(
        1700.0, 60.0, TargetSource.TEAM_SET, DEMO - timedelta(days=2)
    )


def test_patient_detail_assessments_latest_per_kind_in_kind_order(
    service_db: Path, engine: FakeNutritionEngine
) -> None:
    with connect(service_db) as conn:
        insert_assessment(conn, patient_id="NS03", assessed_on="2026-11-20", kind="swallowing")
        insert_assessment(
            conn,
            patient_id="NS03",
            assessed_on="2026-12-03",
            kind="nutrition_screening",
            result="low_risk",
            score=None,
            note="재평가",
        )
        insert_assessment(
            conn, patient_id="NS03", assessed_on="2026-12-06", kind="nutrition_screening"
        )
        detail = patient_detail(conn, engine, "NS03")

    kinds = [a.kind for a in detail.assessments]
    assert kinds == sorted(kinds)
    assert kinds == [
        "appetite_assist",
        "nutrition_screening",
        "pressure_injury",
        "refeeding_risk",
        "swallowing",
    ]
    assert detail.assessments[1] == AssessmentRow(
        date(2026, 12, 3), "nutrition_screening", "low_risk", None, "재평가"
    )


def test_patient_detail_uses_demo_date_from_db(
    service_db: Path, engine: FakeNutritionEngine
) -> None:
    with connect(service_db) as conn:
        conn.execute("UPDATE seed_meta SET value = '2027-01-10' WHERE key = 'demo_date'")
        detail = patient_detail(conn, engine, "NS03")

    assert detail.age == 2027 - 1945


def test_patient_detail_unknown_patient_raises(
    service_db: Path, engine: FakeNutritionEngine
) -> None:
    with connect(service_db) as conn, pytest.raises(PatientNotFoundError):
        patient_detail(conn, engine, "NS99")


# intake_trend --------------------------------------------------------------


def _prescription(
    conn: sqlite3.Connection, prescription_id: str, confirmed_at: str, patient_id: str = "NS03"
) -> None:
    insert_row(
        conn,
        "prescriptions",
        {
            "prescription_id": prescription_id,
            "patient_id": patient_id,
            "recommendation_id": None,
            "items": "[]",
            "confirmed_at": confirmed_at,
            "status": "confirmed",
        },
    )


def test_intake_trend_period_days_and_prescriptions(
    service_db: Path, engine: FakeNutritionEngine
) -> None:
    start = DEMO - timedelta(days=13)
    with connect(service_db) as conn:
        _prescription(conn, "P-end", f"{DEMO.isoformat()}T23:59:59.000000")
        _prescription(conn, "P-start", f"{start.isoformat()}T00:00:00.000000")
        _prescription(conn, "P-before", "2026-11-21T23:59:59.000000")
        _prescription(conn, "P-after", "2026-12-06T00:00:00.000000")
        _prescription(conn, "P-other", "2026-12-01T10:00:00.000000", patient_id="NS04")
        trend = intake_trend(conn, engine, "NS03", 14)
        expected_days = daily_rows(conn, engine, "NS03", start, DEMO)

    assert (trend.patient_id, trend.period_start, trend.period_end) == ("NS03", start, DEMO)
    assert trend.days == expected_days
    assert trend.days[-1].on == DEMO
    assert trend.prescriptions == (
        PrescriptionMark("P-start", f"{start.isoformat()}T00:00:00.000000"),
        PrescriptionMark("P-end", f"{DEMO.isoformat()}T23:59:59.000000"),
    )


def test_intake_trend_ends_at_demo_date_from_db(
    service_db: Path, engine: FakeNutritionEngine
) -> None:
    with connect(service_db) as conn:
        conn.execute("UPDATE seed_meta SET value = '2026-12-03' WHERE key = 'demo_date'")
        trend = intake_trend(conn, engine, "NS01", 1)

    assert trend.period_start == trend.period_end == date(2026, 12, 3)
    assert [d.on for d in trend.days] == [date(2026, 12, 3)]
    assert trend.prescriptions == ()


def test_intake_trend_unknown_patient_raises(service_db: Path, engine: FakeNutritionEngine) -> None:
    with connect(service_db) as conn, pytest.raises(PatientNotFoundError):
        intake_trend(conn, engine, "NS99", 14)


def test_intake_trend_days_below_one_raises(service_db: Path, engine: FakeNutritionEngine) -> None:
    with connect(service_db) as conn, pytest.raises(ValueError):
        intake_trend(conn, engine, "NS01", 0)
