"""OpenAI 임베딩 + Chroma 코사인 벡터 기반 `GuidelineSearch` 구현.

실측 평가 기준 기본값:
- 임베딩 모델: `text-embedding-3-large`
  (환경변수 `RAG_EMBEDDING_MODEL`로 `text-embedding-3-small` 전환 가능)
- 유사도 임계값: `min_relevance_score=0.50` (범위 외 질의 거절률 100%, Positive Hit@3 100%)
- 한·영 임상 용어 쿼리 확장: 기본 활성화 (`enable_bilingual_expand=True`)
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from app.recommender.guideline_types import GuidelineHit
from app.recommender.query_expander import expand_bilingual_query
from app.recommender.rag_sources import (
    DEFAULT_CHROMA_DIR,
    DEFAULT_SOURCES_DIR,
    compute_source_hashes,
    load_guideline_chunks,
)

COLLECTION_NAME = "nutrisight_guideline_chunks"
INDEX_META_FILENAME = "index_meta.json"
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-large"
DEFAULT_MIN_RELEVANCE_SCORE = 0.50


class GuidelineSearchError(RuntimeError):
    """가이드라인 색인 누락·모델 불일치·외부 임베딩 호출 실패를 명시적으로 보고하는 예외."""


class EmbeddingBackend(Protocol):
    """외부 OpenAI 임베딩 호출을 테스트에서 모의할 수 있도록 분리한 최소 인터페이스."""

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        """문서 또는 질의 문자열 목록을 임베딩 벡터 목록으로 변환한다."""
        ...


class OpenAIEmbeddingBackend:
    """OpenAI Embeddings API 직접 호출 구현 (LangChain 비의존)."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str = DEFAULT_EMBEDDING_MODEL,
        base_url: str | None = None,
        timeout_s: float = 20.0,
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

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            response = self._client.embeddings.create(model=self.model, input=list(texts))
        except Exception as exc:
            raise GuidelineSearchError(
                f"임베딩 API 호출 실패 ({type(exc).__name__}): {exc}"
            ) from exc
        ordered = sorted(response.data, key=lambda item: item.index)
        return [list(item.embedding) for item in ordered]


def read_index_meta(persist_dir: str | Path) -> dict[str, Any] | None:
    """Chroma 색인 메타데이터 JSON을 읽는다. 없거나 손상되면 None."""
    meta_path = Path(persist_dir) / INDEX_META_FILENAME
    if not meta_path.exists():
        return None
    try:
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def index_guideline_sources(
    *,
    sources_dir: str | Path = DEFAULT_SOURCES_DIR,
    persist_dir: str | Path = DEFAULT_CHROMA_DIR,
    embedding_model: str = DEFAULT_EMBEDDING_MODEL,
    embedding_backend: EmbeddingBackend,
    chunk_size: int = 900,
    chunk_overlap: int = 180,
    force_rebuild: bool = False,
) -> dict[str, Any]:
    """공식 4종 PDF/XML 원문을 Chroma 코사인 컬렉션에 영구 색인한다."""
    import chromadb

    p_dir = Path(persist_dir)
    meta_path = p_dir / INDEX_META_FILENAME

    if not force_rebuild and meta_path.exists() and (p_dir / "chroma.sqlite3").exists():
        prev = read_index_meta(p_dir)
        fast_hashes = compute_source_hashes(sources_dir)
        if (
            prev is not None
            and fast_hashes
            and prev.get("embedding_model") == embedding_model
            and prev.get("chunk_size") == chunk_size
            and prev.get("chunk_overlap") == chunk_overlap
            and prev.get("doc_hashes") == fast_hashes
            and int(prev.get("vector_dim", 0)) > 0
        ):
            probe_dim = len(embedding_backend.embed_texts(["dimension probe"])[0])
            if probe_dim == int(prev["vector_dim"]):
                return {
                    "success": True,
                    "skipped_unchanged": True,
                    "embedding_model": embedding_model,
                    "vector_dim": probe_dim,
                    "indexed_chunks": int(prev.get("indexed_chunks", 0)),
                    "status_by_doc": prev.get("status_by_doc", {}),
                    "persist_dir": str(p_dir),
                }

    chunks, status_by_doc = load_guideline_chunks(
        sources_dir, chunk_size=chunk_size, chunk_overlap=chunk_overlap
    )
    if not chunks:
        raise GuidelineSearchError(f"색인할 공식 PDF/XML 문서가 없다: {sources_dir}")

    probe_dim = len(embedding_backend.embed_texts(["dimension probe"])[0])
    p_dir.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(p_dir))
    existing_names = {c.name for c in client.list_collections()}
    if COLLECTION_NAME in existing_names:
        client.delete_collection(COLLECTION_NAME)

    collection = client.create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )

    batch_size = 64
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        documents = [f"{c.document_title} ({c.section})\n{c.text}" for c in batch]
        vectors = embedding_backend.embed_texts(documents)
        collection.add(
            ids=[c.chunk_id for c in batch],
            embeddings=vectors,
            documents=documents,
            metadatas=[
                {
                    "doc_id": c.doc_id,
                    "section": c.section,
                    "text": c.text,
                    "source_url": c.source_url,
                    "document_title": c.document_title,
                    "language": c.language,
                }
                for c in batch
            ],
        )

    doc_hashes = {
        doc_id: info["file_hash"]
        for doc_id, info in status_by_doc.items()
        if info.get("loaded") and info.get("file_hash")
    }
    meta_payload = {
        "collection_name": COLLECTION_NAME,
        "embedding_model": embedding_model,
        "vector_dim": probe_dim,
        "chunk_size": chunk_size,
        "chunk_overlap": chunk_overlap,
        "indexed_chunks": len(chunks),
        "doc_hashes": doc_hashes,
        "status_by_doc": status_by_doc,
        "created_at": datetime.now(UTC).isoformat(),
    }
    meta_path.write_text(json.dumps(meta_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "success": True,
        "skipped_unchanged": False,
        "embedding_model": embedding_model,
        "vector_dim": probe_dim,
        "indexed_chunks": len(chunks),
        "status_by_doc": status_by_doc,
        "persist_dir": str(p_dir),
    }


class ChromaGuidelineSearch:
    """`GuidelineSearch` 계약을 구현하는 Chroma 코사인 벡터 검색기."""

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

    def _search_sync(self, query: str, limit: int) -> tuple[GuidelineHit, ...]:
        import chromadb

        meta = read_index_meta(self.persist_dir)
        if meta is None or not (self.persist_dir / "chroma.sqlite3").exists():
            raise GuidelineSearchError(
                f"Chroma 가이드라인 색인이 없다: {self.persist_dir}. "
                "먼저 `uv run python scripts/index_guidelines.py`로 색인을 생성하세요."
            )
        if meta.get("embedding_model") != self.embedding_model:
            raise GuidelineSearchError(
                f"색인 모델({meta.get('embedding_model')})과 "
                f"요청 모델({self.embedding_model})이 다르다."
            )

        effective_query = expand_bilingual_query(query) if self.enable_bilingual_expand else query
        query_vec = self._embedding_backend.embed_texts([effective_query])[0]

        if meta.get("vector_dim") and len(query_vec) != int(meta["vector_dim"]):
            raise GuidelineSearchError(
                f"임베딩 차원 불일치: index={meta.get('vector_dim')}, query={len(query_vec)}"
            )

        try:
            client = chromadb.PersistentClient(path=str(self.persist_dir))
            collection = client.get_collection(name=COLLECTION_NAME)
            total_docs = collection.count()
            if total_docs == 0:
                return ()
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

        hits: list[GuidelineHit] = []
        for idx, md in enumerate(metadatas):
            dist = float(distances[idx]) if idx < len(distances) else 1.0
            similarity = 1.0 - dist
            if similarity < self.min_relevance_score:
                continue
            doc_id = str(md.get("doc_id", "")).strip()
            section = str(md.get("section", "")).strip()
            fallback_doc = str(documents[idx]) if idx < len(documents) else ""
            text = str(md.get("text", "") or fallback_doc).strip()
            source_url = str(md.get("source_url", "")).strip()
            if not (doc_id and section and text and source_url):
                continue
            hits.append(
                GuidelineHit(
                    doc_id=doc_id,
                    section=section,
                    text=text,
                    source_url=source_url,
                )
            )
            if len(hits) >= limit:
                break
        return tuple(hits)

    async def search(self, query: str, limit: int = 5) -> tuple[GuidelineHit, ...]:
        """가이드라인을 코사인 유사도로 검색해 `GuidelineHit` 튜플을 돌려준다."""
        if limit < 1:
            raise ValueError("limit은 1 이상이어야 한다")
        if not query or not query.strip():
            return ()
        return await asyncio.to_thread(self._search_sync, query.strip(), limit)
