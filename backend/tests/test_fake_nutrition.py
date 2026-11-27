"""`FakeNutritionEngine`의 계약 테스트와 Fake 전용 동작 테스트."""

from __future__ import annotations

from datetime import date, timedelta
from enum import StrEnum

import pytest

from app.nutrition.fake import FakeNutritionEngine
from app.nutrition.types import (
    AlertLevel,
    AlertRules,
    DailyIntake,
    MealRecord,
    MealType,
    Nutrient,
    OrderStatus,
    PatientProfile,
    RecordStatus,
    Sex,
    SlotIntake,
    TargetRecord,
    TargetSource,
    WeightRecord,
)
from tests.contracts.nutrition import (
    REFERENCE_DAY,
    SAMPLE_TARGET,
    NutritionEngineContract,
    build_complete_slot_intakes,
    build_daily_intake,
    build_incomplete_slot_intakes,
    build_intake_history,
    build_meal_record,
    build_meals_with_recorded,
    build_plan_slots,
)


class TestFakeNutritionContract(NutritionEngineContract):
    @pytest.fixture
    def engine(self) -> FakeNutritionEngine:
        return FakeNutritionEngine()


@pytest.fixture
def engine() -> FakeNutritionEngine:
    return FakeNutritionEngine()


# ---- 타입 정의 ----


@pytest.mark.parametrize(
    ("enum_type", "expected_values"),
    [
        (Sex, ("female", "male")),
        (TargetSource, ("team_set", "espen_weight", "kdri")),
        (MealType, ("breakfast", "lunch", "dinner")),
        (OrderStatus, ("ordered", "npo", "cancelled")),
        (
            RecordStatus,
            ("not_recorded", "pending", "recorded", "not_determinable", "failed"),
        ),
        (AlertLevel, ("none", "caution", "warning")),
        (Nutrient, ("energy", "protein")),
    ],
)
def test_enum_values_match_data_model(
    enum_type: type[StrEnum], expected_values: tuple[str, ...]
) -> None:
    assert tuple(member.value for member in enum_type) == expected_values


def test_alert_rules_defaults() -> None:
    rules = AlertRules()

    assert rules.caution_avg_pct == pytest.approx(75.0)
    assert rules.caution_window_days == 7
    assert rules.warning_pct == pytest.approx(50.0)
    assert rules.warning_consecutive_days == 5


# ---- meal_nutrients: 최소 계산 ----


@pytest.mark.parametrize(
    ("slot_intakes", "expected_kcal", "expected_protein_g", "expected_incomplete"),
    [
        (build_complete_slot_intakes(), 325.0, 7.5, False),
        (build_incomplete_slot_intakes(), 267.0, 7.8, True),
        ((), 0.0, 0.0, False),
    ],
    ids=["complete", "incomplete", "empty"],
)
def test_meal_nutrients_sums_estimated_slots(
    engine: FakeNutritionEngine,
    slot_intakes: tuple[SlotIntake, ...],
    expected_kcal: float,
    expected_protein_g: float,
    expected_incomplete: bool,
) -> None:
    result = engine.meal_nutrients(slot_intakes, build_plan_slots())

    assert result.energy_kcal_est == pytest.approx(expected_kcal)
    assert result.protein_g_est == pytest.approx(expected_protein_g)
    assert result.incomplete is expected_incomplete


# ---- daily_target: 고정값 ----


@pytest.mark.parametrize(
    ("profile", "targets", "weights"),
    [
        (PatientProfile(Sex.FEMALE, 1940), (), ()),
        (
            PatientProfile(Sex.MALE, 1950),
            (TargetRecord(date(2026, 11, 1), 2000.0, 80.0, TargetSource.TEAM_SET),),
            (WeightRecord(date(2026, 11, 10), 70.0),),
        ),
    ],
    ids=["no_history", "team_set_and_weight"],
)
def test_daily_target_is_fixed_regardless_of_input(
    engine: FakeNutritionEngine,
    profile: PatientProfile,
    targets: tuple[TargetRecord, ...],
    weights: tuple[WeightRecord, ...],
) -> None:
    result = engine.daily_target(profile, targets, weights, REFERENCE_DAY)

    assert result.energy_kcal == pytest.approx(1500.0)
    assert result.protein_g == pytest.approx(55.0)
    assert result.source == TargetSource.KDRI


# ---- daily_intake: 최소 계산 ----


def test_daily_intake_scales_recorded_meals_to_three_meal_pct(
    engine: FakeNutritionEngine,
) -> None:
    meals = build_meals_with_recorded()

    result = engine.daily_intake(REFERENCE_DAY, meals, SAMPLE_TARGET)

    assert result.on == REFERENCE_DAY
    assert result.target == SAMPLE_TARGET
    assert result.energy_kcal == pytest.approx(600.0)
    assert result.protein_g == pytest.approx(20.0)
    assert result.energy_pct == pytest.approx(120.0)  # 600 × 3 ÷ 1,500 × 100
    assert result.protein_pct == pytest.approx(109.0909, rel=1e-4)
    assert (result.recorded_meals, result.unrecorded_meals, result.npo_meals) == (1, 1, 1)


@pytest.mark.parametrize(
    ("meal", "expected_counts"),
    [
        (build_meal_record(OrderStatus.ORDERED, RecordStatus.RECORDED, 400.0, 15.0), (1, 0, 0)),
        (build_meal_record(OrderStatus.ORDERED, RecordStatus.NOT_RECORDED), (0, 1, 0)),
        (build_meal_record(OrderStatus.ORDERED, RecordStatus.NOT_DETERMINABLE), (0, 1, 0)),
        (build_meal_record(OrderStatus.ORDERED, RecordStatus.FAILED), (0, 1, 0)),
        (build_meal_record(OrderStatus.ORDERED, RecordStatus.PENDING), (0, 0, 0)),
        (build_meal_record(OrderStatus.NPO, RecordStatus.NOT_RECORDED), (0, 0, 1)),
        (build_meal_record(OrderStatus.CANCELLED, RecordStatus.NOT_RECORDED), (0, 0, 1)),
    ],
    ids=["recorded", "not_recorded", "not_determinable", "failed", "pending", "npo", "cancelled"],
)
def test_daily_intake_counts_meals_by_status(
    engine: FakeNutritionEngine, meal: MealRecord, expected_counts: tuple[int, int, int]
) -> None:
    result = engine.daily_intake(REFERENCE_DAY, (meal,), SAMPLE_TARGET)

    assert (result.recorded_meals, result.unrecorded_meals, result.npo_meals) == expected_counts


# ---- evaluate_alert: 고정 none ----


def _low_history() -> tuple[DailyIntake, ...]:
    """섭취가 낮은 3일 이력. 각 행은 1,500 kcal·55 g 목표의 3끼 환산식과 맞는다."""
    return (
        build_daily_intake(  # 2끼 기록: 500 × 3 ÷ 2 ÷ 1,500 × 100 = 50, 11 g → 30
            REFERENCE_DAY - timedelta(days=2),
            energy_kcal=500.0,
            protein_g=11.0,
            energy_pct=50.0,
            protein_pct=30.0,
            recorded_meals=2,
            unrecorded_meals=1,
        ),
        build_daily_intake(  # 1끼 기록: 250 × 3 ÷ 1,500 × 100 = 50, 5.5 g → 30
            REFERENCE_DAY - timedelta(days=1),
            energy_kcal=250.0,
            protein_g=5.5,
            energy_pct=50.0,
            protein_pct=30.0,
            recorded_meals=1,
            unrecorded_meals=2,
        ),
        build_daily_intake(  # 전부 미기록
            REFERENCE_DAY,
            energy_kcal=None,
            protein_g=None,
            energy_pct=None,
            protein_pct=None,
            recorded_meals=0,
            unrecorded_meals=3,
        ),
    )


@pytest.mark.parametrize(
    ("history", "expected_unrecorded"),
    [((), 0), (build_intake_history(REFERENCE_DAY), 3), (_low_history(), 6)],
    ids=["empty", "contract_history", "low_history"],
)
def test_evaluate_alert_is_fixed_none(
    engine: FakeNutritionEngine,
    history: tuple[DailyIntake, ...],
    expected_unrecorded: int,
) -> None:
    result = engine.evaluate_alert(history, AlertRules(warning_pct=90.0), REFERENCE_DAY)

    assert result.level == AlertLevel.NONE
    assert result.nutrients == ()
    assert result.evidence == ()
    assert result.period_start is None
    assert result.period_end is None
    assert result.unrecorded_meals == expected_unrecorded
