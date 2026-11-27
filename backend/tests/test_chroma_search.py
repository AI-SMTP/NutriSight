"""`ChromaGuidelineSearch` 계약 테스트와 색인·임계값·쿼리 확장·오류 처리 테스트.

외부 OpenAI API는 호출하지 않고 결정론적 로컬 `StubEmbeddingBackend`로 모의한다.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Sequence
from pathlib import Path

import pytest

from app.config import Settings
from app.main import create_app
from app.recommender.chroma_search import (
    ChromaGuidelineSearch,
    GuidelineSearchError,
    index_guideline_sources,
)
from app.recommender.query_expander import expand_bilingual_query
from tests.contracts.guideline import GuidelineSearchContract


class StubEmbeddingBackend:
    """네트워크 호출 없이 재현 가능한 코사인 벡터를 생성하는 테스트용 임베딩 백엔드."""

    def __init__(self, dim: int = 128) -> None:
        self.dim = dim
        self.calls: int = 0

    def _embed_one(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        tokens = re.findall(r"[0-9a-zA-Z가-힣]{2,}", text.lower())
        for tok in tokens:
            pieces = [tok] + [tok[i : i + 2] for i in range(max(0, len(tok) - 1))]
            for piece in pieces:
                digest = int(hashlib.md5(piece.encode("utf-8")).hexdigest(), 16)
                idx = digest % self.dim
                sign = 1.0 if ((digest >> 8) & 1) == 0 else -1.0
                vec[idx] += sign
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls += 1
        return [self._embed_one(t) for t in texts]


def _seed_sample_xml_sources(sources_dir: Path) -> None:
    """테스트용 공식 구조(GLIM XML) 샘플 문서를 임시 디렉터리에 생성한다."""
    glim_dir = sources_dir / "glim-2025"
    glim_dir.mkdir(parents=True, exist_ok=True)
    (glim_dir / "glim-5-year-update-2025-jpen.xml").write_text(
        """<article><body>
        <sec><title>Food Fortification and Protein Intake</title>
        <p>노인 단백질 섭취 부족 시 식사 강화와 경구영양보충(ONS)을 검토하며,
        food fortification and oral nutritional supplements improve energy protein intake.</p>
        </sec>
        <sec><title>Reduced Food Intake Criteria</title>
        <p>GLIM criteria define reduced food intake as 50 percent or less of energy requirements
        for more than one week in older adults with malnutrition.</p>
        </sec>
        <sec><title>Pressure Injury Nutrition</title>
        <p>욕창 환자의 영양 부족 시 고단백 경구영양보충과 다학제 영양관리팀 의뢰를 검토한다.</p>
        </sec>
        </body></article>""",
        encoding="utf-8",
    )


class TestChromaGuidelineContract(GuidelineSearchContract):
    """`GuidelineSearchContract` 불변 조건 검증 (외부 API 미호출)."""

    @pytest.fixture
    def search(self, tmp_path: Path) -> ChromaGuidelineSearch:
        sources_dir = tmp_path / "rag_sources"
        persist_dir = tmp_path / "chroma_db"
        _seed_sample_xml_sources(sources_dir)
        backend = StubEmbeddingBackend(dim=128)
        index_guideline_sources(
            sources_dir=sources_dir,
            persist_dir=persist_dir,
            embedding_model="stub-large",
            embedding_backend=backend,
        )
        return ChromaGuidelineSearch(
            persist_dir=persist_dir,
            embedding_backend=backend,
            embedding_model="stub-large",
            min_relevance_score=0.05,
        )


def test_bilingual_query_expansion_adds_english_clinical_terms() -> None:
    expanded = expand_bilingual_query("노인 단백질 섭취 부족 식사 강화 및 경구영양보충")
    assert "protein" in expanded
    assert "food fortification" in expanded
    assert "oral nutritional supplements" in expanded

    # 범위 외 질의는 원문을 변형하지 않는다.
    unrelated = "파이썬 FastAPI 웹소켓 설정"
    assert expand_bilingual_query(unrelated) == unrelated


async def test_chroma_search_returns_empty_on_blank_or_below_threshold(tmp_path: Path) -> None:
    sources_dir = tmp_path / "rag_sources"
    persist_dir = tmp_path / "chroma_db"
    _seed_sample_xml_sources(sources_dir)
    backend = StubEmbeddingBackend(dim=128)
    index_guideline_sources(
        sources_dir=sources_dir,
        persist_dir=persist_dir,
        embedding_model="stub-large",
        embedding_backend=backend,
    )
    searcher = ChromaGuidelineSearch(
        persist_dir=persist_dir,
        embedding_backend=backend,
        embedding_model="stub-large",
        min_relevance_score=0.99,
    )

    assert await searcher.search("   ") == ()
    assert await searcher.search("스마트폰 배터리 충전 온도") == ()


async def test_chroma_search_raises_explicit_error_when_index_missing(tmp_path: Path) -> None:
    searcher = ChromaGuidelineSearch(
        persist_dir=tmp_path / "missing_index",
        embedding_backend=StubEmbeddingBackend(dim=64),
        embedding_model="stub-large",
    )

    with pytest.raises(GuidelineSearchError, match="색인이 없다"):
        await searcher.search("노인 단백질 섭취 부족")


def test_indexer_skips_reembedding_when_sources_and_model_unchanged(tmp_path: Path) -> None:
    sources_dir = tmp_path / "rag_sources"
    persist_dir = tmp_path / "chroma_db"
    _seed_sample_xml_sources(sources_dir)
    backend = StubEmbeddingBackend(dim=64)

    first = index_guideline_sources(
        sources_dir=sources_dir,
        persist_dir=persist_dir,
        embedding_model="stub-large",
        embedding_backend=backend,
    )
    second = index_guideline_sources(
        sources_dir=sources_dir,
        persist_dir=persist_dir,
        embedding_model="stub-large",
        embedding_backend=backend,
    )

    assert first["skipped_unchanged"] is False
    assert second["skipped_unchanged"] is True
    assert second["indexed_chunks"] == first["indexed_chunks"]


def test_wiring_selects_chroma_implementation_with_mocked_backend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.recommender import chroma_search

    class _MockOpenAI:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

        def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
            return [[0.1] * 8 for _ in texts]

    monkeypatch.setattr(chroma_search, "OpenAIEmbeddingBackend", _MockOpenAI)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-real")
    monkeypatch.setenv("RAG_CHROMA_DIR", str(tmp_path / "chroma"))

    app = create_app(Settings(_env_file=None, guideline_search="chroma"))

    assert isinstance(app.state.guideline_search, ChromaGuidelineSearch)
