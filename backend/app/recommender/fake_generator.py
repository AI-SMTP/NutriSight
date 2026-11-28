"""외부 호출 없이 입력 요약만으로 고정 카드를 만드는 `FakeRecommendationGenerator`.

실행 중 더미 구현이자 계약 테스트 대상이다 (스펙 3.5절 Fake 규칙).
"""

from __future__ import annotations

from datetime import date, timedelta

from app.nutrition.types import AlertLevel
from app.recommender.generator_types import GeneratedCard, GenerationError
from app.services.ports import (
    AddedBy,
    EvidenceRef,
    IntakeSummary,
    PrescriptionType,
    RecommendationItem,
)

FIXED_EVIDENCE: tuple[EvidenceRef, ...] = (EvidenceRef("espen_geriatrics", "R20"),)
FORTIFICATION_DAYS = 7
REVIEW_AFTER_DAYS = 7


def _item(
    item_id: str,
    type_: PrescriptionType,
    title: str,
    detail: str,
    *,
    duration_days: int | None = None,
    review_date: date | None = None,
) -> RecommendationItem:
    return RecommendationItem(
        item_id=item_id,
        type=type_,
        title=title,
        detail=detail,
        duration_days=duration_days,
        review_date=review_date,
        added_by=AddedBy.AGENT,
        evidence=FIXED_EVIDENCE,
    )


def _items(summary: IntakeSummary) -> tuple[RecommendationItem, ...]:
    base = (
        _item(
            "fortify",
            PrescriptionType.FOOD_FORTIFICATION,
            f"식사 강화 {FORTIFICATION_DAYS}일",
            "주식·반찬에 에너지·단백질을 더한다.",
            duration_days=FORTIFICATION_DAYS,
        ),
        _item(
            "review",
            PrescriptionType.MONITORING_REVIEW,
            "재평가",
            "섭취 추이를 다시 확인한다.",
            review_date=summary.period_end + timedelta(days=REVIEW_AFTER_DAYS),
        ),
    )
    if summary.alert is not None and summary.alert.level is AlertLevel.WARNING:
        return (*base, _item("ons", PrescriptionType.ONS, "경구영양보충 하루 400 kcal", ""))
    return base


def _cautions(summary: IntakeSummary) -> tuple[str, ...]:
    alert = summary.alert
    n = alert.unrecorded_meals if alert else 0
    if n <= 0:
        return ()
    return (f"미기록 끼니 {n}개가 있어 섭취 추이가 실제와 다를 수 있습니다.",)


class FakeRecommendationGenerator:
    """요약의 경고 수준·미기록 끼니 수로 고정 카드를 만드는 추천 생성기 더미."""

    def __init__(self, *, fail: bool = False) -> None:
        self._fail = fail

    async def generate(self, patient_id: str, summary: IntakeSummary) -> GeneratedCard:
        """`fail=True`면 `GenerationError`, 아니면 고정 규칙의 카드를 돌려준다."""
        if self._fail:
            raise GenerationError("FakeRecommendationGenerator(fail=True)")
        return GeneratedCard(items=_items(summary), cautions=_cautions(summary))
