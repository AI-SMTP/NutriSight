"""`Bm25GuidelineSearch` 계약 테스트와 BM25 순위·배선 테스트."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.config import Settings
from app.main import create_app
from app.recommender.bm25_search import Bm25GuidelineSearch
from app.recommender.rag_sources import GuidelineChunk
from tests.contracts.guideline import GuidelineSearchContract

SAMPLE_CHUNKS: tuple[GuidelineChunk, ...] = (
    GuidelineChunk(
        chunk_id="espen_geriatrics#p12_c1",
        doc_id="espen_geriatrics",
        section="p.12",
        text=(
            "Older adults with malnutrition or at risk should receive food fortification "
            "and oral nutritional supplements providing at least 400 kcal and 30 g protein."
        ),
        source_url=(
            "https://www.espen.org/files/ESPEN-Guidelines/"
            "ESPEN%5Fpractical%5Fguideline%5FClinical%5Fnutrition%5Fand%5Fhydration%5Fin%5Fgeriatrics.pdf"
        ),
        document_title="ESPEN Geriatrics",
        language="en",
        file_hash="abc123",
    ),
    GuidelineChunk(
        chunk_id="kjg_elderly_nutrition_2019#p4_c1",
        doc_id="kjg_elderly_nutrition_2019",
        section="p.4",
        text=(
            "고령자의 영양 관리에서는 단백질 섭취 부족 시 식사 강화와 경구영양보충을 고려하며 "
            "지나치게 엄격한 치료식은 지양한다."
        ),
        source_url="https://doi.org/10.4166/kjg.2019.73.4.196",
        document_title="대한소화기학회지 고령자의 영양 관리",
        language="ko",
        file_hash="def456",
    ),
    GuidelineChunk(
        chunk_id="khna_pressure_injury#p83_c1",
        doc_id="khna_pressure_injury",
        section="p.83",
        text=(
            "욕창이 있는 노인 환자에서 영양 부족 시 고단백 경구영양보충과 "
            "다학제 영양관리팀 의뢰를 권장한다."
        ),
        source_url="https://khna.or.kr/home/data/khna_guide_ebp10.pdf",
        document_title="대한간호협회 욕창 예방·관리 가이드라인",
        language="ko",
        file_hash="ghi789",
    ),
)


class TestBm25GuidelineContract(GuidelineSearchContract):
    """`GuidelineSearchContract` 불변 조건 검증."""

    @pytest.fixture
    def search(self) -> Bm25GuidelineSearch:
        return Bm25GuidelineSearch(SAMPLE_CHUNKS)


async def test_bm25_ranks_pressure_injury_doc_first_for_pressure_query() -> None:
    searcher = Bm25GuidelineSearch(SAMPLE_CHUNKS)

    hits = await searcher.search("욕창 환자 다학제 영양관리팀 의뢰", limit=3)

    assert len(hits) >= 1
    assert hits[0].doc_id == "khna_pressure_injury"


async def test_bm25_bilingual_expansion_hits_english_espen_chunk() -> None:
    searcher = Bm25GuidelineSearch(SAMPLE_CHUNKS, enable_bilingual_expand=True)

    hits = await searcher.search("강화식 경구영양보충", limit=3)

    assert any(h.doc_id == "espen_geriatrics" for h in hits)


async def test_bm25_returns_empty_for_blank_or_unmatched_query() -> None:
    searcher = Bm25GuidelineSearch(SAMPLE_CHUNKS)

    assert await searcher.search("   ") == ()
    assert await searcher.search("스마트폰 충전 케이블") == ()


def test_wiring_selects_bm25_implementation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RAG_SOURCES_DIR", str(tmp_path))

    app = create_app(Settings(_env_file=None, guideline_search="bm25"))

    assert isinstance(app.state.guideline_search, Bm25GuidelineSearch)
