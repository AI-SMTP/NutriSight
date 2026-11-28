"""`Bm25GuidelineSearch` v0.2 계약 테스트, 한국어 조사·복합명사 토큰화, 교차언어·역추적 테스트."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.config import ConfigError, Settings
from app.main import create_app
from app.recommender.bm25_search import Bm25GuidelineSearch, tokenize
from app.recommender.fake_guideline import FakeGuidelineSearch
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
    spaced_tokens = tokenize("욕창 예방과 식사 강화 및 인지 저하 식욕 저하 수분 섭취")
    assert "욕창예방" in spaced_tokens
    assert "식사강화" in spaced_tokens
    assert "인지저하" in spaced_tokens
    assert "식욕저하" in spaced_tokens
    assert "수분섭취" in spaced_tokens


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


def _write_bm25_fixture(
    tmp_path: Path,
    *,
    xml_body: str = (
        "<article><body><sec><title>Nutrition Care</title>"
        "<p>Older adults with malnutrition risk should receive food fortification "
        "and oral nutritional supplements providing 400 kcal and 30 g protein daily.</p>"
        "</sec></body></article>"
    ),
    write_approved_file: bool = True,
    review_status: str = "approved",
    override_sha256: str | None = None,
    raw_bytes_override: bytes | None = None,
    extra_artifacts: list[dict[str, object]] | None = None,
) -> tuple[Path, Path]:
    sources_dir = tmp_path / "rag_sources"
    rel_path = "glim-2025/sample-guideline.xml"
    file_path = sources_dir / rel_path
    payload = raw_bytes_override if raw_bytes_override is not None else xml_body.encode("utf-8")
    actual_sha = hashlib.sha256(payload).hexdigest()
    if write_approved_file:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(payload)
    else:
        sources_dir.mkdir(parents=True, exist_ok=True)

    artifacts: list[dict[str, object]] = [
        {
            "artifact_id": "sample_guideline_xml",
            "doc_id": "glim_2025",
            "document_title": "Sample Approved Guideline",
            "publisher": "Test Society",
            "published_year_or_edition": "2025",
            "relative_path": rel_path,
            "format": "xml",
            "source_url": "https://example.org/sample-guideline",
            "language": "en",
            "expected_sha256": (
                override_sha256
                if override_sha256 is not None
                else (actual_sha if review_status == "approved" else None)
            ),
            "review_status": review_status,
        }
    ]
    if extra_artifacts:
        artifacts.extend(extra_artifacts)

    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps({"manifest_version": "test-1.0", "artifacts": artifacts}, ensure_ascii=False),
        encoding="utf-8",
    )
    return sources_dir, manifest_path


def test_wiring_bm25_fails_closed_when_all_approved_sources_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources_dir, manifest_path = _write_bm25_fixture(tmp_path, write_approved_file=False)
    monkeypatch.setenv("RAG_SOURCES_DIR", str(sources_dir))
    monkeypatch.setenv("RAG_MANIFEST_PATH", str(manifest_path))

    with pytest.raises(ConfigError, match="원문 파일 누락"):
        create_app(Settings(_env_file=None, guideline_search="bm25"))


def test_wiring_bm25_fails_closed_on_invalid_manifest_or_min_score(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources_dir, manifest_path = _write_bm25_fixture(tmp_path / "bad_score")
    monkeypatch.setenv("RAG_SOURCES_DIR", str(sources_dir))
    monkeypatch.setenv("RAG_MANIFEST_PATH", str(manifest_path))
    monkeypatch.setenv("RAG_BM25_MIN_SCORE", "not-a-float")
    with pytest.raises(ConfigError, match="GUIDELINE_SEARCH=bm25 초기화 실패"):
        create_app(Settings(_env_file=None, guideline_search="bm25"))

    monkeypatch.delenv("RAG_BM25_MIN_SCORE", raising=False)
    monkeypatch.setenv("RAG_MANIFEST_PATH", str(tmp_path / "missing_manifest.json"))
    with pytest.raises(ConfigError, match="GUIDELINE_SEARCH=bm25 초기화 실패"):
        create_app(Settings(_env_file=None, guideline_search="bm25"))

    bad_json = tmp_path / "bad_manifest.json"
    bad_json.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setenv("RAG_MANIFEST_PATH", str(bad_json))
    with pytest.raises(ConfigError, match="GUIDELINE_SEARCH=bm25 초기화 실패"):
        create_app(Settings(_env_file=None, guideline_search="bm25"))


def test_wiring_bm25_fails_closed_when_partial_approved_source_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources_dir, manifest_path = _write_bm25_fixture(
        tmp_path,
        extra_artifacts=[
            {
                "artifact_id": "missing_approved_pdf",
                "doc_id": "espen_geriatrics",
                "document_title": "Missing Approved PDF",
                "publisher": "ESPEN",
                "published_year_or_edition": "2022",
                "relative_path": "espen-geriatrics/missing.pdf",
                "format": "pdf",
                "source_url": "https://example.org/missing.pdf",
                "language": "en",
                "expected_sha256": "a" * 64,
                "review_status": "approved",
            }
        ],
    )
    monkeypatch.setenv("RAG_SOURCES_DIR", str(sources_dir))
    monkeypatch.setenv("RAG_MANIFEST_PATH", str(manifest_path))

    with pytest.raises(ConfigError, match="missing_approved_pdf"):
        create_app(Settings(_env_file=None, guideline_search="bm25"))


def test_wiring_bm25_fails_closed_when_approved_source_has_zero_chunks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources_dir, manifest_path = _write_bm25_fixture(
        tmp_path,
        xml_body="<article><body><sec><title></title><p>   </p></sec></body></article>",
    )
    monkeypatch.setenv("RAG_SOURCES_DIR", str(sources_dir))
    monkeypatch.setenv("RAG_MANIFEST_PATH", str(manifest_path))

    with pytest.raises(ConfigError, match="추출된 청크가 0개"):
        create_app(Settings(_env_file=None, guideline_search="bm25"))


def test_wiring_bm25_fails_closed_when_manifest_has_only_pending_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources_dir, manifest_path = _write_bm25_fixture(tmp_path, review_status="pending")
    monkeypatch.setenv("RAG_SOURCES_DIR", str(sources_dir))
    monkeypatch.setenv("RAG_MANIFEST_PATH", str(manifest_path))

    with pytest.raises(ConfigError, match="청크가 0개"):
        create_app(Settings(_env_file=None, guideline_search="bm25"))


def test_wiring_bm25_fails_closed_on_hash_mismatch_and_invalid_format(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources_dir, manifest_path = _write_bm25_fixture(
        tmp_path / "hash_case",
        override_sha256="0" * 64,
    )
    monkeypatch.setenv("RAG_SOURCES_DIR", str(sources_dir))
    monkeypatch.setenv("RAG_MANIFEST_PATH", str(manifest_path))
    with pytest.raises(ConfigError, match="SHA-256 판본 불일치"):
        create_app(Settings(_env_file=None, guideline_search="bm25"))

    bad_sources_dir, bad_manifest_path = _write_bm25_fixture(
        tmp_path / "format_case",
        raw_bytes_override=b"NOT_AN_XML_FILE_CONTENT",
    )
    monkeypatch.setenv("RAG_SOURCES_DIR", str(bad_sources_dir))
    monkeypatch.setenv("RAG_MANIFEST_PATH", str(bad_manifest_path))
    with pytest.raises(ConfigError, match="형식 불일치"):
        create_app(Settings(_env_file=None, guideline_search="bm25"))


async def test_wiring_bm25_succeeds_with_valid_approved_and_missing_pending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources_dir, manifest_path = _write_bm25_fixture(
        tmp_path,
        extra_artifacts=[
            {
                "artifact_id": "pending_missing_pdf",
                "doc_id": "glim_2025",
                "document_title": "Pending Missing PDF",
                "publisher": "GLIM",
                "published_year_or_edition": "2025",
                "relative_path": "glim-2025/pending-missing.pdf",
                "format": "pdf",
                "source_url": "https://example.org/pending.pdf",
                "language": "en",
                "expected_sha256": None,
                "review_status": "pending",
            }
        ],
    )
    monkeypatch.setenv("RAG_SOURCES_DIR", str(sources_dir))
    monkeypatch.setenv("RAG_MANIFEST_PATH", str(manifest_path))

    app = create_app(Settings(_env_file=None, guideline_search="bm25"))
    searcher = app.state.guideline_search
    assert isinstance(searcher, Bm25GuidelineSearch)

    hits = await searcher.search("food fortification oral nutritional supplements", limit=3)
    assert len(hits) == 1
    assert hits[0].doc_id == "glim_2025"

    resolved = await searcher.resolve_evidence(hits[0].doc_id, hits[0].section)
    assert resolved == hits[0]
    assert await searcher.search("스마트폰 충전 케이블", limit=3) == ()


def test_fake_default_startup_unaffected_without_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GUIDELINE_SEARCH", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("RAG_SOURCES_DIR", str(tmp_path))
    monkeypatch.setenv("RAG_MANIFEST_PATH", str(tmp_path / "missing_manifest.json"))

    app = create_app(Settings(_env_file=None))

    assert isinstance(app.state.guideline_search, FakeGuidelineSearch)


async def test_bm25_cross_lingual_dementia_and_dehydration_queries() -> None:
    extra_chunks = SAMPLE_CHUNKS + (
        GuidelineChunk(
            chunk_id="espen_geriatrics_pdf::p.22#c1",
            doc_id="espen_geriatrics",
            artifact_id="espen_geriatrics_pdf",
            section="p.22#c1",
            locator="p.22#c1",
            verified_recommendation_no=None,
            text=(
                "Older adults with dementia or cognitive impairment experiencing loss of appetite "
                "should receive supportive mealtime interventions. To prevent low-intake "
                "dehydration, adequate daily fluid intake and hydration drinks are recommended."
            ),
            source_url=SAMPLE_CHUNKS[0].source_url,
            document_title="ESPEN Geriatrics",
            publisher="ESPEN",
            published_year_or_edition="2022",
            actual_source_file="espen-geriatrics/espen-practical-guideline-geriatrics.pdf",
            source_format="pdf",
            language="en",
            file_sha256="a" * 64,
            review_status="approved",
        ),
    )
    searcher = Bm25GuidelineSearch(extra_chunks, enable_bilingual_expand=True)

    dementia_hits = await searcher.search(
        "치매나 인지저하가 있는 고령 환자의 식욕 저하 영양 중재", limit=2
    )
    assert dementia_hits
    assert dementia_hits[0].section == "p.22#c1"

    dehydration_hits = await searcher.search(
        "고령 환자의 탈수 예방을 위한 하루 수분 섭취량 권장 기준과 저수분 상태 모니터링", limit=2
    )
    assert dehydration_hits
    assert dehydration_hits[0].section == "p.22#c1"
