"""`NutritionEngine` 계약 테스트 기반 클래스.

구현별 하위 클래스(`Test*`)는 `engine` 픽스처만 정의한다. 나머지 입력 픽스처는
기본값을 제공하며 하위 클래스가 덮어쓸 수 있다.

계약은 타입·열거값·부호·결측 규칙·미등록 칸 `ValueError`·입력 불변까지만 본다.
목표 우선순위, 3끼 환산식, 경고 임계값은 판단 알고리즘 트랙의 자체 테스트로 검증한다.
"""

from __future__ import annotations

import copy
from datetime import date, timedelta

import pytest

from app.intake.types import SlotStatus
from app.nutrition.types import (
    AlertLevel,
    AlertResult,
    AlertRules,
    DailyIntake,
    DailyTarget,
    MealNutrients,
    MealRecord,
    MealType,
    Nutrient,
    NutrientEvidence,
    NutritionEngine,
    OrderStatus,
    PatientProfile,
    RecordStatus,
    Sex,
    SlotIntake,
    SlotNutrition,
    TargetRecord,
    TargetSource,
    WeightRecord,
)

REFERENCE_DAY = date(2026, 11, 23)
HISTORY_DAYS = 7

SAMPLE_TARGET = DailyTarget(energy_kcal=1500.0, protein_g=55.0, source=TargetSource.KDRI)


def build_plan_slots() -> tuple[SlotNutrition, ...]:
    """표준 배식량 기준 영양값을 가진 칸 3개."""
    return (
        SlotNutrition(slot_id="slot_1", energy_kcal=300.0, protein_g=6.0),
        SlotNutrition(slot_id="slot_2", energy_kcal=50.0, protein_g=3.0),
        SlotNutrition(slot_id="slot_3", energy_kcal=90.0, protein_g=10.0),
    )


def build_daily_intake(
    on: date,
    *,
    energy_kcal: float | None,
    protein_g: float | None,
    energy_pct: float | None,
    protein_pct: float | None,
    recorded_meals: int,
    unrecorded_meals: int = 0,
    npo_meals: int = 0,
    target: DailyTarget = SAMPLE_TARGET,
) -> DailyIntake:
    """`DailyIntake` 한 행을 만든다 (테스트 입력용)."""
    return DailyIntake(
        on=on,
        energy_kcal=energy_kcal,
        protein_g=protein_g,
        energy_pct=energy_pct,
        protein_pct=protein_pct,
        recorded_meals=recorded_meals,
        unrecorded_meals=unrecorded_meals,
        npo_meals=npo_meals,
        target=target,
    )


def build_intake_history(on: date) -> tuple[DailyIntake, ...]:
    """기준일까지 7일 이력. 미기록인 날(결측 %)과 금식이 섞인 날을 포함한다.

    모든 행은 `SAMPLE_TARGET`(1,500 kcal·55 g)과 3끼 환산식
    (합계 × 3 ÷ 기록 끼니 수 ÷ 목표 × 100)에 맞는 값이다.
    """
    first_day = on - timedelta(days=HISTORY_DAYS - 1)
    history: list[DailyIntake] = []
    for offset in range(HISTORY_DAYS):
        day = first_day + timedelta(days=offset)
        if offset == 2:  # 전부 미기록인 날
            row = build_daily_intake(
                day,
                energy_kcal=None,
                protein_g=None,
                energy_pct=None,
                protein_pct=None,
                recorded_meals=0,
                unrecorded_meals=3,
            )
        elif offset == 4:  # 2끼 기록 + 금식 1끼: 900 × 3 ÷ 2 ÷ 1,500 × 100 = 90
            row = build_daily_intake(
                day,
                energy_kcal=900.0,
                protein_g=33.0,
                energy_pct=90.0,
                protein_pct=90.0,
                recorded_meals=2,
                npo_meals=1,
            )
        else:  # 3끼 기록: 1,350 ÷ 1,500 × 100 = 90, 49.5 ÷ 55 × 100 = 90
            row = build_daily_intake(
                day,
                energy_kcal=1350.0,
                protein_g=49.5,
                energy_pct=90.0,
                protein_pct=90.0,
                recorded_meals=3,
            )
        history.append(row)
    return tuple(history)


def build_meal_record(
    order_status: OrderStatus,
    record_status: RecordStatus,
    energy_kcal_est: float | None = None,
    protein_g_est: float | None = None,
    meal: MealType = MealType.BREAKFAST,
) -> MealRecord:
    """끼니 기록 하나를 만든다 (테스트 입력용)."""
    return MealRecord(
        meal=meal,
        order_status=order_status,
        record_status=record_status,
        energy_kcal_est=energy_kcal_est,
        protein_g_est=protein_g_est,
    )


def build_complete_slot_intakes() -> tuple[SlotIntake, ...]:
    """판단 불가 칸이 없는 칸별 섭취 (`build_plan_slots`의 칸 3개)."""
    return (
        SlotIntake(slot_id="slot_1", intake_fraction_est=1.0, status=SlotStatus.ESTIMATED),
        SlotIntake(slot_id="slot_2", intake_fraction_est=0.5, status=SlotStatus.ESTIMATED),
        SlotIntake(slot_id="slot_3", intake_fraction_est=0.0, status=SlotStatus.ESTIMATED),
    )


def build_incomplete_slot_intakes() -> tuple[SlotIntake, ...]:
    """판단 불가 칸 1개(`slot_2`)를 포함한 칸별 섭취."""
    return (
        SlotIntake(slot_id="slot_1", intake_fraction_est=0.8, status=SlotStatus.ESTIMATED),
        SlotIntake(slot_id="slot_2", intake_fraction_est=None, status=SlotStatus.NOT_DETERMINABLE),
        SlotIntake(slot_id="slot_3", intake_fraction_est=0.3, status=SlotStatus.ESTIMATED),
    )


def build_meals_with_recorded() -> tuple[MealRecord, ...]:
    """기록된 아침(600 kcal·20 g) 1끼, 미기록 점심 1끼, 금식 저녁 1끼."""
    return (
        build_meal_record(OrderStatus.ORDERED, RecordStatus.RECORDED, 600.0, 20.0),
        build_meal_record(OrderStatus.ORDERED, RecordStatus.NOT_RECORDED, meal=MealType.LUNCH),
        build_meal_record(OrderStatus.NPO, RecordStatus.NOT_RECORDED, meal=MealType.DINNER),
    )


class NutritionEngineContract:
    """모든 `NutritionEngine` 구현이 지켜야 하는 불변 조건."""

    # ---- 하위 클래스가 정의할 픽스처 ----

    @pytest.fixture
    def engine(self) -> NutritionEngine:
        """하위 클래스가 검증할 구현을 돌려준다."""
        raise NotImplementedError("하위 클래스가 engine 픽스처를 정의해야 한다")

    # ---- 기본 입력 픽스처 (덮어쓰기 가능) ----

    @pytest.fixture
    def on(self) -> date:
        return REFERENCE_DAY

    @pytest.fixture
    def plan_slots(self) -> tuple[SlotNutrition, ...]:
        return build_plan_slots()

    @pytest.fixture
    def complete_slot_intakes(self) -> tuple[SlotIntake, ...]:
        return build_complete_slot_intakes()

    @pytest.fixture
    def incomplete_slot_intakes(self) -> tuple[SlotIntake, ...]:
        return build_incomplete_slot_intakes()

    @pytest.fixture
    def unknown_slot_intakes(self) -> tuple[SlotIntake, ...]:
        """`plan_slots`에 없는 칸(`slot_9`)을 포함한 칸별 섭취."""
        return (
            SlotIntake(slot_id="slot_1", intake_fraction_est=1.0, status=SlotStatus.ESTIMATED),
            SlotIntake(slot_id="slot_9", intake_fraction_est=0.5, status=SlotStatus.ESTIMATED),
        )

    @pytest.fixture
    def profile(self) -> PatientProfile:
        return PatientProfile(sex=Sex.FEMALE, birth_year=1940)

    @pytest.fixture
    def target_records(self) -> tuple[TargetRecord, ...]:
        return (
            TargetRecord(
                effective_from=date(2026, 11, 1),
                energy_kcal=1400.0,
                protein_g=50.0,
                source=TargetSource.TEAM_SET,
            ),
        )

    @pytest.fixture
    def weight_records(self) -> tuple[WeightRecord, ...]:
        return (WeightRecord(measured_on=date(2026, 11, 10), weight_kg=48.5),)

    @pytest.fixture
    def daily_target_value(self) -> DailyTarget:
        return SAMPLE_TARGET

    @pytest.fixture
    def meals_with_recorded(self) -> tuple[MealRecord, ...]:
        """기록된 끼니 1개, 미기록 1개, 금식 1개."""
        return build_meals_with_recorded()

    @pytest.fixture
    def meals_all_unrecorded(self) -> tuple[MealRecord, ...]:
        """전부 미기록인 날 (미기록·판단 불가·분석 실패)."""
        return (
            build_meal_record(OrderStatus.ORDERED, RecordStatus.NOT_RECORDED),
            build_meal_record(
                OrderStatus.ORDERED, RecordStatus.NOT_DETERMINABLE, meal=MealType.LUNCH
            ),
            build_meal_record(OrderStatus.ORDERED, RecordStatus.FAILED, meal=MealType.DINNER),
        )

    @pytest.fixture
    def meals_all_npo(self) -> tuple[MealRecord, ...]:
        """전부 금식·취소인 날."""
        return (
            build_meal_record(OrderStatus.NPO, RecordStatus.NOT_RECORDED),
            build_meal_record(OrderStatus.NPO, RecordStatus.NOT_RECORDED, meal=MealType.LUNCH),
            build_meal_record(
                OrderStatus.CANCELLED, RecordStatus.NOT_RECORDED, meal=MealType.DINNER
            ),
        )

    @pytest.fixture
    def intake_history(self, on: date) -> tuple[DailyIntake, ...]:
        return build_intake_history(on)

    @pytest.fixture
    def alert_rules(self) -> AlertRules:
        return AlertRules()

    # ---- meal_nutrients ----

    @pytest.mark.parametrize("intakes_name", ["complete_slot_intakes", "incomplete_slot_intakes"])
    def test_meal_nutrients_returns_typed_non_negative_amounts(
        self,
        request: pytest.FixtureRequest,
        engine: NutritionEngine,
        plan_slots: tuple[SlotNutrition, ...],
        intakes_name: str,
    ) -> None:
        slot_intakes = request.getfixturevalue(intakes_name)

        result = engine.meal_nutrients(slot_intakes, plan_slots)

        assert isinstance(result, MealNutrients)
        assert isinstance(result.incomplete, bool)
        assert result.energy_kcal_est >= 0.0
        assert result.protein_g_est >= 0.0

    def test_meal_nutrients_with_not_determinable_slot_is_incomplete(
        self,
        engine: NutritionEngine,
        incomplete_slot_intakes: tuple[SlotIntake, ...],
        plan_slots: tuple[SlotNutrition, ...],
    ) -> None:
        result = engine.meal_nutrients(incomplete_slot_intakes, plan_slots)

        assert result.incomplete is True

    def test_meal_nutrients_unknown_slot_raises_value_error(
        self,
        engine: NutritionEngine,
        unknown_slot_intakes: tuple[SlotIntake, ...],
        plan_slots: tuple[SlotNutrition, ...],
    ) -> None:
        with pytest.raises(ValueError):
            engine.meal_nutrients(unknown_slot_intakes, plan_slots)

    # ---- daily_target ----

    @pytest.mark.parametrize("with_history", [True, False], ids=["with_history", "no_history"])
    def test_daily_target_is_positive_with_known_source(
        self,
        engine: NutritionEngine,
        profile: PatientProfile,
        target_records: tuple[TargetRecord, ...],
        weight_records: tuple[WeightRecord, ...],
        on: date,
        with_history: bool,
    ) -> None:
        targets = target_records if with_history else ()
        weights = weight_records if with_history else ()

        result = engine.daily_target(profile, targets, weights, on)

        assert isinstance(result, DailyTarget)
        assert isinstance(result.source, TargetSource)
        assert result.energy_kcal > 0.0
        assert result.protein_g > 0.0

    # ---- daily_intake ----

    @pytest.mark.parametrize(
        "meals_name", ["meals_with_recorded", "meals_all_unrecorded", "meals_all_npo"]
    )
    def test_daily_intake_returns_typed_non_negative_counts(
        self,
        request: pytest.FixtureRequest,
        engine: NutritionEngine,
        daily_target_value: DailyTarget,
        on: date,
        meals_name: str,
    ) -> None:
        meals = request.getfixturevalue(meals_name)

        result = engine.daily_intake(on, meals, daily_target_value)

        assert isinstance(result, DailyIntake)
        assert isinstance(result.target, DailyTarget)
        assert result.recorded_meals >= 0
        assert result.unrecorded_meals >= 0
        assert result.npo_meals >= 0

    @pytest.mark.parametrize("meals_name", ["meals_all_unrecorded", "meals_all_npo"])
    def test_daily_intake_without_recorded_meal_has_no_amounts(
        self,
        request: pytest.FixtureRequest,
        engine: NutritionEngine,
        daily_target_value: DailyTarget,
        on: date,
        meals_name: str,
    ) -> None:
        meals = request.getfixturevalue(meals_name)

        result = engine.daily_intake(on, meals, daily_target_value)

        assert result.energy_kcal is None
        assert result.protein_g is None
        assert result.energy_pct is None
        assert result.protein_pct is None

    def test_daily_intake_with_recorded_meal_has_non_negative_pct(
        self,
        engine: NutritionEngine,
        meals_with_recorded: tuple[MealRecord, ...],
        daily_target_value: DailyTarget,
        on: date,
    ) -> None:
        result = engine.daily_intake(on, meals_with_recorded, daily_target_value)

        assert result.energy_kcal is not None
        assert result.protein_g is not None
        assert result.energy_pct is not None
        assert result.protein_pct is not None
        assert result.energy_kcal >= 0.0
        assert result.protein_g >= 0.0
        assert result.energy_pct >= 0.0  # 상한 없음 (100 초과 가능)
        assert result.protein_pct >= 0.0

    # ---- evaluate_alert ----

    def test_evaluate_alert_returns_typed_result(
        self,
        engine: NutritionEngine,
        intake_history: tuple[DailyIntake, ...],
        alert_rules: AlertRules,
        on: date,
    ) -> None:
        result = engine.evaluate_alert(intake_history, alert_rules, on)

        assert isinstance(result, AlertResult)
        assert isinstance(result.level, AlertLevel)
        assert isinstance(result.nutrients, tuple)
        assert all(isinstance(nutrient, Nutrient) for nutrient in result.nutrients)
        assert isinstance(result.evidence, tuple)
        assert all(isinstance(item, NutrientEvidence) for item in result.evidence)
        assert all(isinstance(item.nutrient, Nutrient) for item in result.evidence)
        assert result.unrecorded_meals >= 0

    def test_evaluate_alert_none_level_has_no_nutrients(
        self,
        engine: NutritionEngine,
        intake_history: tuple[DailyIntake, ...],
        alert_rules: AlertRules,
        on: date,
    ) -> None:
        result = engine.evaluate_alert(intake_history, alert_rules, on)

        if result.level == AlertLevel.NONE:
            assert result.nutrients == ()

    # ---- 입력 불변 ----

    def test_meal_nutrients_does_not_mutate_inputs(
        self,
        engine: NutritionEngine,
        incomplete_slot_intakes: tuple[SlotIntake, ...],
        plan_slots: tuple[SlotNutrition, ...],
    ) -> None:
        before = copy.deepcopy((incomplete_slot_intakes, plan_slots))

        engine.meal_nutrients(incomplete_slot_intakes, plan_slots)

        assert (incomplete_slot_intakes, plan_slots) == before

    def test_daily_target_does_not_mutate_inputs(
        self,
        engine: NutritionEngine,
        profile: PatientProfile,
        target_records: tuple[TargetRecord, ...],
        weight_records: tuple[WeightRecord, ...],
        on: date,
    ) -> None:
        before = copy.deepcopy((profile, target_records, weight_records, on))

        engine.daily_target(profile, target_records, weight_records, on)

        assert (profile, target_records, weight_records, on) == before

    def test_daily_intake_does_not_mutate_inputs(
        self,
        engine: NutritionEngine,
        meals_with_recorded: tuple[MealRecord, ...],
        daily_target_value: DailyTarget,
        on: date,
    ) -> None:
        before = copy.deepcopy((on, meals_with_recorded, daily_target_value))

        engine.daily_intake(on, meals_with_recorded, daily_target_value)

        assert (on, meals_with_recorded, daily_target_value) == before

    def test_evaluate_alert_does_not_mutate_inputs(
        self,
        engine: NutritionEngine,
        intake_history: tuple[DailyIntake, ...],
        alert_rules: AlertRules,
        on: date,
    ) -> None:
        before = copy.deepcopy((intake_history, alert_rules, on))

        engine.evaluate_alert(intake_history, alert_rules, on)

        assert (intake_history, alert_rules, on) == before
