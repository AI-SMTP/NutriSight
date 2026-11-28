"""RAG v0.3 고도화(P0·P1·P2) 재현 및 회귀 테스트.

- P0: NS09-B CKD 병기별 처방 수치 등 미지원 범위 안전 보류 + NS09-A/정상 질의 비간섭 검증
- P1: GLIM JPEN XML `<table-wrap>` 표(`≤50%`) 추출 + 기존 `xml:s*#c*` EvidenceRef 안정성 보존 검증
- P2: Fake 카드 `R20`/`R23` vs 실제 승인 색인 `EvidenceRef` 무결성 구분·차단 검증
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.recommender.bm25_search import Bm25GuidelineSearch
from app.recommender.chroma_search import GuidelineSearchError
from app.recommender.fake_guideline import FakeGuidelineSearch
from app.recommender.guideline_types import GuidelineHit
from app.recommender.rag_sources import (
    DEFAULT_SOURCES_DIR,
    compute_file_sha256,
    load_guideline_chunks,
)
from app.recommender.retrieval_guard import (
    CitationStatus,
    RetrievalStatus,
    safe_search_guidelines,
    verify_evidence_refs,
)
from app.services.ports import EvidenceRef
from tests.test_bm25_search import SAMPLE_CHUNKS


class _FailingSearch:
    async def search(self, query: str, limit: int = 5) -> tuple[GuidelineHit, ...]:
        raise GuidelineSearchError("Simulated Chroma/OpenAI outage")


# ---------------------------------------------------------------------------
# P0: 근거 부족·미지원 범위(NS09-B 등)·오류 안전 처리 및 정상 검색 비간섭
# ---------------------------------------------------------------------------


async def test_p0_ns09_b_and_drug_protocol_return_unsupported_scope_without_hits() -> None:
    searcher = Bm25GuidelineSearch(SAMPLE_CHUNKS)

    ns09_b = await safe_search_guidelines(
        searcher,
        "미기록 끼니가 있고 단백질 목표가 미등록인 노인 만성콩팥병 G3b 환자의 단백질 처방 수치",
        limit=3,
    )
    assert ns09_b.status is RetrievalStatus.UNSUPPORTED_SCOPE
    assert ns09_b.hits == ()
    assert ns09_b.requires_clinical_review is True
    assert ns09_b.abstain_reason is not None

    ind_neg_01 = await safe_search_guidelines(
        searcher,
        "투석하지 않는 만성콩팥병 G3b 노인의 병기별 단백질 처방량과 증량 한도는 얼마인가?",
        limit=3,
    )
    assert ind_neg_01.status is RetrievalStatus.UNSUPPORTED_SCOPE
    assert ind_neg_01.hits == ()

    ind_neg_02 = await safe_search_guidelines(
        searcher,
        "노인 영양불량 환자가 패혈증 치료 시 사용할 첫 항생제와 투여 용량은?",
        limit=3,
    )
    assert ind_neg_02.status is RetrievalStatus.UNSUPPORTED_SCOPE
    assert ind_neg_02.hits == ()


async def test_p0_normal_queries_and_ns09_a_caution_query_are_not_blocked() -> None:
    searcher = Bm25GuidelineSearch(SAMPLE_CHUNKS)

    # NS09-A: 일반 주의사항/영양 평가 질의는 처방 수치 요청이 아니므로 정상 검색되어야 한다.
    ns09_a = await safe_search_guidelines(
        searcher,
        "고령자 만성콩팥병 영양 평가 개별 목표 주의사항",
        limit=3,
    )
    assert ns09_a.status is RetrievalStatus.FOUND
    assert len(ns09_a.hits) >= 1
    assert ns09_a.requires_clinical_review is False

    # 정상 노인 영양 강화 질의(NS07-A)도 그대로 동작해야 한다.
    ns07_a = await safe_search_guidelines(
        searcher,
        "고령자 씹기 불편 체중 감소 식사 강화 경구영양보충",
        limit=3,
    )
    assert ns07_a.status is RetrievalStatus.FOUND
    assert len(ns07_a.hits) >= 1


async def test_p0_empty_result_and_search_error_transition_safely() -> None:
    searcher = Bm25GuidelineSearch(SAMPLE_CHUNKS)

    blank = await safe_search_guidelines(searcher, "   ", limit=3)
    assert blank.status is RetrievalStatus.NO_EVIDENCE
    assert blank.hits == ()
    assert blank.requires_clinical_review is True

    no_match = await safe_search_guidelines(searcher, "엑셀 피벗 테이블 빈 셀 세기", limit=3)
    assert no_match.status is RetrievalStatus.NO_EVIDENCE
    assert no_match.hits == ()
    assert no_match.requires_clinical_review is True

    failed = await safe_search_guidelines(_FailingSearch(), "노인 단백질 섭취 부족", limit=3)
    assert failed.status is RetrievalStatus.SEARCH_ERROR
    assert failed.hits == ()
    assert failed.requires_clinical_review is True
    assert failed.error_detail is not None and "GuidelineSearchError" in failed.error_detail

    with pytest.raises(ValueError):
        await safe_search_guidelines(searcher, "노인 영양", limit=0)


# ---------------------------------------------------------------------------
# P1: GLIM XML `<table-wrap>` 표 추출 및 기존 `xml:s*#c*` 안정성 보존
# ---------------------------------------------------------------------------


def _write_glim_like_xml_with_table(sources_dir: Path, manifest_path: Path) -> None:
    glim_dir = sources_dir / "glim-2025"
    glim_dir.mkdir(parents=True, exist_ok=True)
    xml_path = glim_dir / "glim-5-year-update-2025-jpen.xml"
    xml_path.write_text(
        """<article><body>
        <sec><title>Reduced food intake/assimilation</title>
        <p>The original GLIM paper stated that this criterion is fulfilled by a food intake of
        &lt;50% of calculated energy requirement for &gt;1 week.</p>
        </sec>
        <table-wrap id="jpen2756-tbl-0005">
          <label>Table 5</label>
          <caption>
            <p>Summary of the phenotypic and etiologic criteria for malnutrition.</p>
          </caption>
          <table>
            <thead><tr><th>Phenotypic criteria</th><th>Etiologic criteria</th></tr></thead>
            <tbody>
              <tr>
                <td>&gt;5% weight loss within past 6 mo</td>
                <td>≤50% of ERs for &gt;1 week, or any reduction for &gt;2 weeks</td>
              </tr>
            </tbody>
          </table>
          <table-wrap-foot><p>ERs, energy requirements.</p></table-wrap-foot>
        </table-wrap>
        </body></article>""",
        encoding="utf-8",
    )
    sha = compute_file_sha256(xml_path)
    manifest_path.write_text(
        json.dumps(
            {
                "manifest_version": "1.0",
                "artifacts": [
                    {
                        "artifact_id": "glim_2025_jpen_xml",
                        "doc_id": "glim_2025",
                        "document_title": "GLIM 5-year update (2025) JPEN XML",
                        "publisher": "GLIM / JPEN",
                        "published_year_or_edition": "2025",
                        "relative_path": "glim-2025/glim-5-year-update-2025-jpen.xml",
                        "format": "xml",
                        "source_url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC12053077/",
                        "language": "en",
                        "expected_sha256": sha,
                        "review_status": "approved",
                        "reviewed_at": "2026-11-27",
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


async def test_p1_xml_table_wrap_extraction_preserves_section_ids_and_indexes_50pct(
    tmp_path: Path,
) -> None:
    sources_dir = tmp_path / "sources"
    manifest_path = tmp_path / "manifest.json"
    _write_glim_like_xml_with_table(sources_dir, manifest_path)

    chunks, _ = load_guideline_chunks(sources_dir, manifest_path=manifest_path)
    sections = [c.section for c in chunks]

    # 1) 기존 `<sec>` 청크 ID는 변하지 않고 보존된다.
    assert "xml:s1#c1" in sections
    # 2) 표 청크는 별도 네임스페이스 `xml:tbl:<id>#c1`로 추가된다.
    assert "xml:tbl:jpen2756-tbl-0005#c1" in sections
    assert len(set(sections)) == len(sections)

    tbl_chunk = next(c for c in chunks if c.section == "xml:tbl:jpen2756-tbl-0005#c1")
    assert "≤50% of ERs for >1 week" in tbl_chunk.text
    assert "ERs, energy requirements." in tbl_chunk.text

    # 3) BM25 검색 및 `resolve_evidence` 역추적이 정상 동작한다.
    searcher = Bm25GuidelineSearch(chunks)
    hits = await searcher.search("GLIM Table 5 ≤50% ERs >1 week etiologic criteria", limit=3)
    assert any(h.section == "xml:tbl:jpen2756-tbl-0005#c1" for h in hits)
    resolved = await searcher.resolve_evidence("glim_2025", "xml:tbl:jpen2756-tbl-0005#c1")
    assert resolved is not None
    assert "≤50%" in resolved.text


def test_p1_real_glim_xml_preserves_63_sections_and_extracts_table5_if_present() -> None:
    glim_xml = DEFAULT_SOURCES_DIR / "glim-2025" / "glim-5-year-update-2025-jpen.xml"
    if not glim_xml.exists():
        pytest.skip("로컬 GLIM JPEN XML 원문 미배치 환경")

    chunks, _ = load_guideline_chunks(DEFAULT_SOURCES_DIR)
    glim_chunks = [c for c in chunks if c.doc_id == "glim_2025"]
    sec_chunks = [c for c in glim_chunks if c.section.startswith("xml:s")]
    tbl_chunks = [c for c in glim_chunks if c.section.startswith("xml:tbl:")]

    # 기존 63개 섹션 청크 보존 + Table 1~5 표 청크 추가 확인
    assert len(sec_chunks) == 63
    assert len(tbl_chunks) >= 5
    tbl5_chunks = [c for c in tbl_chunks if c.section.startswith("xml:tbl:jpen2756-tbl-0005#")]
    assert tbl5_chunks
    assert any("≤50%" in c.text for c in tbl5_chunks)


# ---------------------------------------------------------------------------
# P2: 인용 무결성 — Fake R20/R23 vs 실제 승인 색인 EvidenceRef 구분
# ---------------------------------------------------------------------------


async def test_p2_verify_evidence_refs_blocks_fake_ids_and_accepts_verified_ids() -> None:
    real_like_searcher = Bm25GuidelineSearch(SAMPLE_CHUNKS)

    # 1) 실제 색인에 있는 ID(R20)와 없는 모의 ID(R23, 단백질 섭취)를 정확히 구분
    mixed_refs = (
        EvidenceRef(doc_id="espen_geriatrics", section="R20"),
        EvidenceRef(doc_id="espen_geriatrics", section="R23"),
        EvidenceRef(doc_id="kjg_elderly_nutrition_2019", section="단백질 섭취"),
    )
    mixed_report = await verify_evidence_refs(mixed_refs, real_like_searcher)
    assert mixed_report.verified_count == 1
    assert mixed_report.unverified_count == 2
    assert mixed_report.all_verified is False
    assert mixed_report.can_display_as_official is False
    assert mixed_report.checks[0].status is CitationStatus.VERIFIED_OFFICIAL
    assert mixed_report.checks[1].status is CitationStatus.UNVERIFIED_OR_MOCK
    assert mixed_report.checks[2].status is CitationStatus.UNVERIFIED_OR_MOCK

    # 2) 실제 검색 결과에서 나온 ID만 넣으면 모두 VERIFIED_OFFICIAL
    hits = await real_like_searcher.search("욕창 고단백 영양관리팀", limit=2)
    verified_refs = tuple(EvidenceRef(doc_id=h.doc_id, section=h.section) for h in hits)
    ok_report = await verify_evidence_refs(verified_refs, real_like_searcher)
    assert ok_report.all_verified is True
    assert ok_report.can_display_as_official is True
    assert all(c.status is CitationStatus.VERIFIED_OFFICIAL for c in ok_report.checks)

    # 3) FakeGuidelineSearch 자체는 역조회를 지원하지 않으므로 공식 근거로 표시 금지
    fake_report = await verify_evidence_refs(mixed_refs, FakeGuidelineSearch())
    assert fake_report.can_display_as_official is False
    assert all(c.status is CitationStatus.INDEX_UNAVAILABLE for c in fake_report.checks)
