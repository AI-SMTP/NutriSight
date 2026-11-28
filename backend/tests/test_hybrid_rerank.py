"""Hybrid Search(BM25 + Dense + RRF) 및 Reranker 계약·안전성·폴백 회귀 테스트.

모든 테스트는 외부 유료 API 호출 없이 로컬 인메모리 픽스처로 실행된다.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path

import pytest

from app.agent_preview.bridge import bind_patient_tools
from app.agent_preview.fake_agent import FakeAgentPreview
from app.config import Settings
from app.recommender.bm25_search import Bm25GuidelineSearch
from app.recommender.guideline_types import GuidelineHit, GuidelineSearch
from app.recommender.hybrid_search import (
    HybridGuidelineSearch,
    HybridStatus,
    fuse_rrf,
)
from app.recommender.rag_sources import GuidelineChunk
from app.recommender.reranker import (
    OnnxBgeReranker,
    RerankedGuidelineSearch,
    RerankResult,
    RerankScore,
    RerankStatus,
)
from app.recommender.retrieval_guard import (
    CitationStatus,
    RetrievalStatus,
    safe_search_guidelines,
    verify_evidence_refs,
)
from app.services.fake_patient_data import SUMMARY_ON, FakePatientData
from app.services.ports import EvidenceRef
from app.wiring import GUIDELINE_SEARCHES
from scripts.eval_retrieval_upgrade import evaluate_passage_groups, matches_gold_ref
from tests.contracts.guideline import GuidelineSearchContract
from tests.test_rag_scope_smoke_18 import ALLOWED_INFORMATION_QUERIES, UNSUPPORTED_QUERIES


def _sample_chunks() -> list[GuidelineChunk]:
    return [
        GuidelineChunk(
            chunk_id="espen_geriatrics::p.10#c1",
            doc_id="espen_geriatrics",
            artifact_id="espen_geriatrics",
            section="p.10#c1",
            locator="p.10",
            verified_recommendation_no=None,
            text=(
                "Older persons with malnutrition or at risk of malnutrition should be offered "
                "oral nutritional supplements (ONS) providing at least 400 kcal/day and "
                "30 g/day of protein."
            ),
            source_url="https://espen.org/geriatrics",
            document_title="ESPEN Geriatrics",
            publisher="ESPEN",
            published_year_or_edition="2019",
            actual_source_file="espen.pdf",
            source_format="pdf",
            language="en",
            file_sha256="a" * 64,
            review_status="approved",
        ),
        GuidelineChunk(
            chunk_id="glim_2025::xml:tbl:jpen2756-tbl-0005#c2",
            doc_id="glim_2025",
            artifact_id="glim_2025",
            section="xml:tbl:jpen2756-tbl-0005#c2",
            locator="xml:tbl:jpen2756-tbl-0005",
            verified_recommendation_no=None,
            text=(
                "Reduced food intake ≤50% of energy requirements for >1 week, "
                "or any reduction for >2 weeks."
            ),
            source_url="https://glim.org/2025",
            document_title="GLIM 2025",
            publisher="JPEN",
            published_year_or_edition="2025",
            actual_source_file="glim.xml",
            source_format="xml",
            language="en",
            file_sha256="b" * 64,
            review_status="approved",
        ),
        GuidelineChunk(
            chunk_id="khna_pressure_injury::p.48#c1",
            doc_id="khna_pressure_injury",
            artifact_id="khna_pressure_injury",
            section="p.48#c1",
            locator="p.48",
            verified_recommendation_no=None,
            text=(
                "욕창 예방 및 관리를 위해 영양불량 위험이 있는 노인 환자에게 "
                "식사 강화와 고단백 경구영양보충을 고려한다."
            ),
            source_url="https://khna.or.kr/pi",
            document_title="KHNA Pressure Injury",
            publisher="KHNA",
            published_year_or_edition="2023",
            actual_source_file="khna.pdf",
            source_format="pdf",
            language="ko",
            file_sha256="c" * 64,
            review_status="approved",
        ),
        GuidelineChunk(
            chunk_id="kjg_elderly_nutrition_2019::p.5#c1",
            doc_id="kjg_elderly_nutrition_2019",
            artifact_id="kjg_elderly_nutrition_2019",
            section="p.5#c1",
            locator="p.5",
            verified_recommendation_no=None,
            text=(
                "고령자 만성콩팥병 영양 평가 시 개별 목표를 확인하고 "
                "식이상담 의사소통 주의사항을 준수한다."
            ),
            source_url="https://kjg.or.kr/2019",
            document_title="KJG Elderly Nutrition",
            publisher="KJG",
            published_year_or_edition="2019",
            actual_source_file="kjg.pdf",
            source_format="pdf",
            language="ko",
            file_sha256="d" * 64,
            review_status="approved",
        ),
    ]


class _StubDenseSearch:
    """네트워크 없이 고정된 후보 또는 오류를 반환하는 테스트용 Dense 어댑터."""

    def __init__(
        self,
        hits: Sequence[GuidelineHit] = (),
        *,
        fail_with: Exception | None = None,
    ) -> None:
        self._hits = tuple(hits)
        self._fail_with = fail_with
        self._index = {(h.doc_id, h.section): h for h in self._hits}
        self.calls: list[str] = []

    async def search(self, query: str, limit: int = 5) -> tuple[GuidelineHit, ...]:
        if limit < 1:
            raise ValueError("limit은 1 이상이어야 한다")
        self.calls.append(query)
        if self._fail_with is not None:
            raise self._fail_with
        if not query.strip():
            return ()
        return self._hits[:limit]

    async def resolve_evidence(
        self, doc_id: str, section: str, *, version_id: str | None = None
    ) -> GuidelineHit | None:
        return self._index.get((doc_id.strip(), section.strip()))


class _KeywordStubReranker:
    """테스트용 결정적 Reranker (원문 변조 없이 키워드 일치 수로 재정렬)."""

    model_name = "stub-keyword-reranker"

    def __init__(self, *, preferred_section: str | None = None, fail: bool = False) -> None:
        self._preferred_section = preferred_section
        self._fail = fail

    async def rerank(
        self,
        query: str,
        candidates: Sequence[GuidelineHit],
        *,
        limit: int = 3,
    ) -> RerankResult:
        if self._fail:
            raise RuntimeError("simulated reranker crash")
        scored = []
        for idx, hit in enumerate(candidates, start=1):
            score = 0.99 if hit.section == self._preferred_section else max(0.1, 0.8 - 0.1 * idx)
            scored.append(RerankScore(hit=hit, score=score, original_rank=idx, truncated=False))
        scored.sort(key=lambda item: (-item.score, item.original_rank))
        top = tuple(scored[:limit])
        return RerankResult(
            status=RerankStatus.OK,
            hits=tuple(item.hit for item in top),
            scored=top,
            model_name=self.model_name,
        )


class _FabricatingReranker:
    """원본 후보에 없는 가짜 인용을 끼워 넣으려 시도하는 악성/버그 Reranker 테스트 더블."""

    model_name = "malicious-fabricating-reranker"

    async def rerank(
        self,
        query: str,
        candidates: Sequence[GuidelineHit],
        *,
        limit: int = 3,
    ) -> RerankResult:
        fake = GuidelineHit(
            doc_id="espen_geriatrics",
            section="R20",
            text="fabricated citation",
            source_url="https://example.invalid/fake",
        )
        return RerankResult(
            status=RerankStatus.OK,
            hits=(fake,),
            scored=(RerankScore(hit=fake, score=1.0, original_rank=1),),
            model_name=self.model_name,
        )


class TestHybridGuidelineSearchContract(GuidelineSearchContract):
    @pytest.fixture
    def search(self) -> GuidelineSearch:
        chunks = _sample_chunks()
        bm25 = Bm25GuidelineSearch(chunks)
        dense_hits = [GuidelineHit(c.doc_id, c.section, c.text, c.source_url) for c in chunks]
        return HybridGuidelineSearch(
            bm25_search=bm25,
            dense_search=_StubDenseSearch(dense_hits),
        )


class TestRerankedGuidelineSearchContract(GuidelineSearchContract):
    @pytest.fixture
    def search(self) -> GuidelineSearch:
        chunks = _sample_chunks()
        bm25 = Bm25GuidelineSearch(chunks)
        dense_hits = [GuidelineHit(c.doc_id, c.section, c.text, c.source_url) for c in chunks]
        hybrid = HybridGuidelineSearch(
            bm25_search=bm25,
            dense_search=_StubDenseSearch(dense_hits),
        )
        return RerankedGuidelineSearch(
            base_search=hybrid,
            reranker=_KeywordStubReranker(),
        )


def test_fuse_rrf_math_dedup_and_deterministic_tie_break() -> None:
    h_a = GuidelineHit("doc_a", "s1", "text a", "https://a.example")
    h_b = GuidelineHit("doc_b", "s1", "text b", "https://b.example")
    h_c = GuidelineHit("doc_c", "s1", "text c", "https://c.example")

    # h_b appears in both BM25(#2) and Dense(#1) -> 1/62 + 1/61 > single source 1/61
    candidates = fuse_rrf([h_a, h_b], [h_b, h_c], rrf_k=60)
    keys = [(c.hit.doc_id, c.hit.section) for c in candidates]
    assert keys[0] == ("doc_b", "s1")
    assert candidates[0].bm25_rank == 2
    assert candidates[0].dense_rank == 1
    assert candidates[0].rrf_score == round(1.0 / 62 + 1.0 / 61, 8)
    # h_a (#1 BM25 = 1/61) vs h_c (#2 Dense = 1/62)
    assert keys[1] == ("doc_a", "s1")
    assert keys[2] == ("doc_c", "s1")

    # Tie-breaking: h_a (#1 BM25 = 1/61) vs h_c (#1 Dense = 1/61) -> doc_a before doc_c
    tied = fuse_rrf([h_a], [h_c], rrf_k=60)
    assert [(c.hit.doc_id, c.hit.section) for c in tied] == [("doc_a", "s1"), ("doc_c", "s1")]


async def test_hybrid_dense_failure_marks_degraded_fallback_explicitly(
    caplog: pytest.LogCaptureFixture,
) -> None:
    chunks = _sample_chunks()
    bm25 = Bm25GuidelineSearch(chunks)
    failing_dense = _StubDenseSearch(fail_with=RuntimeError("openai timeout"))
    hybrid = HybridGuidelineSearch(
        bm25_search=bm25,
        dense_search=failing_dense,
        fallback_to_bm25_on_dense_error=True,
    )

    with caplog.at_level(logging.WARNING):
        res = await hybrid.search_with_details("욕창 예방 고단백 경구영양보충", limit=3)

    assert res.status == HybridStatus.DEGRADED_BM25_FALLBACK
    assert res.dense_error is not None and "openai timeout" in res.dense_error
    assert len(res.hits) >= 1
    assert any("BM25 fallback" in rec.message for rec in caplog.records)


async def test_hybrid_respects_dense_empty_oos_rejection() -> None:
    chunks = _sample_chunks()
    bm25 = Bm25GuidelineSearch(chunks)
    empty_dense = _StubDenseSearch(hits=())
    hybrid = HybridGuidelineSearch(
        bm25_search=bm25,
        dense_search=empty_dense,
        require_dense_hit_when_ok=True,
    )

    res = await hybrid.search_with_details("욕창 예방 고단백 경구영양보충", limit=3)
    assert res.status == HybridStatus.OK
    assert res.hits == ()
    assert res.dense_count == 0
    assert res.bm25_count >= 1


async def test_hybrid_dense_failure_propagates_to_search_error_when_fallback_disabled() -> None:
    chunks = _sample_chunks()
    bm25 = Bm25GuidelineSearch(chunks)
    failing_dense = _StubDenseSearch(fail_with=RuntimeError("dense down"))
    hybrid = HybridGuidelineSearch(
        bm25_search=bm25,
        dense_search=failing_dense,
        fallback_to_bm25_on_dense_error=False,
    )

    safe_res = await safe_search_guidelines(hybrid, "욕창 예방 식사 강화", limit=3)
    assert safe_res.status == RetrievalStatus.SEARCH_ERROR
    assert safe_res.hits == ()
    assert safe_res.requires_clinical_review is True


async def test_onnx_reranker_missing_model_falls_back_with_rerank_unavailable(
    tmp_path: Path,
) -> None:
    chunks = _sample_chunks()
    hits = [GuidelineHit(c.doc_id, c.section, c.text, c.source_url) for c in chunks]
    reranker = OnnxBgeReranker(model_dir=tmp_path / "nonexistent_model")
    result = await reranker.rerank("노인 영양불량 ONS", hits, limit=2)

    assert result.status == RerankStatus.RERANK_UNAVAILABLE
    assert result.fallback_reason is not None and "RERANK_UNAVAILABLE" in result.fallback_reason
    assert result.hits == tuple(hits[:2])


async def test_reranked_search_reorders_preserves_immutability_and_blocks_fabrication() -> None:
    chunks = _sample_chunks()
    hits = [GuidelineHit(c.doc_id, c.section, c.text, c.source_url) for c in chunks]
    base = _StubDenseSearch(hits)

    # 1) Normal reorder promotes preferred section without mutating fields
    reranked = RerankedGuidelineSearch(
        base_search=base,
        reranker=_KeywordStubReranker(preferred_section="xml:tbl:jpen2756-tbl-0005#c2"),
    )
    res = await reranked.search_with_details("GLIM 50% 섭취 감소", limit=2)
    assert res.status == RerankStatus.OK
    assert res.hits[0] == hits[1]
    assert "≤50%" in res.hits[0].text

    # 2) Crashing reranker falls back cleanly
    crashing = RerankedGuidelineSearch(
        base_search=base,
        reranker=_KeywordStubReranker(fail=True),
    )
    crash_res = await crashing.search_with_details("GLIM 50% 섭취 감소", limit=2)
    assert crash_res.status == RerankStatus.RERANK_UNAVAILABLE
    assert crash_res.hits == tuple(hits[:2])

    # 3) Fabricating reranker is blocked and falls back to verified 1st-stage hits
    guarded = RerankedGuidelineSearch(
        base_search=base,
        reranker=_FabricatingReranker(),
    )
    guard_res = await guarded.search_with_details("ONS 400 kcal", limit=2)
    assert guard_res.status == RerankStatus.RERANK_UNAVAILABLE
    assert guard_res.hits == tuple(hits[:2])
    assert all(h.section != "R20" for h in guard_res.hits)


@pytest.mark.parametrize("query", UNSUPPORTED_QUERIES)
async def test_hybrid_rerank_blocks_all_9_unsafe_ckd_drug_queries(query: str) -> None:
    chunks = _sample_chunks()
    bm25 = Bm25GuidelineSearch(chunks)
    dense = _StubDenseSearch(
        [GuidelineHit(c.doc_id, c.section, c.text, c.source_url) for c in chunks]
    )
    hybrid = HybridGuidelineSearch(bm25_search=bm25, dense_search=dense)
    reranked = RerankedGuidelineSearch(base_search=hybrid, reranker=_KeywordStubReranker())

    res = await safe_search_guidelines(reranked, query, limit=3)
    assert res.status == RetrievalStatus.UNSUPPORTED_SCOPE
    assert res.hits == ()
    assert res.requires_clinical_review is True
    assert dense.calls == []  # Unsafe queries must be blocked BEFORE touching retrieval


@pytest.mark.parametrize("query", ALLOWED_INFORMATION_QUERIES)
async def test_hybrid_rerank_does_not_overblock_9_normal_queries(query: str) -> None:
    chunks = _sample_chunks()
    bm25 = Bm25GuidelineSearch(chunks)
    dense = _StubDenseSearch(
        [GuidelineHit(c.doc_id, c.section, c.text, c.source_url) for c in chunks]
    )
    hybrid = HybridGuidelineSearch(bm25_search=bm25, dense_search=dense)
    reranked = RerankedGuidelineSearch(base_search=hybrid, reranker=_KeywordStubReranker())

    res = await safe_search_guidelines(reranked, query, limit=3)
    assert res.status == RetrievalStatus.FOUND
    assert len(res.hits) >= 1


async def test_hybrid_rerank_citation_integrity_blocks_fake_r20_r23_and_isolates_patients() -> None:
    chunks = _sample_chunks()
    bm25 = Bm25GuidelineSearch(chunks)
    dense = _StubDenseSearch(
        [GuidelineHit(c.doc_id, c.section, c.text, c.source_url) for c in chunks]
    )
    hybrid = HybridGuidelineSearch(bm25_search=bm25, dense_search=dense)
    reranked = RerankedGuidelineSearch(base_search=hybrid, reranker=_KeywordStubReranker())

    # Fake R20/R23 blocked
    fake_audit = await verify_evidence_refs(
        [
            EvidenceRef(doc_id="espen_geriatrics", section="R20"),
            EvidenceRef(doc_id="espen_geriatrics", section="R23"),
        ],
        reranked,
    )
    assert fake_audit.can_display_as_official is False
    assert fake_audit.verified_count == 0
    assert all(c.status == CitationStatus.UNVERIFIED_OR_MOCK for c in fake_audit.checks)

    # Real approved ID verified
    real_audit = await verify_evidence_refs(
        [EvidenceRef(doc_id="glim_2025", section="xml:tbl:jpen2756-tbl-0005#c2")],
        reranked,
    )
    assert real_audit.can_display_as_official is True
    assert real_audit.verified_count == 1

    # Patient NS01 / NS02 isolation & read-only recommendation card preservation
    pdata = FakePatientData()
    ns01_before = await pdata.get_recommendation("NS01")
    ns02_before = await pdata.get_recommendation("NS02")
    tools_ns01 = bind_patient_tools("NS01", patient_data=pdata, guideline_search=reranked)
    tools_ns02 = bind_patient_tools("NS02", patient_data=pdata, guideline_search=reranked)
    events_ns01 = [
        ev
        async for ev in FakeAgentPreview(tools_ns01).stream(
            "욕창 예방과 식사 강화 가이드라인 근거를 알려줘", on=SUMMARY_ON
        )
    ]
    events_ns02 = [
        ev
        async for ev in FakeAgentPreview(tools_ns02).stream(
            "노인 영양불량 경구영양보충 기준을 알려줘", on=SUMMARY_ON
        )
    ]
    assert any(ev.data.get("patient_id") == "NS01" for ev in events_ns01)
    assert all(ev.data.get("patient_id") != "NS02" for ev in events_ns01)
    assert any(ev.data.get("patient_id") == "NS02" for ev in events_ns02)
    assert all(ev.data.get("patient_id") != "NS01" for ev in events_ns02)
    assert await pdata.get_recommendation("NS01") == ns01_before
    assert await pdata.get_recommendation("NS02") == ns02_before


def test_glim_table5_label_mapping_before_and_after() -> None:
    gold = ("glim_2025", "table:jpen2756-tbl-0005")
    xml_hit = ("glim_2025", "xml:tbl:jpen2756-tbl-0005#c2")

    assert matches_gold_ref(xml_hit, gold, apply_glim_table5_mapping=False) is False
    assert matches_gold_ref(xml_hit, gold, apply_glim_table5_mapping=True) is True

    groups = [[["glim_2025", "table:jpen2756-tbl-0005"]]]
    cov_before, total, all_before = evaluate_passage_groups(
        [xml_hit], groups, apply_glim_table5_mapping=False
    )
    cov_after, _, all_after = evaluate_passage_groups(
        [xml_hit], groups, apply_glim_table5_mapping=True
    )
    assert (cov_before, total, all_before) == (0, 1, False)
    assert (cov_after, total, all_after) == (1, 1, True)


def test_wiring_registers_hybrid_without_changing_default_fake() -> None:
    assert Settings().guideline_search == "fake"
    assert "hybrid" in GUIDELINE_SEARCHES
    assert "hybrid_rerank" in GUIDELINE_SEARCHES


@pytest.mark.parametrize("mode", ["hybrid", "hybrid_rerank"])
def test_wiring_hybrid_and_rerank_fail_closed_when_approved_sources_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    from app.config import ConfigError
    from app.main import create_app

    monkeypatch.setenv("RAG_SOURCES_DIR", str(tmp_path))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(ConfigError, match="원문 파일 누락"):
        create_app(Settings(_env_file=None, guideline_search=mode))
