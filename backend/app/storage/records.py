"""조회 함수가 돌려주는 레코드 (스펙 3.5).

모든 레코드는 frozen dataclass이고 컬렉션은 `tuple`이다. 필드 이름과 단위는
`docs/data-model.md`를 따르되, DB의 `date` 열은 `on`(`date` 타입)으로 담는다.
JSON 열은 파싱해서 담고, 열거값은 기존 `StrEnum`으로 바꾼다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

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


@dataclass(frozen=True)
class Patient:
    """환자 한 명 (`patients`). `conditions`는 JSON 배열을 파싱한 것이다."""

    patient_id: str
    display_name: str
    room: str | None
    sex: Sex
    birth_year: int
    height_cm: float | None
    default_diet_type: str
    conditions: tuple[str, ...]
    diet_restrictions: str
    ckd_dialysis: str  # none, ckd, dialysis
    observation_start: date
    data_source: str  # mock, upload


@dataclass(frozen=True)
class WeightRow:
    """체중 기록 한 행 (`patient_weights`)."""

    measured_on: date
    weight_kg: float


@dataclass(frozen=True)
class TargetRow:
    """목표 이력 한 행 (`patient_targets`)."""

    effective_from: date
    energy_kcal: float
    protein_g: float
    source: TargetSource
    note: str | None


@dataclass(frozen=True)
class AssessmentRow:
    """평가 기록 한 행 (`patient_assessments`)."""

    assessed_on: date
    kind: str  # mna_sf, nutrition_screening, swallowing, ...
    result: str | None
    score: float | None
    note: str | None


@dataclass(frozen=True)
class PatientHistory:
    """환자의 체중·목표·평가 이력. 각 컬렉션은 날짜 오름차순이다."""

    patient_id: str
    weights: tuple[WeightRow, ...]
    targets: tuple[TargetRow, ...]
    assessments: tuple[AssessmentRow, ...]


@dataclass(frozen=True)
class MealPlanSlot:
    """배식 계획의 칸 하나 (`meal_plan_slots`). 미배식 칸은 `menu_name is None`, 값 0이다."""

    slot_id: str
    position: str
    dish_type: str  # rice, soup, main, side, kimchi
    menu_name: str | None
    served_g: float
    energy_kcal: float
    protein_g: float


@dataclass(frozen=True)
class MealPlan:
    """끼니 배식 계획 (`meal_plans`). `slots`는 `slot_id` 순이다."""

    meal_plan_id: str
    on: date
    meal: MealType
    diet_type: str
    baseline_photo_id: str | None
    slots: tuple[MealPlanSlot, ...]


@dataclass(frozen=True)
class SlotIntakeRow:
    """칸별 섭취 한 행 (`slot_intakes`)."""

    slot_id: str
    intake_fraction_est: float | None  # 0~1. 판단 불가면 None
    status: SlotStatus
    quality_issues: tuple[QualityIssue, ...]
    estimate_basis: str  # mock, staff, vlm:<어댑터>


@dataclass(frozen=True)
class MealOrder:
    """환자의 한 끼 발주 (`meal_orders`). `on`·`meal`은 배식 계획에서 가져온다.

    금식 발주도 `record_status`는 값이 있다(`not_recorded`). `slot_intakes`는 `slot_id` 순이다.
    """

    meal_order_id: str
    patient_id: str
    meal_plan_id: str
    on: date
    meal: MealType
    diet_category: str | None
    diet_code: str | None
    order_status: OrderStatus
    order_from: str | None
    order_note: str | None
    record_status: RecordStatus
    post_photo_id: str | None
    staff_zero_reason: str | None  # refused, not_eaten
    energy_kcal_est: float | None
    protein_g_est: float | None
    incomplete: bool
    data_source: str
    slot_intakes: tuple[SlotIntakeRow, ...]


@dataclass(frozen=True)
class DailyIntakeRow:
    """하루 섭취 한 행 (`daily_intakes`). 기록된 끼니가 없으면 섭취량과 %는 None이다."""

    patient_id: str
    on: date
    energy_kcal: float | None
    protein_g: float | None
    energy_pct: float | None
    protein_pct: float | None
    recorded_meals: int
    unrecorded_meals: int
    npo_meals: int


@dataclass(frozen=True)
class AlertRow:
    """섭취 부족 경고 한 행 (`alerts`).

    `evaluated_at`은 원문 `YYYY-MM-DDTHH:MM:SS`, `basis_values`는 근거 수치 JSON 배열을
    `NutrientEvidence`로 파싱한 것이다(NULL이면 빈 tuple).
    """

    alert_id: str
    patient_id: str
    evaluated_at: str
    level: AlertLevel
    basis_period: str | None
    basis_values: tuple[NutrientEvidence, ...]
    nutrients: tuple[Nutrient, ...]
    unrecorded_meals: int
