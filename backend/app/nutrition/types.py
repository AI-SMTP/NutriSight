"""판단 알고리즘 계약 (`docs/system-architecture.md` 6절의 함수 4개를 메서드로).

`NutritionEngine` 구현은 입력을 고치지 않고 외부 호출을 하지 않는 동기 순수 메서드만 둔다.
값의 이름·단위·상태 값은 `docs/data-model.md`를 따른다. `_pct`는 백분율(0 이상, 상한 없음)이다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Protocol

from app.intake.types import SlotStatus


class Sex(StrEnum):
    FEMALE = "female"
    MALE = "male"


class TargetSource(StrEnum):
    """하루 목표의 출처. 우선순위는 판단 알고리즘 트랙이 정한다."""

    TEAM_SET = "team_set"  # 진료팀 설정
    ESPEN_WEIGHT = "espen_weight"  # 체중 기반 계산
    KDRI = "kdri"  # 한국인 영양소 섭취기준


class MealType(StrEnum):
    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"


class OrderStatus(StrEnum):
    ORDERED = "ordered"
    NPO = "npo"  # 금식
    CANCELLED = "cancelled"  # 외출·퇴원 등


class RecordStatus(StrEnum):
    NOT_RECORDED = "not_recorded"  # 발주됐지만 식후 사진이 없음
    PENDING = "pending"  # 분석 대기·분석 중
    RECORDED = "recorded"
    NOT_DETERMINABLE = "not_determinable"  # 사진 전체 판단 불가
    FAILED = "failed"  # 분석 실패


class AlertLevel(StrEnum):
    NONE = "none"
    CAUTION = "caution"
    WARNING = "warning"


class Nutrient(StrEnum):
    ENERGY = "energy"
    PROTEIN = "protein"


@dataclass(frozen=True)
class SlotIntake:
    """칸 하나의 섭취 (`slot_intakes`)."""

    slot_id: str
    intake_fraction_est: float | None  # 0~1. 판단 불가면 None
    status: SlotStatus


@dataclass(frozen=True)
class SlotNutrition:
    """배식 계획의 칸별 영양값, 표준 배식량 기준 (`meal_plan_slots`)."""

    slot_id: str
    energy_kcal: float
    protein_g: float


@dataclass(frozen=True)
class MealNutrients:
    """끼니 영양 섭취량 (`meal_orders` 계산 필드)."""

    energy_kcal_est: float
    protein_g_est: float
    incomplete: bool  # 판단 불가 칸이 있어 합계가 불완전한지


@dataclass(frozen=True)
class PatientProfile:
    sex: Sex
    birth_year: int


@dataclass(frozen=True)
class TargetRecord:
    """목표 이력 한 행 (`patient_targets`)."""

    effective_from: date
    energy_kcal: float
    protein_g: float
    source: TargetSource


@dataclass(frozen=True)
class WeightRecord:
    """체중 기록 한 행 (`patient_weights`)."""

    measured_on: date
    weight_kg: float


@dataclass(frozen=True)
class DailyTarget:
    """그날 적용된 하루 목표."""

    energy_kcal: float
    protein_g: float
    source: TargetSource


@dataclass(frozen=True)
class MealRecord:
    """환자의 한 끼 발주·기록 (`meal_orders`)."""

    meal: MealType
    order_status: OrderStatus
    record_status: RecordStatus
    energy_kcal_est: float | None
    protein_g_est: float | None


@dataclass(frozen=True)
class DailyIntake:
    """하루 섭취 (`daily_intakes`). 기록된 끼니가 없으면 섭취량과 %는 None이다."""

    on: date
    energy_kcal: float | None  # 기록된 끼니 합계
    protein_g: float | None
    energy_pct: float | None  # 3끼 환산 목표 대비 %, 0 이상·상한 없음
    protein_pct: float | None
    recorded_meals: int
    unrecorded_meals: int
    npo_meals: int  # 금식·취소 끼니 수
    target: DailyTarget


@dataclass(frozen=True)
class AlertRules:
    """경고 규칙 설정값."""

    caution_avg_pct: float = 75.0
    caution_window_days: int = 7
    warning_pct: float = 50.0
    warning_consecutive_days: int = 5


@dataclass(frozen=True)
class NutrientEvidence:
    """영양소별 경고 근거 수치."""

    nutrient: Nutrient
    avg_pct: float | None
    low_days_streak: int


@dataclass(frozen=True)
class AlertResult:
    """섭취 부족 경고 판정 (`alerts`). `level`이 none이면 `nutrients`는 비어 있다."""

    level: AlertLevel
    nutrients: tuple[Nutrient, ...]
    period_start: date | None
    period_end: date | None
    evidence: tuple[NutrientEvidence, ...]
    unrecorded_meals: int


class NutritionEngine(Protocol):
    """판단 알고리즘이 따르는 인터페이스. 모든 메서드는 동기 순수 함수다."""

    def meal_nutrients(
        self,
        slot_intakes: tuple[SlotIntake, ...],
        plan_slots: tuple[SlotNutrition, ...],
    ) -> MealNutrients:
        """칸별 섭취와 배식 계획으로 끼니 영양량을 낸다. 미등록 칸이면 `ValueError`."""
        ...

    def daily_target(
        self,
        profile: PatientProfile,
        targets: tuple[TargetRecord, ...],
        weights: tuple[WeightRecord, ...],
        on: date,
    ) -> DailyTarget:
        """그날 적용된 하루 목표. 목표·체중 이력이 없어도 항상 돌려준다."""
        ...

    def daily_intake(
        self,
        on: date,
        meals: tuple[MealRecord, ...],
        target: DailyTarget,
    ) -> DailyIntake:
        """그날 끼니 기록과 목표로 하루 섭취 한 행을 만든다."""
        ...

    def evaluate_alert(
        self,
        history: tuple[DailyIntake, ...],
        rules: AlertRules,
        on: date,
    ) -> AlertResult:
        """일별 섭취 이력과 규칙으로 섭취 부족 경고를 판정한다."""
        ...
