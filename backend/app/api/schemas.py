"""HTTP API 요청·응답 모델 (스펙 3.3 응답 모델·`ItemInput`, `docs/data-model.md`).

필드 이름은 스펙·data-model 그대로다. 서비스 결과(frozen dataclass)와 필드 이름이 같은 모델은
`from_attributes`로 `Model.model_validate(view)`가 그대로 읽는다(tuple은 list로 검증된다).
이름이 다른 필드는 `validation_alias`(`DailyIntakeOut.date` ← `on`) 또는 생성 함수
(`AlertOut.from_row`)로 맞춘다. 앱이 만든 시각(`created_at`·`updated_at`·`confirmed_at`)과 판정 시각
(`evaluated_at`)은 저장 문자열 형식 그대로 돌려준다. 실수 값은 반올림하지 않는다.

요청 모델은 모르는 필드를 거부한다(`extra="forbid"`, 422). 항목 값 규칙은 `item_rules`의 검사기를
그대로 부른다(생성기 결과·포트 저장과 같은 규칙).
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Annotated, Literal, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.nutrition.types import AlertLevel, Nutrient, Sex, TargetSource
from app.services import item_rules
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


class PrescriptionOut(_ViewModel):
    """처방 한 건 (`Prescription`). `confirmed_at`은 저장 문자열 그대로다."""

    prescription_id: str
    patient_id: str
    recommendation_id: str | None
    items: list[ItemOut]
    confirmed_at: str
    status: Literal["confirmed"]


# 요청 ----------------------------------------------------------------------


REQUEST_LIST_MAX = 100  # 요청 목록 상한(확정 `item_ids`, 처방 작성 `items`). 요청 크기 제한


_ISO_DATE_TEXT = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _iso_date_text(value: object) -> object:
    """날짜 입력(`review_date`)을 `YYYY-MM-DD` 문자열·null·`date`로 한정한다.

    FastAPI는 본문을 dict로 바꾼 뒤 Python 모드로 검증하므로 `Field(strict=True)`는 날짜 문자열까지
    거부한다. 그래서 형식은 여기서 거르고 실제 날짜 변환은 Pydantic에 맡긴다.
    """
    if value is None or (isinstance(value, dt.date) and not isinstance(value, dt.datetime)):
        return value
    if isinstance(value, str) and _ISO_DATE_TEXT.fullmatch(value):
        return value
    raise ValueError("review_date는 YYYY-MM-DD 문자열이어야 한다")


# `YYYY-MM-DD` 문자열·null만 받는 날짜 입력 타입. 값 규칙은 필드마다 `AfterValidator`로 더한다.
IsoDateOrNone = Annotated[dt.date | None, BeforeValidator(_iso_date_text)]


class _RequestModel(BaseModel):
    """요청 본문 기반. 모르는 필드(`added_by`·`evidence` 등)는 422로 거부한다."""

    model_config = ConfigDict(extra="forbid")


class ItemInput(_RequestModel):
    """의사가 보낸 항목 한 개. `added_by`·`evidence`는 받지 않는다(서버가 정한다).

    `duration_days`는 엄격 정수라 JSON `true`·`"7"`을 거부한다. `review_date`는 `YYYY-MM-DD`
    문자열과 null만 받는다(숫자·시각이 붙은 문자열은 422).
    """

    item_id: Annotated[str, AfterValidator(item_rules.check_item_id)]
    type: PrescriptionType
    title: Annotated[str, AfterValidator(item_rules.check_title)]
    detail: Annotated[str, AfterValidator(item_rules.check_detail)]
    duration_days: Annotated[
        int | None, Field(strict=True), AfterValidator(item_rules.check_duration_days)
    ]
    review_date: Annotated[IsoDateOrNone, AfterValidator(item_rules.check_review_date)]

    def to_edit(self) -> item_rules.ItemEdit:
        """서비스 입력 `ItemEdit`로 바꾼다. 두 타입의 필드는 이름·값이 1:1이다."""
        return item_rules.ItemEdit(**self.model_dump())


class _ItemsBody(_RequestModel):
    """항목 목록(`items`)을 받는 요청 본문 기반. `item_id`는 목록 안에서 유일해야 한다(422)."""

    items: list[ItemInput]

    @model_validator(mode="after")
    def _check_unique(self) -> Self:
        item_rules.check_unique_item_ids(item.item_id for item in self.items)
        return self

    def edits(self) -> tuple[item_rules.ItemEdit, ...]:
        """서비스로 넘길 항목 tuple(요청 순서 그대로)."""
        return tuple(item.to_edit() for item in self.items)


class RecommendationPatch(_ItemsBody):
    """PATCH 본문. `items`가 카드의 새 항목 목록(순서 포함)이다.

    `expected_updated_at`은 카드 응답의 `updated_at` 문자열 그대로이며 `datetime`으로 바꾸지 않는다.
    """

    expected_updated_at: str


class PrescriptionCreate(_ItemsBody):
    """처방 직접 작성 본문. `items`는 1~100개이고 `item_id`는 목록 안에서 유일하다."""

    items: list[ItemInput] = Field(min_length=1, max_length=REQUEST_LIST_MAX)


class ConfirmRequest(_RequestModel):
    """확정 본문. `item_ids`는 1~100개이고 중복은 하나로 취급한다(서비스)."""

    item_ids: list[str] = Field(min_length=1, max_length=REQUEST_LIST_MAX)
    expected_updated_at: str

    def to_item_ids(self) -> tuple[str, ...]:
        """서비스로 넘길 `item_id` tuple(요청 순서 그대로)."""
        return tuple(self.item_ids)
