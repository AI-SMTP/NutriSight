"""T5 골격이 없어도 RAG·환자 포트를 연결해 검증하는 환자 범위 고정 어댑터.

실제 처방·카드 저장 동작은 제공하지 않는다. 팀 T5가 승인하기 전까지
데모/테스트 전용이며 실제 환자 정보 및 외부 LLM 호출을 사용하지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from app.recommender.guideline_types import GuidelineSearch
from app.recommender.retrieval_guard import (
    CitationAuditReport,
    SafeRetrievalResult,
    safe_search_guidelines,
    verify_evidence_refs,
)
from app.services.ports import (
    IntakeSummary,
    PatientDataPort,
    RecommendationItem,
    RecommendationStatus,
)


class DraftPreviewStatus(StrEnum):
    BLOCKED = "blocked"
    REQUIRES_DOCTOR_REVIEW = "requires_doctor_review"


@dataclass(frozen=True)
class DraftPreviewResult:
    """미검증 근거나 부적절한 카드 상태면 차단한다. DB에는 절대 저장하지 않는다."""

    patient_id: str
    status: DraftPreviewStatus
    reason: str
    citation_audit: CitationAuditReport | None = None
    saved: bool = False


@dataclass(frozen=True)
class ScopedPatientTools:
    """환자 ID가 메서드 입력으로 노출되지 않는 T5 대비 도구 어댑터."""

    patient_id: str
    patient_data: PatientDataPort
    guideline_search: GuidelineSearch

    async def get_intake_summary(self, *, days: int, on: date) -> IntakeSummary:
        if days < 1:
            raise ValueError("days는 1 이상이어야 합니다")
        return await self.patient_data.get_intake_summary(self.patient_id, days, on)

    async def search_guidelines(self, query: str, *, limit: int = 3) -> SafeRetrievalResult:
        return await safe_search_guidelines(self.guideline_search, query, limit=limit)

    async def draft_prescription_preview(
        self, items: tuple[RecommendationItem, ...]
    ) -> DraftPreviewResult:
        """T5 도구 이름 대응용 *검증만* 수행. 원본 카드를 수정하지 않는다.

        실제 T5의 draft_prescription은 의료진·팀 합의 후 별도로 구현해야 한다.
        """
        card = await self.patient_data.get_recommendation(self.patient_id)
        if card is None or card.status is not RecommendationStatus.ACTIVE:
            return DraftPreviewResult(
                patient_id=self.patient_id,
                status=DraftPreviewStatus.BLOCKED,
                reason="수정 가능한 active 추천 카드가 없습니다.",
            )
        if not items:
            return DraftPreviewResult(
                patient_id=self.patient_id,
                status=DraftPreviewStatus.BLOCKED,
                reason="검토할 추천 항목이 없습니다.",
            )
        if any(not item.evidence for item in items):
            return DraftPreviewResult(
                patient_id=self.patient_id,
                status=DraftPreviewStatus.BLOCKED,
                reason="출처가 누락된 추천 항목이 있습니다.",
            )

        refs = tuple(ref for item in items for ref in item.evidence)
        audit = await verify_evidence_refs(refs, self.guideline_search)
        if not audit.can_display_as_official:
            return DraftPreviewResult(
                patient_id=self.patient_id,
                status=DraftPreviewStatus.BLOCKED,
                reason="색인에 역추적되지 않는 인용이 있어 추천 초안을 보류합니다.",
                citation_audit=audit,
            )

        return DraftPreviewResult(
            patient_id=self.patient_id,
            status=DraftPreviewStatus.REQUIRES_DOCTOR_REVIEW,
            reason=(
                "인용 ID는 검증됐지만 임상적 적절성은 미검증입니다. "
                "의료진 판단과 T5 승인 후에만 별도 저장 흐름을 구현해야 합니다."
            ),
            citation_audit=audit,
        )


def bind_patient_tools(
    patient_id: str,
    *,
    patient_data: PatientDataPort,
    guideline_search: GuidelineSearch,
) -> ScopedPatientTools:
    """선택된 환자 ID를 도구 생성 시 묶는다. 모델이 환자를 다시 선택할 수 없다."""
    if not patient_id or not patient_id.strip():
        raise ValueError("patient_id는 비어 있을 수 없습니다")
    return ScopedPatientTools(
        patient_id=patient_id.strip(),
        patient_data=patient_data,
        guideline_search=guideline_search,
    )
