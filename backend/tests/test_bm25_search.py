"""`Bm25GuidelineSearch` v0.2 계약 테스트, 한국어 조사·복합명사 토큰화, 교차언어·역추적 테스트."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.config import Settings
from app.main import create_app
from app.recommender.bm25_search import Bm25GuidelineSearch, tokenize
from app.recommender.rag_sources import GuidelineChunk
from tests.contracts.guideline import GuidelineSearchContract

SAMPLE_CHUNKS: tuple[GuidelineChunk, ...] = (
    GuidelineChunk(
        chunk_id="espen_geriatrics_pdf::R20",
        doc_id="espen_geriatrics",
        artifact_id="espen_geriatrics_pdf",
        section="R20",
        locator="p.12#c1",
        verified_recommendation_no="R20",
        text=(
            "Older adults with malnutrition or at risk should receive food fortification "
            "and oral nutritional supplements providing at least 400 kcal and 30 g/kg protein."
        ),
        source_url=(
            "https://www.espen.org/files/ESPEN-Guidelines/"
            "ESPEN%5Fpractical%5Fguideline%5FClinical%5Fnutrition%5Fand%5Fhydration%5Fin%5Fgeriatrics.pdf"
        ),
        document_title="ESPEN Geriatrics",
        publisher="ESPEN",
        published_year_or_edition="2022",
        actual_source_file="espen-geriatrics/espen-practical-guideline-geriatrics.pdf",
        source_format="pdf",
        language="en",
        file_sha256="a" * 64,
        review_status="approved",
    ),
    GuidelineChunk(
        chunk_id="kjg_elderly_nutrition_2019_pdf::p.4#c1",
        doc_id="kjg_elderly_nutrition_2019",
        artifact_id="kjg_elderly_nutrition_2019_pdf",
        section="p.4#c1",
        locator="p.4#c1",
        verified_recommendation_no=None,
        text=(
            "고령자의 영양 관리에서는 단백질 섭취 부족 시 식사 강화와 경구영양보충을 고려하며 "
            "지나치게 엄격한 치료식은 지양한다."
        ),
        source_url="https://doi.org/10.4166/kjg.2019.73.4.196",
        document_title="대한소화기학회지 고령자의 영양 관리",
        publisher="대한소화기학회",
        published_year_or_edition="2019",
        actual_source_file="kjg-elderly-nutrition-2019/kjg-2019-73-4-196-elderly-nutrition.pdf",
        source_format="pdf",
        language="ko",
        file_sha256="b" * 64,
        review_status="approved",
    ),
    GuidelineChunk(
        chunk_id="khna_pressure_injury_pdf::p.83#c1",
        doc_id="khna_pressure_injury",
        artifact_id="khna_pressure_injury_pdf",
        section="p.83#c1",
        locator="p.83#c1",
        verified_recommendation_no=None,
        text=(
            "욕창이 있는 노인 환자에서 영양 부족 시 고단백 경구영양보충과 "
            "다학제 영양관리팀 의뢰를 권장한다."
        ),
        source_url="https://khna.or.kr/home/data/khna_guide_ebp10.pdf",
        document_title="대한간호협회 욕창 예방·관리 가이드라인",
        publisher="대한간호협회",
        published_year_or_edition="khna_guide_ebp10",
        actual_source_file="khna-pressure-injury/khna-pressure-injury-guideline.pdf",
        source_format="pdf",
        language="ko",
        file_sha256="c" * 64,
        review_status="approved",
    ),
)


class TestBm25GuidelineContract(GuidelineSearchContract):
    """`GuidelineSearchContract` 불변 조건 검증."""

    @pytest.fixture
    def search(self) -> Bm25GuidelineSearch:
        return Bm25GuidelineSearch(SAMPLE_CHUNKS)


def test_bm25_korean_tokenization_particles_compounds_and_clinical_units() -> None:
    tokens = tokenize("욕창을 가진 노인 환자의 경구영양보충과 30 kcal/kg 1.0 g/kg 50% 기준")
    # 조사 제거
    assert "욕창" in tokens
    assert "환자" in tokens
    # 오분절 방지 ('환자'에서 '자'를 잘라 '환'을 만들지 않음)
    assert "환" not in tokens
    # 복합명사 분해
    assert "경구" in tokens
    assert "영양" in tokens
    assert "보충" in tokens
    # 임상 단위 보존
    assert "kcal/kg" in tokens
    assert "g/kg" in tokens
    assert "50%" in tokens

    # 띄어쓰기 복합명사 결합
    spaced_tokens = tokenize("욕창 예방과 식사 강화")
    assert "욕창예방" in spaced_tokens
    assert "식사강화" in spaced_tokens


async def test_bm25_ranks_pressure_injury_and_handles_ko_en_cross_lingual() -> None:
    searcher = Bm25GuidelineSearch(SAMPLE_CHUNKS, enable_bilingual_expand=True)

    ko_hits = await searcher.search("욕창을 앓는 환자 영양 관리 팀 의뢰", limit=3)
    assert len(ko_hits) >= 1
    assert ko_hits[0].doc_id == "khna_pressure_injury"

    # 영문 질의 → 국문 가이드라인
    en_to_ko = await searcher.search("pressure injury multidisciplinary nutrition support", limit=3)
    assert any(h.doc_id == "khna_pressure_injury" for h in en_to_ko)

    # 한국어 질의 → 영문 ESPEN
    ko_to_en = await searcher.search("강화식 경구영양보충", limit=3)
    assert any(h.doc_id == "espen_geriatrics" for h in ko_to_en)


async def test_bm25_reverse_lookup_limits_and_reproducibility() -> None:
    searcher = Bm25GuidelineSearch(SAMPLE_CHUNKS)

    r1 = await searcher.search("노인 단백질 섭취 부족", limit=1)
    r3 = await searcher.search("노인 단백질 섭취 부족", limit=3)
    r3_repeat = await searcher.search("노인 단백질 섭취 부족", limit=3)

    assert len(r1) == 1
    assert r3 == r3_repeat
    assert r1[0] == r3[0]

    resolved = await searcher.resolve_evidence("espen_geriatrics", "R20")
    assert resolved is not None
    assert resolved.section == "R20"
    assert await searcher.resolve_evidence("espen_geriatrics", "R999") is None


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
