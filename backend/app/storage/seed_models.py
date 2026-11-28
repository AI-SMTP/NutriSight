"""시드 파일(`data/seed/demo_seed.json`)의 형태 검증 모델 (스펙 3.7).

- 날짜는 시연일(D=0) 기준 상대 일수(`*_offset`)로 받는다. 실제 날짜 변환은 적재 때 한다.
- 열거값은 기존 `StrEnum`을 재사용하고, 대응 `StrEnum`이 없는 값은 `Literal`로 받아
  `schema.sql`의 CHECK 목록과 같은 값만 통과시킨다.
- 모르는 필드는 거절한다. `meta`와 발주의 `source_note`는 받기만 하고 적재에 쓰지 않는다.
- 필드 사이 관계(ID 중복, 참조 대상 존재)는 `seed.load_seed_file`이 검증한다.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.intake.types import QualityIssue, SlotStatus
from app.nutrition.types import MealType, OrderStatus, RecordStatus, Sex, TargetSource

# 식판 칸 수는 6칸 고정이다(data-model.md "식판 칸 배치").
SLOTS_PER_PLAN = 6

CkdDialysis = Literal["none", "ckd", "dialysis"]
DataSource = Literal["mock", "upload"]
AssessmentKind = Literal[
    "mna_sf",
    "nutrition_screening",
    "swallowing",
    "chewing",
    "appetite_assist",
    "pressure_injury",
    "refeeding_risk",
]
DishType = Literal["rice", "soup", "main", "side", "kimchi"]
StaffZeroReason = Literal["refused", "not_eaten"]
# `vlm:<어댑터>`는 어댑터 이름이 한 글자 이상이어야 한다(schema.sql의 GLOB 'vlm:?*').
ESTIMATE_BASIS_PATTERN = r"^(mock|staff|vlm:.+)$"

NonEmptyStr = Annotated[str, StringConstraints(min_length=1)]


class _SeedModel(BaseModel):
    """시드 모델 공통 설정: 모르는 필드와 NaN·무한대 거절, 읽기 전용."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class SeedPatient(_SeedModel):
    """환자 한 명. `age_at_d0`는 시연일 기준 나이로, 적재 때 `birth_year`로 바꾼다."""

    patient_id: NonEmptyStr
    display_name: str
    room: str | None
    sex: Sex
    age_at_d0: int = Field(ge=0)
    height_cm: float | None
    default_diet_type: NonEmptyStr
    conditions: tuple[str, ...]
    diet_restrictions: str
    ckd_dialysis: CkdDialysis
    observation_start_offset: int
    data_source: DataSource


class SeedWeight(_SeedModel):
    """체중 기록 한 행. 키는 (`patient_id`, `day_offset`)."""

    patient_id: str
    day_offset: int
    weight_kg: float


class SeedTarget(_SeedModel):
    """목표 이력 한 행. 키는 (`patient_id`, `effective_from_offset`)."""

    patient_id: str
    effective_from_offset: int
    energy_kcal: float
    protein_g: float
    source: TargetSource
    note: str | None


class SeedAssessment(_SeedModel):
    """평가 기록 한 행. 키는 (`patient_id`, `day_offset`, `kind`)."""

    patient_id: str
    day_offset: int
    kind: AssessmentKind
    result: str | None
    score: float | None
    note: str | None


class SeedSlot(_SeedModel):
    """배식 계획의 칸 하나. 미배식 칸은 `menu_name` None, `served_g`·열량·단백질 0이다."""

    slot_id: NonEmptyStr
    position: str
    dish_type: DishType
    menu_name: str | None
    served_g: float = Field(ge=0)
    energy_kcal: float
    protein_g: float

    @property
    def is_served(self) -> bool:
        """배식 칸이면 True. 미배식 칸에는 칸별 섭취를 둘 수 없다."""
        return self.served_g > 0

    @model_validator(mode="after")
    def _check_unserved_consistency(self) -> SeedSlot:
        """`served_g == 0`과 `menu_name is None`은 함께만 쓰고, 미배식 칸의 값은 0이다."""
        if (self.served_g == 0) != (self.menu_name is None):
            raise ValueError("미배식 칸은 served_g 0과 menu_name null을 함께 써야 한다")
        if self.served_g == 0 and (self.energy_kcal != 0 or self.protein_g != 0):
            raise ValueError("미배식 칸의 energy_kcal·protein_g는 0이어야 한다")
        return self


class SeedMealPlan(_SeedModel):
    """끼니 배식 계획. 키는 `meal_plan_id`, 그리고 (`day_offset`, `meal`, `diet_type`)."""

    meal_plan_id: NonEmptyStr
    day_offset: int
    meal: MealType
    diet_type: NonEmptyStr
    baseline_photo_id: str | None
    slots: tuple[SeedSlot, ...] = Field(min_length=SLOTS_PER_PLAN, max_length=SLOTS_PER_PLAN)


class SeedSlotIntake(_SeedModel):
    """칸별 섭취 한 행. `slot_id`는 발주한 배식 계획의 배식 칸이어야 한다."""

    slot_id: NonEmptyStr
    intake_fraction_est: float | None = Field(ge=0, le=1)
    status: SlotStatus
    quality_issues: tuple[QualityIssue, ...]
    estimate_basis: str = Field(pattern=ESTIMATE_BASIS_PATTERN)


class SeedMealOrder(_SeedModel):
    """환자의 한 끼 발주.

    `record_status`는 금식·취소 발주에서만 None일 수 있고, 적재 때 `not_recorded`로 바꾼다.
    금식·취소 발주에는 칸별 섭취가 없다.
    `order_from_meal`이 없으면 적재 때 `breakfast`를 쓴다. `source_note`는 버린다.
    """

    meal_order_id: NonEmptyStr
    patient_id: str
    meal_plan_id: str
    diet_category: str | None
    diet_code: str | None
    order_status: OrderStatus
    order_from_offset: int | None
    order_from_meal: MealType | None = None
    order_note: str | None
    record_status: RecordStatus | None
    staff_zero_reason: StaffZeroReason | None
    post_photo_id: str | None
    slot_intakes: tuple[SeedSlotIntake, ...]
    energy_kcal_est: float | None
    protein_g_est: float | None
    incomplete: bool
    data_source: DataSource
    source_note: str | None = None

    @model_validator(mode="after")
    def _check_status_consistency(self) -> SeedMealOrder:
        """발주된 끼니만 기록 상태 None을 금하고, 금식·취소 끼니에는 칸별 섭취를 두지 않는다."""
        if self.order_status is OrderStatus.ORDERED and self.record_status is None:
            raise ValueError("발주된 끼니(ordered)의 record_status는 null일 수 없다")
        if self.order_status is not OrderStatus.ORDERED and self.slot_intakes:
            raise ValueError(f"{self.order_status} 발주에는 칸별 섭취를 둘 수 없다")
        return self


class DemoSeed(_SeedModel):
    """시드 파일 전체. `meta`는 설명 문서라 받기만 한다."""

    meta: Any = None
    patients: tuple[SeedPatient, ...]
    patient_weights: tuple[SeedWeight, ...]
    patient_targets: tuple[SeedTarget, ...]
    patient_assessments: tuple[SeedAssessment, ...]
    meal_plans: tuple[SeedMealPlan, ...]
    meal_orders: tuple[SeedMealOrder, ...]
