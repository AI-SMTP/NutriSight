"""Windows 안전 버전 분리 재색인 + OpenAI 임베딩 Chroma 코사인 `GuidelineSearch` 구현 (v0.2).

핵심 안정화 설계:
1. 재색인은 기존 활성 색인을 삭제하지 않고 새 `versions/<version_id>/` 디렉터리에 구축한다.
2. 모든 배치 저장 후 별도 핸들로 무결성(건수·모델·차원·메타데이터·스모크 질의)을 검증한다.
3. 검증 통과 후에만 `active_pointer.json`을 임시 파일 + `os.replace()`로 원자적 교체한다.
4. API 오류·배치 실패 시 실패 버전은 `failed`로 남기고 기존 활성 색인은 손상 없이 유지된다.
5. `resolve_evidence(doc_id, section)`로 `EvidenceRef`에서 정확한 원문 청크를 역추적한다.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from app.recommender.guideline_types import GuidelineHit
from app.recommender.query_expander import expand_bilingual_query
from app.recommender.rag_sources import (
    DEFAULT_CHROMA_DIR,
    DEFAULT_MANIFEST_PATH,
    DEFAULT_SOURCES_DIR,
    EXTRACTOR_VERSION,
    SECTION_ID_VERSION,
    compute_source_hashes,
    load_guideline_chunks,
    load_source_manifest,
)

COLLECTION_NAME = "nutrisight_guideline_chunks"
INDEX_META_FILENAME = "index_meta.json"
ACTIVE_POINTER_FILENAME = "active_pointer.json"
VERSIONS_SUBDIR = "versions"
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-large"
DEFAULT_MIN_RELEVANCE_SCORE = 0.50
_SAFE_VERSION_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def _validate_version_id(version_id: str) -> str:
    """경로 탈출(`..`, 드라이브 경로, 구분자)을 차단하는 안전한 버전 식별자 검증."""
    if not isinstance(version_id, str) or not _SAFE_VERSION_ID_RE.match(version_id):
        raise GuidelineSearchError(f"유효하지 않은 색인 버전 식별자: {version_id!r}")
    if ".." in version_id:
        raise GuidelineSearchError(f"경로 탈출 문자열이 포함된 버전 식별자: {version_id!r}")
    return version_id


class GuidelineSearchError(RuntimeError):
    """가이드라인 색인 누락·손상·모델 불일치·외부 임베딩 호출 실패를 명시적으로 보고하는 예외."""


class EmbeddingBackend(Protocol):
    """외부 OpenAI 임베딩 호출을 테스트에서 모의할 수 있도록 분리한 최소 인터페이스."""

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        """문서 또는 질의 문자열 목록을 임베딩 벡터 목록으로 변환한다."""
        ...


@dataclass
class EmbeddingUsageTracker:
    """임베딩 API 호출 횟수·토큰 사용량 누적 추적기 (평가 스크립트용)."""

    call_count: int = 0
    prompt_tokens: int = 0
    total_tokens: int = 0
    error_count: int = 0


class OpenAIEmbeddingBackend:
    """OpenAI Embeddings API 직접 호출 구현 (LangChain 비의존)."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str = DEFAULT_EMBEDDING_MODEL,
        base_url: str | None = None,
        timeout_s: float = 20.0,
        usage_tracker: EmbeddingUsageTracker | None = None,
    ) -> None:
        if not api_key or "your_" in api_key:
            raise GuidelineSearchError(
                "OPENAI_API_KEY가 설정되지 않아 임베딩 기반 가이드라인 검색을 실행할 수 없다."
            )
        from openai import OpenAI

        kwargs: dict[str, Any] = {
            "api_key": api_key,
            "timeout": timeout_s,
            "max_retries": 0,
        }
        if base_url:
            kwargs["base_url"] = base_url
        self._client = OpenAI(**kwargs)
        self.model = model
        self.usage = usage_tracker or EmbeddingUsageTracker()

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            self.usage.call_count += 1
            response = self._client.embeddings.create(model=self.model, input=list(texts))
        except Exception as exc:
            self.usage.error_count += 1
            raise GuidelineSearchError(
                f"임베딩 API 호출 실패 ({type(exc).__name__}): {exc}"
            ) from exc

        usage_obj = getattr(response, "usage", None)
        if usage_obj is not None:
            self.usage.prompt_tokens += int(getattr(usage_obj, "prompt_tokens", 0) or 0)
            self.usage.total_tokens += int(getattr(usage_obj, "total_tokens", 0) or 0)

        ordered = sorted(response.data, key=lambda item: item.index)
        return [list(item.embedding) for item in ordered]


def _atomic_write_json(target_path: Path, payload: dict[str, Any], *, retries: int = 5) -> None:
    """Windows 공유 잠금에도 안전하게 임시 파일 기록 후 `os.replace()`로 원자 교체한다."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target_path.with_name(
        f".{target_path.name}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp"
    )
    encoded = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    try:
        with tmp_path.open("wb") as f:
            f.write(encoded)
            f.flush()
            os.fsync(f.fileno())
        last_exc: Exception | None = None
        for attempt in range(retries):
            try:
                os.replace(tmp_path, target_path)
                return
            except PermissionError as exc:
                last_exc = exc
                time.sleep(0.05 * (attempt + 1))
        if last_exc is not None:
            raise last_exc
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


def read_active_pointer(persist_dir: str | Path) -> dict[str, Any] | None:
    """`active_pointer.json`을 읽는다. 파일이 없으면 None, 손상되면 GuidelineSearchError."""
    pointer_path = Path(persist_dir) / ACTIVE_POINTER_FILENAME
    if not pointer_path.exists():
        return None
    try:
        data = json.loads(pointer_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise GuidelineSearchError(
            f"활성 색인 포인터 파일이 손상되었다: {pointer_path} ({type(exc).__name__})"
        ) from exc
    if not isinstance(data, dict) or not data.get("active_version"):
        raise GuidelineSearchError(f"활성 색인 포인터 형식이 올바르지 않다: {pointer_path}")
    return data


def resolve_version_dir(persist_dir: str | Path, version_id: str) -> tuple[Path, dict[str, Any]]:
    """지정된 `version_id`가 `versions/` 내부의 검증 완료 버전인지 확인하고 반환한다."""
    safe_id = _validate_version_id(version_id)
    root = Path(persist_dir)
    versions_root = (root / VERSIONS_SUBDIR).resolve()
    version_dir = (versions_root / safe_id).resolve()
    if version_dir.parent != versions_root:
        raise GuidelineSearchError(f"버전 디렉터리 경로 탈출 감지: {version_id!r}")

    meta = read_index_meta(version_dir)
    if meta is None or not (version_dir / "chroma.sqlite3").exists():
        raise GuidelineSearchError(
            f"색인 버전({safe_id})이 존재하지 않거나 손상되었다: {version_dir}"
        )
    if meta.get("version_id") != safe_id:
        raise GuidelineSearchError(
            f"색인 메타데이터 version_id 불일치: expected={safe_id}, got={meta.get('version_id')}"
        )
    if meta.get("status") != "verified":
        raise GuidelineSearchError(
            f"검증되지 않은 색인 버전({safe_id}, status={meta.get('status')})은 사용할 수 없다."
        )
    return version_dir, meta


def resolve_active_version_dir(persist_dir: str | Path) -> tuple[Path, dict[str, Any]]:
    """현재 활성화된 검증 완료 버전 디렉터리와 `index_meta.json`을 해결한다."""
    root = Path(persist_dir)
    pointer = read_active_pointer(root)
    if pointer is None:
        raise GuidelineSearchError(
            f"활성 가이드라인 색인이 없다: {root}. "
            "먼저 `uv run python scripts/index_guidelines.py`로 색인을 생성하세요."
        )
    return resolve_version_dir(root, str(pointer["active_version"]))


def read_index_meta(version_dir: str | Path) -> dict[str, Any] | None:
    """지정 색인 버전 디렉터리의 `index_meta.json`을 읽는다."""
    meta_path = Path(version_dir) / INDEX_META_FILENAME
    if not meta_path.exists():
        return None
    try:
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _verify_candidate_index(
    *,
    version_dir: Path,
    expected_count: int,
    expected_doc_ids: set[str],
    expected_dim: int,
    probe_vector: list[float],
) -> None:
    """새 Chroma 버전 디렉터리를 다시 열어 건수·메타데이터·스모크 질의 무결성을 검증한다."""
    import chromadb

    if not (version_dir / "chroma.sqlite3").exists():
        raise GuidelineSearchError(f"후보 색인 DB 파일 누락: {version_dir}")

    client = chromadb.PersistentClient(path=str(version_dir))
    collection = client.get_collection(name=COLLECTION_NAME)
    actual_count = collection.count()
    if actual_count != expected_count:
        raise GuidelineSearchError(
            f"후보 색인 청크 수 불일치: expected={expected_count}, actual={actual_count}"
        )

    stored = collection.get(include=["metadatas"])
    metadatas = stored.get("metadatas") or []
    found_docs: set[str] = set()
    seen_keys: set[tuple[str, str]] = set()
    for md in metadatas:
        if not isinstance(md, dict):
            raise GuidelineSearchError("후보 색인 메타데이터 손상")
        doc_id = str(md.get("doc_id", "")).strip()
        section = str(md.get("section", "")).strip()
        text = str(md.get("text", "")).strip()
        source_url = str(md.get("source_url", "")).strip()
        if not (doc_id and section and text and source_url):
            raise GuidelineSearchError(
                f"후보 색인 필수 메타데이터 누락: doc_id={doc_id!r}, section={section!r}"
            )
        key = (doc_id, section)
        if key in seen_keys:
            raise GuidelineSearchError(f"후보 색인 중복 근거 식별자 감지: {key}")
        seen_keys.add(key)
        found_docs.add(doc_id)

    if found_docs != expected_doc_ids:
        raise GuidelineSearchError(
            f"후보 색인 문서 집합 불일치: expected={sorted(expected_doc_ids)}, "
            f"actual={sorted(found_docs)}"
        )

    if len(probe_vector) != expected_dim:
        raise GuidelineSearchError(
            f"후보 색인 차원 검증 실패: expected={expected_dim}, actual={len(probe_vector)}"
        )

    smoke = collection.query(
        query_embeddings=[probe_vector],
        n_results=1,
        include=["metadatas", "distances"],
    )
    smoke_mds = (smoke.get("metadatas") or [[]])[0]
    if not smoke_mds:
        raise GuidelineSearchError("후보 색인 스모크 질의 결과가 비어 있다.")


def index_guideline_sources(
    *,
    sources_dir: str | Path = DEFAULT_SOURCES_DIR,
    persist_dir: str | Path = DEFAULT_CHROMA_DIR,
    manifest_path: str | Path = DEFAULT_MANIFEST_PATH,
    embedding_model: str = DEFAULT_EMBEDDING_MODEL,
    embedding_backend: EmbeddingBackend,
    chunk_size: int = 900,
    chunk_overlap: int = 180,
    require_approved: bool = True,
    force_rebuild: bool = False,
    batch_size: int = 64,
    batch_writer_hook: Any | None = None,
) -> dict[str, Any]:
    """공식 원문을 새 버전 디렉터리에 구축·검증한 뒤에만 `active_pointer.json`을 교체한다.

    실패 시 새 버전 디렉터리는 `failed` 상태로 남고, 기존 활성 포인터와 색인은 변경되지 않는다.
    """
    import chromadb

    root = Path(persist_dir)
    _, manifest_sha = load_source_manifest(manifest_path)
    fast_hashes = compute_source_hashes(
        sources_dir, manifest_path=manifest_path, require_approved=require_approved
    )

    # 1) 무변경 스킵 (임베딩 API를 호출하지 않되, 로컬 Chroma 컬렉션 정상 열림·건수까지 확인)
    if not force_rebuild and fast_hashes:
        try:
            active_dir, active_meta = resolve_active_version_dir(root)
            expected_chunks = int(active_meta.get("indexed_chunks", 0))
            if (
                active_meta.get("embedding_model") == embedding_model
                and active_meta.get("chunk_size") == chunk_size
                and active_meta.get("chunk_overlap") == chunk_overlap
                and active_meta.get("extractor_version") == EXTRACTOR_VERSION
                and active_meta.get("section_id_version") == SECTION_ID_VERSION
                and active_meta.get("manifest_sha256") == manifest_sha
                and active_meta.get("doc_hashes") == fast_hashes
                and int(active_meta.get("vector_dim", 0)) > 0
                and expected_chunks > 0
            ):
                check_client = chromadb.PersistentClient(path=str(active_dir))
                check_col = check_client.get_collection(name=COLLECTION_NAME)
                if check_col.count() == expected_chunks:
                    return {
                        "success": True,
                        "skipped_unchanged": True,
                        "active_version": active_dir.name,
                        "embedding_model": embedding_model,
                        "vector_dim": int(active_meta["vector_dim"]),
                        "indexed_chunks": expected_chunks,
                        "status_by_artifact": active_meta.get("status_by_artifact", {}),
                        "missing_or_unapproved_doc_ids": active_meta.get(
                            "missing_or_unapproved_doc_ids", []
                        ),
                        "persist_dir": str(root),
                    }
        except Exception:
            pass

    # 2) 매니페스트 검증 및 청킹 (실패 시 기존 활성 색인 무손상)
    try:
        chunks, load_report = load_guideline_chunks(
            sources_dir,
            manifest_path=manifest_path,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            require_approved=require_approved,
            fail_on_approved_issue=True,
        )
    except ValueError as exc:
        raise GuidelineSearchError(str(exc)) from exc

    if not chunks:
        raise GuidelineSearchError(
            f"색인 가능한 승인 문헌이 없다: {sources_dir} "
            f"(미승인/누락={load_report.get('missing_or_unapproved_doc_ids')})"
        )

    # 3) 새 버전 디렉터리 생성 (기존 활성 버전과 완전히 분리)
    version_id = f"v{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
    version_dir = root / VERSIONS_SUBDIR / version_id
    version_dir.mkdir(parents=True, exist_ok=True)
    meta_path = version_dir / INDEX_META_FILENAME

    def _mark_failed(reason: str) -> None:
        _atomic_write_json(
            meta_path,
            {
                "version_id": version_id,
                "status": "failed",
                "error": reason,
                "embedding_model": embedding_model,
                "created_at": datetime.now(UTC).isoformat(),
            },
        )

    try:
        probe_vec = embedding_backend.embed_texts(["dimension probe"])[0]
        vector_dim = len(probe_vec)
        if vector_dim < 1:
            raise GuidelineSearchError("임베딩 차원이 0이다.")

        client = chromadb.PersistentClient(path=str(version_dir))
        collection = client.create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

        for batch_index, i in enumerate(range(0, len(chunks), batch_size)):
            batch = chunks[i : i + batch_size]
            documents = [f"{c.document_title} ({c.section})\n{c.text}" for c in batch]
            vectors = embedding_backend.embed_texts(documents)
            if len(vectors) != len(batch):
                raise GuidelineSearchError(
                    f"임베딩 응답 개수 불일치: expected={len(batch)}, got={len(vectors)}"
                )
            if any(len(v) != vector_dim for v in vectors):
                raise GuidelineSearchError("배치 내 임베딩 벡터 차원이 일관되지 않다.")

            if batch_writer_hook is not None:
                batch_writer_hook(batch_index, batch)

            embeddings_payload: list[Sequence[float]] = [list(v) for v in vectors]
            collection.add(
                ids=[c.chunk_id for c in batch],
                embeddings=embeddings_payload,
                documents=documents,
                metadatas=[
                    {
                        "chunk_id": c.chunk_id,
                        "doc_id": c.doc_id,
                        "artifact_id": c.artifact_id,
                        "section": c.section,
                        "locator": c.locator,
                        "verified_recommendation_no": c.verified_recommendation_no or "",
                        "text": c.text,
                        "source_url": c.source_url,
                        "document_title": c.document_title,
                        "publisher": c.publisher,
                        "published_year_or_edition": c.published_year_or_edition,
                        "actual_source_file": c.actual_source_file,
                        "source_format": c.source_format,
                        "language": c.language,
                        "file_sha256": c.file_sha256,
                        "review_status": c.review_status,
                    }
                    for c in batch
                ],
            )

        # 4) 활성화 전 무결성 검증
        expected_doc_ids = {c.doc_id for c in chunks}
        _verify_candidate_index(
            version_dir=version_dir,
            expected_count=len(chunks),
            expected_doc_ids=expected_doc_ids,
            expected_dim=vector_dim,
            probe_vector=probe_vec,
        )

        indexed_at = datetime.now(UTC).isoformat()
        doc_hashes = {
            aid: info["actual_sha256"]
            for aid, info in load_report["status_by_artifact"].items()
            if info.get("loaded") and info.get("actual_sha256")
        }
        meta_payload = {
            "version_id": version_id,
            "status": "verified",
            "collection_name": COLLECTION_NAME,
            "embedding_model": embedding_model,
            "vector_dim": vector_dim,
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
            "extractor_version": EXTRACTOR_VERSION,
            "section_id_version": SECTION_ID_VERSION,
            "manifest_sha256": manifest_sha,
            "indexed_chunks": len(chunks),
            "loaded_doc_ids": sorted(expected_doc_ids),
            "missing_or_unapproved_doc_ids": load_report.get("missing_or_unapproved_doc_ids", []),
            "doc_hashes": doc_hashes,
            "status_by_artifact": load_report["status_by_artifact"],
            "indexed_at": indexed_at,
        }
        _atomic_write_json(meta_path, meta_payload)

        # 5) 검증 통과 후에만 active_pointer.json 원자 교체
        _atomic_write_json(
            root / ACTIVE_POINTER_FILENAME,
            {
                "active_version": version_id,
                "embedding_model": embedding_model,
                "vector_dim": vector_dim,
                "indexed_chunks": len(chunks),
                "activated_at": indexed_at,
            },
        )
    except Exception as exc:
        _mark_failed(f"{type(exc).__name__}: {exc}")
        if isinstance(exc, GuidelineSearchError):
            raise
        raise GuidelineSearchError(f"Chroma 재색인 실패 ({type(exc).__name__}): {exc}") from exc

    return {
        "success": True,
        "skipped_unchanged": False,
        "active_version": version_id,
        "embedding_model": embedding_model,
        "vector_dim": vector_dim,
        "indexed_chunks": len(chunks),
        "loaded_doc_ids": sorted({c.doc_id for c in chunks}),
        "missing_or_unapproved_doc_ids": load_report.get("missing_or_unapproved_doc_ids", []),
        "status_by_artifact": load_report["status_by_artifact"],
        "persist_dir": str(root),
    }


class ChromaGuidelineSearch:
    """`GuidelineSearch` 계약을 구현하는 버전 분리 Chroma 코사인 벡터 검색기."""

    def __init__(
        self,
        *,
        persist_dir: str | Path = DEFAULT_CHROMA_DIR,
        embedding_backend: EmbeddingBackend,
        embedding_model: str = DEFAULT_EMBEDDING_MODEL,
        min_relevance_score: float = DEFAULT_MIN_RELEVANCE_SCORE,
        enable_bilingual_expand: bool = True,
    ) -> None:
        self.persist_dir = Path(persist_dir)
        self._embedding_backend = embedding_backend
        self.embedding_model = embedding_model
        self.min_relevance_score = min_relevance_score
        self.enable_bilingual_expand = enable_bilingual_expand

    def _open_collection(self, *, version_id: str | None = None) -> tuple[Any, dict[str, Any]]:
        import chromadb

        if version_id is not None:
            version_dir, meta = resolve_version_dir(self.persist_dir, version_id)
        else:
            version_dir, meta = resolve_active_version_dir(self.persist_dir)
        if version_id is None and meta.get("embedding_model") != self.embedding_model:
            raise GuidelineSearchError(
                f"활성 색인 모델({meta.get('embedding_model')})과 "
                f"요청 모델({self.embedding_model})이 다르다."
            )
        try:
            client = chromadb.PersistentClient(path=str(version_dir))
            collection = client.get_collection(name=COLLECTION_NAME)
        except Exception as exc:
            raise GuidelineSearchError(
                f"Chroma 컬렉션 열기 실패 ({type(exc).__name__}): {exc}"
            ) from exc
        return collection, meta

    def _open_active_collection(self) -> tuple[Any, dict[str, Any]]:
        return self._open_collection(version_id=None)

    def _search_sync_scored(
        self, query: str, limit: int, *, apply_threshold: bool = True
    ) -> tuple[list[tuple[GuidelineHit, float, dict[str, Any]]], dict[str, Any]]:
        collection, meta = self._open_active_collection()
        effective_query = expand_bilingual_query(query) if self.enable_bilingual_expand else query
        query_vec = self._embedding_backend.embed_texts([effective_query])[0]

        if meta.get("vector_dim") and len(query_vec) != int(meta["vector_dim"]):
            raise GuidelineSearchError(
                f"임베딩 차원 불일치: index={meta.get('vector_dim')}, query={len(query_vec)}"
            )

        try:
            total_docs = collection.count()
            if total_docs == 0:
                return [], meta
            raw = collection.query(
                query_embeddings=[query_vec],
                n_results=min(limit, total_docs),
                include=["metadatas", "distances", "documents"],
            )
        except Exception as exc:
            raise GuidelineSearchError(
                f"Chroma 컬렉션 조회 실패 ({type(exc).__name__}): {exc}"
            ) from exc

        metadatas = (raw.get("metadatas") or [[]])[0]
        distances = (raw.get("distances") or [[]])[0]
        documents = (raw.get("documents") or [[]])[0]

        scored_hits: list[tuple[GuidelineHit, float, dict[str, Any]]] = []
        for idx, md in enumerate(metadatas):
            dist = float(distances[idx]) if idx < len(distances) else 1.0
            similarity = round(1.0 - dist, 4)
            if apply_threshold and similarity < self.min_relevance_score:
                continue
            doc_id = str(md.get("doc_id", "")).strip()
            section = str(md.get("section", "")).strip()
            fallback_doc = str(documents[idx]) if idx < len(documents) else ""
            text = str(md.get("text", "") or fallback_doc).strip()
            source_url = str(md.get("source_url", "")).strip()
            if not (doc_id and section and text and source_url):
                continue
            scored_hits.append(
                (
                    GuidelineHit(
                        doc_id=doc_id,
                        section=section,
                        text=text,
                        source_url=source_url,
                    ),
                    similarity,
                    dict(md),
                )
            )
            if len(scored_hits) >= limit:
                break
        return scored_hits, meta

    async def search(self, query: str, limit: int = 5) -> tuple[GuidelineHit, ...]:
        """가이드라인을 코사인 유사도로 검색해 `GuidelineHit` 튜플을 돌려준다."""
        if limit < 1:
            raise ValueError("limit은 1 이상이어야 한다")
        if not query or not query.strip():
            return ()
        scored, _ = await asyncio.to_thread(
            self._search_sync_scored, query.strip(), limit, apply_threshold=True
        )
        return tuple(hit for hit, _, _ in scored)

    async def search_with_scores(
        self, query: str, limit: int = 5, *, apply_threshold: bool = True
    ) -> tuple[list[tuple[GuidelineHit, float, dict[str, Any]]], dict[str, Any]]:
        """평가·진단용: 점수·메타데이터·활성 버전 정보를 함께 반환한다."""
        if limit < 1:
            raise ValueError("limit은 1 이상이어야 한다")
        if not query or not query.strip():
            return [], {}
        return await asyncio.to_thread(
            self._search_sync_scored,
            query.strip(),
            limit,
            apply_threshold=apply_threshold,
        )

    def _resolve_evidence_sync(
        self, doc_id: str, section: str, *, version_id: str | None = None
    ) -> GuidelineHit | None:
        collection, _ = self._open_collection(version_id=version_id)
        result = collection.get(
            where={"$and": [{"doc_id": doc_id}, {"section": section}]},
            include=["metadatas"],
        )
        metadatas = result.get("metadatas") or []
        if len(metadatas) != 1:
            return None
        md = metadatas[0]
        text = str(md.get("text", "")).strip()
        source_url = str(md.get("source_url", "")).strip()
        if not (text and source_url):
            return None
        return GuidelineHit(
            doc_id=str(md["doc_id"]).strip(),
            section=str(md["section"]).strip(),
            text=text,
            source_url=source_url,
        )

    async def resolve_evidence(
        self, doc_id: str, section: str, *, version_id: str | None = None
    ) -> GuidelineHit | None:
        """`EvidenceRef(doc_id, section)`에서 정확한 단일 원문 청크를 역추적한다.

        `version_id`를 지정하면 재색인 이후에도 해당 시점 스냅샷에서 원문을 일관되게 조회한다.
        """
        if not doc_id.strip() or not section.strip():
            return None
        return await asyncio.to_thread(
            self._resolve_evidence_sync,
            doc_id.strip(),
            section.strip(),
            version_id=version_id,
        )
