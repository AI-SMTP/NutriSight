"""HTTP API 응답 모델 (스펙 3.3 응답 모델, `docs/data-model.md`).

필드 이름은 스펙·data-model 그대로다. 서비스 결과(frozen dataclass)와 필드 이름이 같은 모델은
`from_attributes`로 `Model.model_validate(view)`가 그대로 읽는다(tuple은 list로 검증된다).
이름이 다른 필드는 `validation_alias`(`DailyIntakeOut.date` ← `on`) 또는 생성 함수
(`AlertOut.from_row`)로 맞춘다. 앱이 만든 시각(`created_at`·`updated_at`·`confirmed_at`)과 판정 시각
(`evaluated_at`)은 저장 문자열 형식 그대로 돌려준다. 실수 값은 반올림하지 않는다.
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.nutrition.types import AlertLevel, Nutrient, Sex, TargetSource
from app.services.clock import format_app_timestamp
from app.services.patients import alert_to_result
from app.services.ports import AddedBy, ModifiedBy, PrescriptionType, RecommendationStatus
from app.storage.records import AlertRow


class _ViewModel(BaseModel):
    """서비스 결과 객체의 속성을 읽어 검증하는 응답 모델 기반."""

    model_config = ConfigDict(from_attributes=True)


# 목록·요약 -------------------------------------------------------------------


class PatientListItem(_ViewModel):
    """환자 목록 한 줄. 판정이 없으면 `alert_level`은 null이다."""

    patient_id: str
    display_name: str
    room: str | None
    alert_level: AlertLevel | None
    alert_nutrients: list[Nutrient]


class LatestWeight(_ViewModel):
    """시연일 이하 최근 체중."""

    measured_on: dt.date
    weight_kg: float


class WeightChangeOut(_ViewModel):
    """30일 체중 변화. `pct`는 기준 측정값 대비 백분율."""

    kg: float
    pct: float


class TargetOut(_ViewModel):
    """시연일 목표. `effective_from`은 `team_set`일 때 적용 시작일, 아니면 null."""

    energy_kcal: float
    protein_g: float
    source: TargetSource
    effective_from: dt.date | None


class AssessmentOut(_ViewModel):
    """`kind`별 최신 평가 한 건."""

    kind: str
    assessed_on: dt.date
    result: str | None
    score: float | None
    note: str | None


class PatientDetail(_ViewModel):
    """환자 요약."""

    patient_id: str
    display_name: str
    room: str | None
    sex: Sex
    age: int
    height_cm: float | None
    conditions: list[str]
    diet_restrictions: str
    ckd_dialysis: str
    latest_weight: LatestWeight | None
    weight_change_30d: WeightChangeOut | None
    bmi: float | None
    target: TargetOut
    assessments: list[AssessmentOut]


# 섭취 추이 -------------------------------------------------------------------


class DailyTargetOut(_ViewModel):
    """그날 적용된 하루 목표."""

    energy_kcal: float
    protein_g: float
    source: TargetSource


class DailyIntakeOut(_ViewModel):
    """하루 섭취. 기록된 끼니가 없으면 섭취량과 %는 null이다."""

    date: dt.date = Field(validation_alias="on")  # 서비스 `DailyIntake.on`을 읽는다
    energy_kcal: float | None
    protein_g: float | None
    energy_pct: float | None
    protein_pct: float | None
    recorded_meals: int
    unrecorded_meals: int
    npo_meals: int
    target: DailyTargetOut


class PrescriptionMark(_ViewModel):
    """섭취 추이에 표시할 처방 확정 시점. `confirmed_at`은 저장 문자열 그대로다."""

    prescription_id: str
    confirmed_at: str


class IntakeTrend(_ViewModel):
    """시연일을 끝으로 하는 섭취 추이. `days`는 오래된 날부터, 발주가 있는 날만."""

    patient_id: str
    period_start: dt.date
    period_end: dt.date
    days: list[DailyIntakeOut]
    prescriptions: list[PrescriptionMark]


# 경고 ----------------------------------------------------------------------


class EvidenceOut(_ViewModel):
    """영양소별 경고 근거 수치."""

    nutrient: Nutrient
    avg_pct: float | None
    low_days_streak: int


class AlertOut(_ViewModel):
    """섭취 부족 판정 (`Alert`). 근거 기간이 없으면 `period_start`·`period_end`는 null이다."""

    alert_id: str
    evaluated_at: str
    level: AlertLevel
    nutrients: list[Nutrient]
    period_start: dt.date | None
    period_end: dt.date | None
    evidence: list[EvidenceOut]
    unrecorded_meals: int

    @classmethod
    def from_row(cls, row: AlertRow) -> AlertOut:
        """판정 행의 ID·시각과 `alert_to_result`의 기간·근거를 합친다."""
        result = alert_to_result(row)
        return cls(
            alert_id=row.alert_id,
            evaluated_at=row.evaluated_at,
            level=result.level,
            nutrients=result.nutrients,
            period_start=result.period_start,
            period_end=result.period_end,
            evidence=result.evidence,
            unrecorded_meals=result.unrecorded_meals,
        )


# 추천 카드 -----------------------------------------------------------------


class EvidenceRefOut(_ViewModel):
    """추천 항목의 근거 문서 ID와 절."""

    doc_id: str
    section: str


class ItemOut(_ViewModel):
    """추천·처방 항목 (`docs/data-model.md` 6절 추천 항목 스키마)."""

    item_id: str
    type: PrescriptionType
    title: str
    detail: str
    duration_days: int | None
    review_date: dt.date | None
    added_by: AddedBy
    evidence: list[EvidenceRefOut]


class RecommendationOut(_ViewModel):
    """추천 카드 (`Recommendation`). 시각은 저장 문자열 형식 그대로다.

    화면은 `updated_at`을 PATCH·확정의 `expected_updated_at`으로 그대로 돌려준다.
    """

    recommendation_id: str
    patient_id: str
    alert_id: str | None
    items: list[ItemOut]
    cautions: list[str]
    last_modified_by: ModifiedBy
    thread_id: str | None
    created_at: str
    updated_at: str
    status: RecommendationStatus

    @field_validator("created_at", "updated_at", mode="before")
    @classmethod
    def _app_timestamp_text(cls, value: object) -> object:
        """카드의 `datetime`을 저장 문자열 형식(`format_app_timestamp`)으로 바꾼다."""
        return format_app_timestamp(value) if isinstance(value, dt.datetime) else value
