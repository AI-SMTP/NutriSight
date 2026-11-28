"""`ChromaGuidelineSearch` v0.2 계약·원자 재색인·매니페스트 승인·근거 역추적 테스트.

외부 OpenAI API는 호출하지 않고 결정론적 로컬 `StubEmbeddingBackend`로 모의한다.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Sequence
from pathlib import Path

import pytest

from app.config import Settings
from app.main import create_app
from app.recommender.chroma_search import (
    ACTIVE_POINTER_FILENAME,
    VERSIONS_SUBDIR,
    ChromaGuidelineSearch,
    GuidelineSearchError,
    index_guideline_sources,
    read_active_pointer,
    read_index_meta,
)
from app.recommender.query_expander import expand_bilingual_query
from app.recommender.rag_sources import (
    audit_source_manifest,
    compute_file_sha256,
    extract_verified_recommendation_no,
    load_guideline_chunks,
)
from tests.contracts.guideline import GuidelineSearchContract


class StubEmbeddingBackend:
    """네트워크 호출 없이 재현 가능한 코사인 벡터를 생성하는 테스트용 임베딩 백엔드."""

    def __init__(self, dim: int = 128, *, fail_on_call: int | None = None) -> None:
        self.dim = dim
        self.fail_on_call = fail_on_call
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
        if self.fail_on_call is not None and self.calls == self.fail_on_call:
            raise GuidelineSearchError("Simulated OpenAI embedding API failure")
        return [self._embed_one(t) for t in texts]


def _write_test_manifest(
    manifest_path: Path,
    *,
    xml_path: Path,
    review_status: str = "approved",
    expected_sha256: str | None = None,
    extra_artifacts: list[dict[str, object]] | None = None,
) -> None:
    sha = expected_sha256 if expected_sha256 is not None else compute_file_sha256(xml_path)
    artifacts: list[dict[str, object]] = [
        {
            "artifact_id": "glim_2025_jpen_xml",
            "doc_id": "glim_2025",
            "document_title": "GLIM 5년 업데이트(2025) — JPEN XML",
            "publisher": "GLIM Working Group / JPEN",
            "published_year_or_edition": "2025 (JPEN XML)",
            "relative_path": "glim-2025/glim-5-year-update-2025-jpen.xml",
            "format": "xml",
            "source_url": "https://aspenjournals.onlinelibrary.wiley.com/journal/19412444",
            "language": "en",
            "expected_sha256": sha,
            "review_status": review_status,
            "reviewed_at": "2026-11-27" if review_status == "approved" else None,
        }
    ]
    if extra_artifacts:
        artifacts.extend(extra_artifacts)
    manifest_path.write_text(
        json.dumps(
            {"manifest_version": "1.0", "artifacts": artifacts}, ensure_ascii=False, indent=2
        ),
        encoding="utf-8",
    )


def _seed_sample_xml_sources(
    sources_dir: Path,
    *,
    manifest_path: Path,
    review_status: str = "approved",
    body_suffix: str = "",
) -> Path:
    glim_dir = sources_dir / "glim-2025"
    glim_dir.mkdir(parents=True, exist_ok=True)
    xml_path = glim_dir / "glim-5-year-update-2025-jpen.xml"
    long_filler = " ".join(["older adult protein nutrition monitoring"] * 40)
    xml_path.write_text(
        f"""<article><body>
        <sec><title>Food Fortification and Protein Intake</title>
        <p>Recommendation 20: 노인 단백질 섭취 부족 시 식사 강화와 경구영양보충(ONS)을 검토하며,
        food fortification and oral nutritional supplements improve energy protein intake.
        {body_suffix}</p>
        </sec>
        <sec><title>Multi Chunk Section</title>
        <p>{long_filler}. First distinct passage about energy requirements 30 kcal/kg.</p>
        <p>{long_filler}. Second distinct passage about malnutrition GLIM 50% intake criteria.</p>
        </sec>
        <sec><title>Pressure Injury Nutrition</title>
        <p>욕창 환자의 영양 부족 시 고단백 경구영양보충과 다학제 영양관리팀 의뢰를 검토한다.</p>
        </sec>
        </body></article>""",
        encoding="utf-8",
    )
    _write_test_manifest(manifest_path, xml_path=xml_path, review_status=review_status)
    return xml_path


class TestChromaGuidelineContract(GuidelineSearchContract):
    """`GuidelineSearchContract` 불변 조건 검증 (외부 API 미호출)."""

    @pytest.fixture
    def search(self, tmp_path: Path) -> ChromaGuidelineSearch:
        sources_dir = tmp_path / "rag_sources"
        persist_dir = tmp_path / "chroma_db"
        manifest_path = tmp_path / "manifest.json"
        _seed_sample_xml_sources(sources_dir, manifest_path=manifest_path)
        backend = StubEmbeddingBackend(dim=128)
        index_guideline_sources(
            sources_dir=sources_dir,
            persist_dir=persist_dir,
            manifest_path=manifest_path,
            embedding_model="stub-large",
            embedding_backend=backend,
        )
        return ChromaGuidelineSearch(
            persist_dir=persist_dir,
            embedding_backend=backend,
            embedding_model="stub-large",
            min_relevance_score=0.05,
        )


def test_p0_initial_index_and_zero_api_call_skip_when_unchanged(tmp_path: Path) -> None:
    sources_dir = tmp_path / "rag_sources"
    persist_dir = tmp_path / "chroma_db"
    manifest_path = tmp_path / "manifest.json"
    _seed_sample_xml_sources(sources_dir, manifest_path=manifest_path)
    backend = StubEmbeddingBackend(dim=64)

    first = index_guideline_sources(
        sources_dir=sources_dir,
        persist_dir=persist_dir,
        manifest_path=manifest_path,
        embedding_model="stub-large",
        embedding_backend=backend,
    )
    calls_after_first = backend.calls

    second = index_guideline_sources(
        sources_dir=sources_dir,
        persist_dir=persist_dir,
        manifest_path=manifest_path,
        embedding_model="stub-large",
        embedding_backend=backend,
    )

    assert first["skipped_unchanged"] is False
    assert second["skipped_unchanged"] is True
    assert second["active_version"] == first["active_version"]
    # 무변경 스킵 시 임베딩 API를 전혀 호출하지 않는다.
    assert backend.calls == calls_after_first


async def test_p0_reindex_failure_mid_api_preserves_previous_active_index(tmp_path: Path) -> None:
    sources_dir = tmp_path / "rag_sources"
    persist_dir = tmp_path / "chroma_db"
    manifest_path = tmp_path / "manifest.json"
    _seed_sample_xml_sources(sources_dir, manifest_path=manifest_path)

    healthy_backend = StubEmbeddingBackend(dim=64)
    first = index_guideline_sources(
        sources_dir=sources_dir,
        persist_dir=persist_dir,
        manifest_path=manifest_path,
        embedding_model="stub-v1",
        embedding_backend=healthy_backend,
    )
    prev_version = first["active_version"]

    # 두 번째 배치(call=2)에서 API 오류를 강제 발생
    failing_backend = StubEmbeddingBackend(dim=64, fail_on_call=2)
    with pytest.raises(GuidelineSearchError, match="Simulated OpenAI embedding API failure"):
        index_guideline_sources(
            sources_dir=sources_dir,
            persist_dir=persist_dir,
            manifest_path=manifest_path,
            embedding_model="stub-v2",
            embedding_backend=failing_backend,
            force_rebuild=True,
        )

    # 활성 포인터는 여전히 이전 정상 버전을 가리키며 실패 버전은 failed로 기록된다.
    pointer = read_active_pointer(persist_dir)
    assert pointer is not None
    assert pointer["active_version"] == prev_version

    version_dirs = list((persist_dir / VERSIONS_SUBDIR).iterdir())
    failed_metas = [
        read_index_meta(d) for d in version_dirs if d.name != prev_version and read_index_meta(d)
    ]
    assert any(m and m.get("status") == "failed" for m in failed_metas)

    # 기존 정상 검색기는 중단 없이 계속 검색 및 근거 역추적 가능
    searcher = ChromaGuidelineSearch(
        persist_dir=persist_dir,
        embedding_backend=healthy_backend,
        embedding_model="stub-v1",
        min_relevance_score=0.05,
    )
    hits = await searcher.search("노인 단백질 섭취 부족 식사 강화", limit=3)
    assert len(hits) >= 1
    resolved = await searcher.resolve_evidence(hits[0].doc_id, hits[0].section)
    assert resolved == hits[0]


async def test_p0_partial_batch_write_failure_preserves_previous_index(tmp_path: Path) -> None:
    sources_dir = tmp_path / "rag_sources"
    persist_dir = tmp_path / "chroma_db"
    manifest_path = tmp_path / "manifest.json"
    _seed_sample_xml_sources(sources_dir, manifest_path=manifest_path)

    backend = StubEmbeddingBackend(dim=64)
    first = index_guideline_sources(
        sources_dir=sources_dir,
        persist_dir=persist_dir,
        manifest_path=manifest_path,
        embedding_model="stub-large",
        embedding_backend=backend,
        batch_size=2,
    )

    def _fail_second_batch(batch_idx: int, _batch: object) -> None:
        if batch_idx == 1:
            raise OSError("Simulated disk write failure on batch 1")

    with pytest.raises(GuidelineSearchError, match="Simulated disk write failure"):
        index_guideline_sources(
            sources_dir=sources_dir,
            persist_dir=persist_dir,
            manifest_path=manifest_path,
            embedding_model="stub-large",
            embedding_backend=backend,
            force_rebuild=True,
            batch_size=2,
            batch_writer_hook=_fail_second_batch,
        )

    pointer = read_active_pointer(persist_dir)
    assert pointer is not None
    assert pointer["active_version"] == first["active_version"]

    searcher = ChromaGuidelineSearch(
        persist_dir=persist_dir,
        embedding_backend=backend,
        embedding_model="stub-large",
        min_relevance_score=0.05,
    )
    assert len(await searcher.search("욕창 영양관리팀", limit=2)) >= 1


async def test_p0_model_change_and_source_modification_activate_new_version(tmp_path: Path) -> None:
    sources_dir = tmp_path / "rag_sources"
    persist_dir = tmp_path / "chroma_db"
    manifest_path = tmp_path / "manifest.json"
    _seed_sample_xml_sources(sources_dir, manifest_path=manifest_path, body_suffix="v1-marker")

    b_small = StubEmbeddingBackend(dim=64)
    r1 = index_guideline_sources(
        sources_dir=sources_dir,
        persist_dir=persist_dir,
        manifest_path=manifest_path,
        embedding_model="text-embedding-3-small",
        embedding_backend=b_small,
    )

    # 모델 변경 → 새 버전으로 재색인
    b_large = StubEmbeddingBackend(dim=128)
    r2 = index_guideline_sources(
        sources_dir=sources_dir,
        persist_dir=persist_dir,
        manifest_path=manifest_path,
        embedding_model="text-embedding-3-large",
        embedding_backend=b_large,
    )
    assert r2["active_version"] != r1["active_version"]
    assert r2["vector_dim"] == 128

    # 원문 변경 + 매니페스트 해시 갱신 → 새 버전으로 재색인
    _seed_sample_xml_sources(sources_dir, manifest_path=manifest_path, body_suffix="v2-updated")
    r3 = index_guideline_sources(
        sources_dir=sources_dir,
        persist_dir=persist_dir,
        manifest_path=manifest_path,
        embedding_model="text-embedding-3-large",
        embedding_backend=b_large,
    )
    assert r3["active_version"] != r2["active_version"]

    searcher = ChromaGuidelineSearch(
        persist_dir=persist_dir,
        embedding_backend=b_large,
        embedding_model="text-embedding-3-large",
        min_relevance_score=0.05,
    )
    hits = await searcher.search("노인 단백질 섭취 부족 식사 강화", limit=3)
    assert any("v2-updated" in h.text for h in hits)


def test_p0_manifest_never_auto_approves_pending_and_blocks_hash_mismatch(tmp_path: Path) -> None:
    sources_dir = tmp_path / "rag_sources"
    manifest_path = tmp_path / "manifest.json"
    xml_path = _seed_sample_xml_sources(
        sources_dir, manifest_path=manifest_path, review_status="pending"
    )

    # 파일이 존재해도 review_status=pending이면 승인·적재되지 않는다.
    audit = audit_source_manifest(sources_dir, manifest_path=manifest_path)
    assert audit["approved_ready_doc_ids"] == []
    assert audit["artifacts"][0]["status"] == "pending_review"
    assert len(audit["artifacts"][0]["actual_sha256"]) == 64

    chunks, _ = load_guideline_chunks(sources_dir, manifest_path=manifest_path)
    assert chunks == []

    # approved인데 SHA-256이 불일치하면 무결성 검증 실패로 차단한다.
    _write_test_manifest(
        manifest_path,
        xml_path=xml_path,
        review_status="approved",
        expected_sha256="0" * 64,
    )
    with pytest.raises(ValueError, match="SHA-256 판본 불일치"):
        load_guideline_chunks(sources_dir, manifest_path=manifest_path)

    # Codex 지적 반영: approved인데 expected_sha256이 비어 있거나 None이면 fail-closed 차단
    _write_test_manifest(
        manifest_path,
        xml_path=xml_path,
        review_status="approved",
        expected_sha256="",
    )
    with pytest.raises(ValueError, match="expected_sha256"):
        load_guideline_chunks(sources_dir, manifest_path=manifest_path)

    # Codex 지적 반영: 중복 artifact_id 매니페스트 즉시 차단
    _write_test_manifest(
        manifest_path,
        xml_path=xml_path,
        review_status="approved",
        extra_artifacts=[
            {
                "artifact_id": "glim_2025_jpen_xml",
                "doc_id": "glim_2025",
                "document_title": "Duplicate",
                "publisher": "Dup",
                "published_year_or_edition": "2025",
                "relative_path": "glim-2025/other.xml",
                "format": "xml",
                "source_url": "https://example.org",
                "language": "en",
                "expected_sha256": None,
                "review_status": "pending",
            }
        ],
    )
    with pytest.raises(ValueError, match="중복되거나 비어 있는 artifact_id"):
        load_guideline_chunks(sources_dir, manifest_path=manifest_path)


async def test_codex_pointer_traversal_guard_and_version_pinned_reverse_lookup(
    tmp_path: Path,
) -> None:
    # 경로 탈출 active_version 포인터 차단
    bad_dir = tmp_path / "bad_pointer"
    bad_dir.mkdir()
    (bad_dir / ACTIVE_POINTER_FILENAME).write_text(
        json.dumps({"active_version": "../escape"}), encoding="utf-8"
    )
    bad_searcher = ChromaGuidelineSearch(
        persist_dir=bad_dir,
        embedding_backend=StubEmbeddingBackend(dim=64),
        embedding_model="stub-large",
    )
    with pytest.raises(GuidelineSearchError, match="유효하지 않은 색인 버전 식별자"):
        await bad_searcher.search("노인 단백질")

    # 재색인 후에도 이전 version_id 스냅샷으로 기존 근거 정확 역추적
    sources_dir = tmp_path / "rag_sources"
    persist_dir = tmp_path / "chroma_db"
    manifest_path = tmp_path / "manifest.json"
    _seed_sample_xml_sources(sources_dir, manifest_path=manifest_path, body_suffix="gen1-only")
    backend = StubEmbeddingBackend(dim=64)
    r1 = index_guideline_sources(
        sources_dir=sources_dir,
        persist_dir=persist_dir,
        manifest_path=manifest_path,
        embedding_model="stub-large",
        embedding_backend=backend,
    )
    _seed_sample_xml_sources(sources_dir, manifest_path=manifest_path, body_suffix="gen2-only")
    r2 = index_guideline_sources(
        sources_dir=sources_dir,
        persist_dir=persist_dir,
        manifest_path=manifest_path,
        embedding_model="stub-large",
        embedding_backend=backend,
    )
    assert r1["active_version"] != r2["active_version"]

    searcher = ChromaGuidelineSearch(
        persist_dir=persist_dir,
        embedding_backend=backend,
        embedding_model="stub-large",
    )
    old_hit = await searcher.resolve_evidence("glim_2025", "R20", version_id=r1["active_version"])
    new_hit = await searcher.resolve_evidence("glim_2025", "R20")
    assert old_hit is not None and "gen1-only" in old_hit.text
    assert new_hit is not None and "gen2-only" in new_hit.text


async def test_p1_unique_section_ids_no_collision_and_exact_reverse_lookup(tmp_path: Path) -> None:
    sources_dir = tmp_path / "rag_sources"
    persist_dir = tmp_path / "chroma_db"
    manifest_path = tmp_path / "manifest.json"
    _seed_sample_xml_sources(sources_dir, manifest_path=manifest_path)

    chunks, _ = load_guideline_chunks(
        sources_dir, manifest_path=manifest_path, chunk_size=350, chunk_overlap=50
    )
    # 동일 섹션에서 여러 청크가 분할되어도 (doc_id, section)이 100% 고유해야 한다.
    keys = [(c.doc_id, c.section) for c in chunks]
    assert len(chunks) >= 4
    assert len(set(keys)) == len(keys)
    # 검증된 단일 권고 번호 Recommendation 20 → R20 추출, 없는 문단에는 R번호를 생성하지 않는다.
    assert any(c.section == "R20" for c in chunks)
    assert extract_verified_recommendation_no("일반적인 노인 단백질 섭취 권고 문장") is None

    backend = StubEmbeddingBackend(dim=128)
    index_guideline_sources(
        sources_dir=sources_dir,
        persist_dir=persist_dir,
        manifest_path=manifest_path,
        embedding_model="stub-large",
        embedding_backend=backend,
        chunk_size=350,
        chunk_overlap=50,
    )
    searcher = ChromaGuidelineSearch(
        persist_dir=persist_dir,
        embedding_backend=backend,
        embedding_model="stub-large",
        min_relevance_score=0.05,
    )

    for c in chunks:
        resolved = await searcher.resolve_evidence(c.doc_id, c.section)
        assert resolved is not None
        assert resolved.text == c.text
        assert resolved.source_url == c.source_url
    assert await searcher.resolve_evidence("glim_2025", "nonexistent#c99") is None


def test_bilingual_query_expansion_handles_ko_en_and_unrelated() -> None:
    ko_exp = expand_bilingual_query("노인 단백질 섭취 부족 식사 강화 및 경구영양보충")
    assert "protein" in ko_exp
    assert "food" in ko_exp
    assert "oral" in ko_exp

    en_exp = expand_bilingual_query("pressure injury nutrition support")
    assert "욕창" in en_exp

    unrelated = "파이썬 FastAPI 웹소켓 설정"
    assert expand_bilingual_query(unrelated) == unrelated


def test_bilingual_query_expansion_covers_dementia_dehydration_without_leaks() -> None:
    dementia_exp = expand_bilingual_query(
        "치매나 인지저하가 있는 고령 환자의 식사 시간 식욕 저하와 영양 중재 권고"
    )
    assert "dementia" in dementia_exp
    assert "cognitive" in dementia_exp
    assert "appetite" in dementia_exp
    # 중복 토큰이 힌트 괄호 안에 반복 추가되지 않아야 한다.
    assert dementia_exp.count("dementia") == 1

    dehydration_exp = expand_bilingual_query(
        "고령 환자의 탈수 예방을 위한 하루 수분 섭취량 권장 기준과 저수분 상태 모니터링"
    )
    assert "dehydration" in dehydration_exp
    assert "fluid" in dehydration_exp
    assert "hydration" in dehydration_exp

    # 욕창+수분 질의(HOLD-04)에는 탈수/저수분 편향 토큰이 붙지 않아야 한다.
    pressure_exp = expand_bilingual_query(
        "욕창예방과 상처 치유를 위한 영양사정 및 에너지·단백질·수분 섭취 모니터링"
    )
    assert "pressure" in pressure_exp
    assert "dehydration" not in pressure_exp
    assert "fluid" not in pressure_exp

    en_dementia = expand_bilingual_query("older adults with dementia and dehydration")
    assert "치매" in en_dementia
    assert "탈수" in en_dementia

    oos_query = "임신성 당뇨 산모의 인슐린 용량 조절과 태아 성장 초음파 추적 간격"
    assert expand_bilingual_query(oos_query) == oos_query


async def test_chroma_search_handles_corrupted_pointer_and_missing_index(tmp_path: Path) -> None:
    missing_searcher = ChromaGuidelineSearch(
        persist_dir=tmp_path / "missing_index",
        embedding_backend=StubEmbeddingBackend(dim=64),
        embedding_model="stub-large",
    )
    with pytest.raises(GuidelineSearchError, match="활성 가이드라인 색인이 없다"):
        await missing_searcher.search("노인 단백질 섭취 부족")

    corrupted_dir = tmp_path / "corrupted"
    corrupted_dir.mkdir()
    (corrupted_dir / ACTIVE_POINTER_FILENAME).write_text("{broken json", encoding="utf-8")
    corrupted_searcher = ChromaGuidelineSearch(
        persist_dir=corrupted_dir,
        embedding_backend=StubEmbeddingBackend(dim=64),
        embedding_model="stub-large",
    )
    with pytest.raises(GuidelineSearchError, match="포인터 파일이 손상되었다"):
        await corrupted_searcher.search("노인 단백질 섭취 부족")


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
