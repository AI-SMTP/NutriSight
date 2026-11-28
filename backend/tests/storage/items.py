"""저장소 테스트가 함께 쓰는 추천 항목 표본 (`docs/data-model.md` 6절 예시)."""

from __future__ import annotations

from datetime import date

from app.services.ports import AddedBy, EvidenceRef, PrescriptionType, RecommendationItem

# 에이전트 항목: 근거 2개, 재평가일 없음.
AGENT_ITEM = RecommendationItem(
    item_id="rx1",
    type=PrescriptionType.FOOD_FORTIFICATION,
    title="식사 강화 7일",
    detail="단백질 반찬 강화로 에너지·단백질 밀도 높이기",
    duration_days=7,
    review_date=None,
    added_by=AddedBy.AGENT,
    evidence=(
        EvidenceRef(doc_id="espen_geriatrics", section="R20"),
        EvidenceRef(doc_id="espen_geriatrics", section="R23"),
    ),
)
# 의사 항목: 근거 없음, 기간 없음, 재평가일 있음.
DOCTOR_ITEM = RecommendationItem(
    item_id="rx2",
    type=PrescriptionType.MONITORING_REVIEW,
    title="재평가",
    detail="",
    duration_days=None,
    review_date=date(2026, 12, 4),
    added_by=AddedBy.DOCTOR,
    evidence=(),
)
