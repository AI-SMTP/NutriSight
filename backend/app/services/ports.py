"""환자 데이터 포트 계약과 추천 카드 타입 (`docs/data-model.md` 6절).

`PatientDataPort`는 섭취 요약 조회, 추천 카드 조회, 추천 카드 수정을 맡는다.
값의 이름·상태 값은 `docs/data-model.md`를 따른다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Protocol

from app.nutrition.types import AlertResult, DailyIntake


class PrescriptionType(StrEnum):
    """처방 유형 7종 (`docs/data-model.md` 6절)."""

    FOOD_FORTIFICATION = "food_fortification"  # 식사 강화
    ONS = "ons"  # 경구영양보충
    TEXTURE_MODIFICATION = "texture_modification"  # 식사 형태 변경
    SNACK_ADDITION = "snack_addition"  # 간식 추가
    DIETITIAN_REFERRAL = "dietitian_referral"  # 영양 상담·다학제 의뢰
    MONITORING_REVIEW = "monitoring_review"  # 재평가·관찰
    OTHER = "other"


class AddedBy(StrEnum):
    """추천 항목을 만든 주체."""

    AGENT = "agent"
    DOCTOR = "doctor"


class ModifiedBy(StrEnum):
    """추천 카드를 마지막으로 고친 주체."""

    AGENT = "agent"
    CHAT = "chat"
    DOCTOR = "doctor"


class RecommendationStatus(StrEnum):
    """추천 카드 상태. `active`만 고칠 수 있다."""

    ACTIVE = "active"
    SUPERSEDED = "superseded"
    CONFIRMED = "confirmed"
    FAILED = "failed"


@dataclass(frozen=True)
class LeftMenu:
    """자주 남긴 메뉴 한 항목. 집계 규칙은 T4에서 정한다."""

    menu_name: str
    dish_type: str
    avg_intake_fraction: float  # 0~1
    meal_count: int  # 1 이상


@dataclass(frozen=True)
class IntakeSummary:
    """기준일 `on`을 포함한 최근 `days`일 섭취 요약."""

    patient_id: str
    period_start: date
    period_end: date  # = on
    daily: tuple[DailyIntake, ...]  # 오래된 날부터. 발주가 하나라도 있는 날만
    alert: AlertResult | None  # 판정일이 on 이하인 판정 중 가장 최근 것
    frequently_left_menus: tuple[LeftMenu, ...]  # avg_intake_fraction 오름차순


@dataclass(frozen=True)
class EvidenceRef:
    """근거 문서 ID와 절 (가이드라인 검색 결과의 `doc_id`·`section`)."""

    doc_id: str
    section: str


@dataclass(frozen=True)
class RecommendationItem:
    """추천 항목 한 개 (`docs/data-model.md` 6절 추천 항목 스키마)."""

    item_id: str  # 카드 안에서 유일
    type: PrescriptionType
    title: str
    detail: str
    duration_days: int | None
    review_date: date | None
    added_by: AddedBy
    evidence: tuple[EvidenceRef, ...]


@dataclass(frozen=True)
class RecommendationCard:
    """추천 카드 (`recommendations`)."""

    recommendation_id: str
    patient_id: str
    alert_id: str | None
    items: tuple[RecommendationItem, ...]
    cautions: tuple[str, ...]
    last_modified_by: ModifiedBy
    thread_id: str | None  # chat 수정이면 대화 ID, agent·doctor 수정이면 None
    created_at: datetime
    updated_at: datetime
    status: RecommendationStatus


class PatientDataError(Exception):
    """환자 데이터 포트 예외의 공통 기반."""


class PatientNotFoundError(PatientDataError):
    """환자가 없다."""


class RecommendationNotFoundError(PatientDataError):
    """추천 카드가 없다."""


class RecommendationNotEditableError(PatientDataError):
    """상태가 `active`가 아닌 카드는 고칠 수 없다."""


class PatientDataPort(Protocol):
    """화면·에이전트 도구가 환자 데이터를 읽고 추천 카드를 고치는 인터페이스."""

    async def get_intake_summary(self, patient_id: str, days: int, on: date) -> IntakeSummary:
        """`on - (days - 1)` ~ `on` 섭취 요약. 환자 없음 → `PatientNotFoundError`,
        `days < 1` → `ValueError`."""
        ...

    async def get_recommendation(self, patient_id: str) -> RecommendationCard | None:
        """`active`·`failed` 카드 중 `created_at`이 가장 늦은 것(같으면 ID가 사전순으로 큰 것).
        후보가 없으면 `None`, 환자 없음 → `PatientNotFoundError`."""
        ...

    async def update_recommendation(
        self,
        recommendation_id: str,
        items: tuple[RecommendationItem, ...],
        modified_by: ModifiedBy,
        thread_id: str | None,
    ) -> RecommendationCard:
        """`items`·`last_modified_by`·`thread_id`·`updated_at`만 바꾼 카드를 돌려준다.

        카드 없음 → `RecommendationNotFoundError`, `active`가 아님 →
        `RecommendationNotEditableError`, `thread_id` 규칙·`item_id` 중복 위반 → `ValueError`.
        """
        ...
