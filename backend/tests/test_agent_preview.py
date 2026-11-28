"""T5가 아직 없는 상황에서 실행 가능한 RAG↔Agent 미리보기 계약 테스트."""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from app.agent_preview.bridge import (
    DraftPreviewStatus,
    bind_patient_tools,
)
from app.agent_preview.fake_agent import FakeAgentPreview
from app.recommender.fake_guideline import FakeGuidelineSearch
from app.recommender.guideline_types import GuidelineHit
from app.recommender.retrieval_guard import RetrievalStatus, detect_unsupported_scope
from app.services.fake_patient_data import (
    PATIENT_WITH_ACTIVE,
    PATIENT_WITH_FAILED_ONLY,
    SUMMARY_ON,
    FakePatientData,
)
from app.services.ports import EvidenceRef


class _VerifiedSearch:
    async def search(self, query: str, limit: int = 5) -> tuple[GuidelineHit, ...]:
        return (
            GuidelineHit(
                doc_id="approved_demo",
                section="p.1#c1",
                text="모의 평가 문구: 실제 환자 처방에 사용하지 않습니다.",
                source_url="https://example.org/demo",
            ),
        )[:limit]

    async def resolve_evidence(
        self, doc_id: str, section: str
    ) -> GuidelineHit | None:
        hits = await self.search("demo")
        return next(
            (hit for hit in hits if hit.doc_id == doc_id and hit.section == section),
            None,
        )


def _tools(patient_id: str, search: object | None = None):
    return bind_patient_tools(
        patient_id,
        patient_data=FakePatientData(),
        guideline_search=search if search is not None else FakeGuidelineSearch(),
    )


async def test_bound_patient_id_and_independent_summaries() -> None:
    first = _tools(PATIENT_WITH_ACTIVE)
    second = _tools(PATIENT_WITH_FAILED_ONLY)
    first_summary = await first.get_intake_summary(days=7, on=SUMMARY_ON)
    second_summary = await second.get_intake_summary(days=7, on=SUMMARY_ON)

    assert first_summary.patient_id == PATIENT_WITH_ACTIVE
    assert second_summary.patient_id == PATIENT_WITH_FAILED_ONLY
    assert len(first_summary.daily) > 0
    assert second_summary.daily == ()


async def test_known_unsafe_ckd_queries_are_deferred_without_hits() -> None:
    tools = _tools(PATIENT_WITH_ACTIVE, _VerifiedSearch())
    for query in (
        "미기록 끼니가 있고 단백질 목표가 미등록인 노인 만성콩팥병 G3b 환자의 단백질 처방 수치",
        "CKD G3b 노인 단백질 섭취량 몇 g/kg/day로 하면 돼?",
        "만성콩팥병 3b 환자 단백질 몇 g/kg이 적절해?",
    ):
        assert detect_unsupported_scope(query) is not None
        result = await tools.search_guidelines(query)
        assert result.status is RetrievalStatus.UNSUPPORTED_SCOPE
        assert result.hits == ()
        assert result.requires_clinical_review is True


async def test_normal_question_remains_searchable() -> None:
    tools = _tools(PATIENT_WITH_ACTIVE, _VerifiedSearch())
    result = await tools.search_guidelines("고령자 영양 평가와 식사 강화 주의사항")
    assert result.status is RetrievalStatus.FOUND
    assert len(result.hits) == 1


async def test_fake_citations_block_prescription_preview_without_port_write() -> None:
    port = FakePatientData()
    tools = bind_patient_tools(
        PATIENT_WITH_ACTIVE, patient_data=port, guideline_search=FakeGuidelineSearch()
    )
    card = await port.get_recommendation(PATIENT_WITH_ACTIVE)
    assert card is not None
    preview = await tools.draft_prescription_preview(card.items)
    assert preview.status is DraftPreviewStatus.BLOCKED
    assert preview.saved is False
    assert (await port.get_recommendation(PATIENT_WITH_ACTIVE)) == card


async def test_verified_ref_only_requests_review_and_does_not_write() -> None:
    port = FakePatientData()
    tools = bind_patient_tools(
        PATIENT_WITH_ACTIVE, patient_data=port, guideline_search=_VerifiedSearch()
    )
    card = await port.get_recommendation(PATIENT_WITH_ACTIVE)
    assert card is not None
    clean_item = replace(
        card.items[0], evidence=(EvidenceRef("approved_demo", "p.1#c1"),)
    )
    preview = await tools.draft_prescription_preview((clean_item,))
    assert preview.status is DraftPreviewStatus.REQUIRES_DOCTOR_REVIEW
    assert preview.saved is False
    assert preview.citation_audit is not None
    assert preview.citation_audit.all_verified
    assert (await port.get_recommendation(PATIENT_WITH_ACTIVE)) == card


async def test_fake_agent_sse_contract_and_no_card_mutation() -> None:
    tools = _tools(PATIENT_WITH_ACTIVE, _VerifiedSearch())
    events = [event async for event in FakeAgentPreview(tools).stream(
        "고령자 영양 평가", on=date(2026, 11, 26)
    )]
    names = [event.name for event in events]
    assert names == [
        "tool_start", "tool_end", "tool_start", "tool_end", "token", "done"
    ]
    assert "card_updated" not in names
    assert events[3].data["citations_verified"] is True
    assert events[-1].data["status"] == "read_only_preview"
    assert all(event.to_sse().endswith("\n\n") for event in events)
    assert all("NS02" not in event.to_sse() for event in events)


async def test_invalid_patient_and_no_cross_patient_tool_input() -> None:
    tools = _tools("nonexistent_patient", _VerifiedSearch())
    events = [event async for event in FakeAgentPreview(tools).stream(
        "고령자 영양", on=SUMMARY_ON
    )]
    assert [event.name for event in events] == [
        "tool_start", "error", "done"
    ]
    with pytest.raises(ValueError):
        bind_patient_tools("", patient_data=FakePatientData(),
                           guideline_search=FakeGuidelineSearch())


async def test_fake_guideline_hits_are_never_presented_as_official() -> None:
    tools = _tools(PATIENT_WITH_ACTIVE)
    events = [
        event
        async for event in FakeAgentPreview(tools).stream(
            "고령자 식사 강화", on=SUMMARY_ON
        )
    ]
    search_done = next(
        event for event in events
        if event.name == "tool_end" and event.data["tool"] == "search_guidelines"
    )
    assert search_done.data["citations_verified"] is False
    token = next(event.data["text"] for event in events if event.name == "token")
    assert "검증되지 않았습니다" in token
