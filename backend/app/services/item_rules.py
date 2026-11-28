"""추천 항목·근거·카드 공통 검증 규칙 (스펙 3.5절 항목 규칙 표).

Pydantic 입력 검증기, 생성기 결과 검증, 포트 저장이 같은 함수를 쓴다.
dataclass 타입 주석은 실행 중 값을 보장하지 않으므로 값마다 타입과 범위를 검사한다.
위반이면 `ValueError`를 던진다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime

from app.recommender.generator_types import GeneratedCard
from app.services.ports import (
    AddedBy,
    EvidenceRef,
    ModifiedBy,
    PrescriptionType,
    RecommendationItem,
)

ITEM_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
TITLE_MAX = 100
DETAIL_MAX = 1000
DURATION_MAX_DAYS = 365
EVIDENCE_FIELD_MAX = 100
CAUTIONS_MAX = 10
CAUTION_MAX = 300


@dataclass(frozen=True)
class ItemEdit:
    """의사가 보낸 항목 한 개 (`ItemInput`). `added_by`·`evidence`는 받지 않는다."""

    item_id: str
    type: PrescriptionType
    title: str
    detail: str
    duration_days: int | None
    review_date: date | None

    def to_doctor_item(self) -> RecommendationItem:
        """의사가 새로 만든 항목으로 바꾼다(`added_by = doctor`, `evidence = ()`)."""
        return RecommendationItem(
            item_id=self.item_id,
            type=self.type,
            title=self.title,
            detail=self.detail,
            duration_days=self.duration_days,
            review_date=self.review_date,
            added_by=AddedBy.DOCTOR,
            evidence=(),
        )


def _check_str(value: object, name: str, min_len: int, max_len: int) -> str:
    """`min_len`~`max_len`자 문자열인지 확인한다."""
    if not isinstance(value, str):
        raise ValueError(f"{name}은 문자열이어야 한다")
    if not min_len <= len(value) <= max_len:
        raise ValueError(f"{name}은 {min_len}~{max_len}자여야 한다")
    return value


def check_item_id(value: object) -> str:
    """`item_id`가 `^[A-Za-z0-9_-]{1,32}$`인지 확인한다."""
    # fullmatch로 끝의 줄바꿈("abc\n")도 거부한다.
    if not isinstance(value, str) or ITEM_ID_PATTERN.fullmatch(value) is None:
        raise ValueError("item_id는 영문·숫자·_·- 1~32자여야 한다")
    return value


def check_title(value: object) -> str:
    """`title`이 1~100자 문자열인지 확인한다."""
    return _check_str(value, "title", 1, TITLE_MAX)


def check_detail(value: object) -> str:
    """`detail`이 0~1000자 문자열인지 확인한다."""
    return _check_str(value, "detail", 0, DETAIL_MAX)


def check_duration_days(value: object) -> int | None:
    """`duration_days`가 `None` 또는 1~365 정수(`bool` 제외)인지 확인한다."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("duration_days는 정수여야 한다")
    if not 1 <= value <= DURATION_MAX_DAYS:
        raise ValueError(f"duration_days는 1~{DURATION_MAX_DAYS}이어야 한다")
    return value


def check_review_date(value: object) -> date | None:
    """`review_date`가 `None` 또는 `date`(`datetime` 제외)인지 확인한다."""
    if value is None:
        return None
    if isinstance(value, datetime) or not isinstance(value, date):
        raise ValueError("review_date는 날짜여야 한다")
    return value


def check_thread_id(modified_by: ModifiedBy, thread_id: str | None) -> None:
    """`chat` 수정은 대화 ID가 있어야 하고, `agent`·`doctor` 수정은 `None`이어야 한다."""
    if modified_by == ModifiedBy.CHAT and not thread_id:
        raise ValueError("chat 수정에는 thread_id가 있어야 한다")
    if modified_by != ModifiedBy.CHAT and thread_id is not None:
        raise ValueError(f"{modified_by.value} 수정의 thread_id는 None이어야 한다")


def _check_evidence(evidence: object) -> None:
    """근거가 `EvidenceRef` tuple이고 `doc_id`·`section`이 1~100자인지 확인한다."""
    if not isinstance(evidence, tuple):
        raise ValueError("evidence는 tuple이어야 한다")
    for ref in evidence:
        if not isinstance(ref, EvidenceRef):
            raise ValueError("evidence 원소는 EvidenceRef여야 한다")
        _check_str(ref.doc_id, "doc_id", 1, EVIDENCE_FIELD_MAX)
        _check_str(ref.section, "section", 1, EVIDENCE_FIELD_MAX)


def _check_enum(value: object, enum_cls: type, name: str) -> None:
    """열거형 인스턴스인지 확인한다. 같은 값의 문자열은 거부한다."""
    if not isinstance(value, enum_cls):
        raise ValueError(f"{name}은 {enum_cls.__name__}여야 한다")


def _check_item(item: object) -> None:
    """항목 하나의 공통 항목 규칙과 근거 규칙을 확인한다."""
    if not isinstance(item, RecommendationItem):
        raise ValueError("항목은 RecommendationItem이어야 한다")
    check_item_id(item.item_id)
    _check_enum(item.type, PrescriptionType, "type")
    check_title(item.title)
    check_detail(item.detail)
    check_duration_days(item.duration_days)
    check_review_date(item.review_date)
    _check_enum(item.added_by, AddedBy, "added_by")
    _check_evidence(item.evidence)


def validate_items(items: tuple[RecommendationItem, ...]) -> None:
    """모든 항목의 공통 항목·근거 규칙과 `item_id` 유일성을 확인한다."""
    if not isinstance(items, tuple):
        raise ValueError("items는 tuple이어야 한다")
    seen: set[str] = set()
    for item in items:
        _check_item(item)
        if item.item_id in seen:
            raise ValueError(f"item_id가 중복된다: {item.item_id}")
        seen.add(item.item_id)


def validate_cautions(cautions: tuple[str, ...]) -> None:
    """`cautions`가 최대 10개의 1~300자 문자열 tuple인지 확인한다."""
    if not isinstance(cautions, tuple):
        raise ValueError("cautions는 tuple이어야 한다")
    if len(cautions) > CAUTIONS_MAX:
        raise ValueError(f"cautions는 최대 {CAUTIONS_MAX}개다")
    for caution in cautions:
        _check_str(caution, "caution", 1, CAUTION_MAX)


def validate_generated_items(
    items: tuple[RecommendationItem, ...], cautions: tuple[str, ...]
) -> None:
    """생성기 결과의 항목·주의 문구를 확인한다.

    공통 규칙에 더해 항목이 1개 이상이고 모든 항목이 `added_by = agent`여야 한다.
    """
    validate_items(items)
    validate_cautions(cautions)
    if not items:
        raise ValueError("생성 결과에는 항목이 1개 이상 있어야 한다")
    if any(item.added_by is not AddedBy.AGENT for item in items):
        raise ValueError("생성 결과의 항목은 모두 added_by = agent여야 한다")


def validate_generated_card(card: object) -> None:
    """생성기 반환값이 `GeneratedCard` 인스턴스이고 생성기 결과 규칙을 모두 지키는지 확인한다."""
    if not isinstance(card, GeneratedCard):
        raise ValueError(f"생성 결과는 GeneratedCard여야 한다: {type(card).__name__}")
    validate_generated_items(card.items, card.cautions)
