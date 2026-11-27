"""외부 호출 없이 계약 불변 조건만 지키는 `FakeNutritionEngine`.

실행 중 더미 구현이자 계약 테스트 대상이다. 판단 알고리즘 트랙의 기준 구현이 아니다.
`daily_target`·`evaluate_alert`는 입력과 무관한 고정값을 돌려주고, `meal_nutrients`·
`daily_intake`는 계약(미등록 칸 `ValueError`, `incomplete`, 기록 0끼 → `None`)을 지키는
최소 계산만 한다.
"""

from __future__ import annotations

from datetime import date

from app.intake.types import SlotStatus
from app.nutrition.types import (
    AlertLevel,
    AlertResult,
    AlertRules,
    DailyIntake,
    DailyTarget,
    MealNutrients,
    MealRecord,
    OrderStatus,
    PatientProfile,
    RecordStatus,
    SlotIntake,
    SlotNutrition,
    TargetRecord,
    TargetSource,
    WeightRecord,
)

FAKE_TARGET_ENERGY_KCAL = 1500.0
FAKE_TARGET_PROTEIN_G = 55.0
MEALS_PER_DAY = 3
PCT_SCALE = 100.0

# 발주된 끼니 중 평균에서 빼고 미기록으로 세는 기록 상태 (`pending`은 아직 집계하지 않는다)
_UNRECORDED_STATUSES = frozenset(
    {RecordStatus.NOT_RECORDED, RecordStatus.NOT_DETERMINABLE, RecordStatus.FAILED}
)


class FakeNutritionEngine:
    """고정 목표·고정 `none` 판정과 최소 계산만 하는 판단 알고리즘 더미."""

    def meal_nutrients(
        self,
        slot_intakes: tuple[SlotIntake, ...],
        plan_slots: tuple[SlotNutrition, ...],
    ) -> MealNutrients:
        plan_by_slot = {slot.slot_id: slot for slot in plan_slots}
        unknown_ids = [i.slot_id for i in slot_intakes if i.slot_id not in plan_by_slot]
        if unknown_ids:
            raise ValueError(f"배식 계획에 없는 칸: {', '.join(unknown_ids)}")

        estimated = [
            (intake.intake_fraction_est, plan_by_slot[intake.slot_id])
            for intake in slot_intakes
            if intake.status == SlotStatus.ESTIMATED and intake.intake_fraction_est is not None
        ]
        return MealNutrients(
            energy_kcal_est=sum(fraction * slot.energy_kcal for fraction, slot in estimated),
            protein_g_est=sum(fraction * slot.protein_g for fraction, slot in estimated),
            incomplete=len(estimated) < len(slot_intakes),
        )

    def daily_target(
        self,
        profile: PatientProfile,
        targets: tuple[TargetRecord, ...],
        weights: tuple[WeightRecord, ...],
        on: date,
    ) -> DailyTarget:
        return DailyTarget(
            energy_kcal=FAKE_TARGET_ENERGY_KCAL,
            protein_g=FAKE_TARGET_PROTEIN_G,
            source=TargetSource.KDRI,
        )

    def daily_intake(
        self,
        on: date,
        meals: tuple[MealRecord, ...],
        target: DailyTarget,
    ) -> DailyIntake:
        ordered = [meal for meal in meals if meal.order_status == OrderStatus.ORDERED]
        recorded = [meal for meal in ordered if meal.record_status == RecordStatus.RECORDED]
        unrecorded_count = sum(1 for meal in ordered if meal.record_status in _UNRECORDED_STATUSES)
        npo_count = len(meals) - len(ordered)

        energy_kcal: float | None = None
        protein_g: float | None = None
        energy_pct: float | None = None
        protein_pct: float | None = None
        if recorded:
            # recorded 끼니의 추정치 None을 0으로 보는 것은 더미 전용 단순화다 (데이터 모델상 없음)
            energy_kcal = sum(meal.energy_kcal_est or 0.0 for meal in recorded)
            protein_g = sum(meal.protein_g_est or 0.0 for meal in recorded)
            energy_pct = _scaled_pct(energy_kcal, len(recorded), target.energy_kcal)
            protein_pct = _scaled_pct(protein_g, len(recorded), target.protein_g)

        return DailyIntake(
            on=on,
            energy_kcal=energy_kcal,
            protein_g=protein_g,
            energy_pct=energy_pct,
            protein_pct=protein_pct,
            recorded_meals=len(recorded),
            unrecorded_meals=unrecorded_count,
            npo_meals=npo_count,
            target=target,
        )

    def evaluate_alert(
        self,
        history: tuple[DailyIntake, ...],
        rules: AlertRules,
        on: date,
    ) -> AlertResult:
        return AlertResult(
            level=AlertLevel.NONE,
            nutrients=(),
            period_start=None,
            period_end=None,
            evidence=(),
            unrecorded_meals=sum(day.unrecorded_meals for day in history),
        )


def _scaled_pct(total: float, recorded_count: int, daily_target: float) -> float:
    """기록된 끼니 합계를 3끼로 환산한 목표 대비 %."""
    return total * MEALS_PER_DAY / recorded_count / daily_target * PCT_SCALE
