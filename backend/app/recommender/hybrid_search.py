"""BM25 + Dense(Chroma) RRF 결합 하이브리드 `GuidelineSearch` 구현.

설계 원칙:
- 공용 계약(`GuidelineSearch`, `GuidelineHit`)을 변경하지 않는다.
- 1단계 후보 생성: BM25 Top N(기본 10) + Dense Top N(기본 10)을 독립 조회 후
  `(doc_id, section)` 기준으로 중복 제거한다.
- 2단계 결합: Reciprocal Rank Fusion(RRF) `score = sum(weight / (k + rank))`
  (기본 `k=60`, 1-based rank)으로 결합하고, 동점 시 `(doc_id, section)` 오름차순으로
  결정적(deterministic) 정렬한다.
- Dense 장애 처리: Dense 검색 실패 시 `DEGRADED_BM25_FALLBACK` 상태와 오류 사유를
  명시적으로 기록·로깅해 정상 `hybrid` 수치와 저하(fallback) 결과가 섞이지 않게 한다.
- 원문 역조회(`resolve_evidence`): `EvidenceRef(doc_id, section)` 검증 계약을 유지한다.
"""

from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass
from enum import StrEnum

from app.recommender.guideline_types import GuidelineHit, GuidelineSearch

logger = logging.getLogger(__name__)

DEFAULT_CANDIDATE_K = 10
DEFAULT_RRF_K = 60


class HybridStatus(StrEnum):
    """하이브리드 검색 실행 상태."""

    OK = "ok"
    DEGRADED_BM25_FALLBACK = "degraded_bm25_fallback"


@dataclass(frozen=True)
class HybridCandidate:
    """RRF 결합 단계의 단일 후보와 출처별 순위·점수 추적 정보."""

    hit: GuidelineHit
    rrf_score: float
    bm25_rank: int | None = None
    dense_rank: int | None = None
    bm25_score: float | None = None
    dense_score: float | None = None


@dataclass(frozen=True)
class HybridSearchResult:
    """평가·진단·Reranker 연계를 위한 하이브리드 검색 상세 결과."""

    hits: tuple[GuidelineHit, ...]
    candidates: tuple[HybridCandidate, ...]
    status: HybridStatus
    dense_error: str | None = None
    bm25_count: int = 0
    dense_count: int = 0
    merged_count: int = 0


def fuse_rrf(
    bm25_hits: tuple[GuidelineHit, ...] | list[GuidelineHit],
    dense_hits: tuple[GuidelineHit, ...] | list[GuidelineHit],
    *,
    rrf_k: int = DEFAULT_RRF_K,
    bm25_weight: float = 1.0,
    dense_weight: float = 1.0,
    bm25_scores: dict[tuple[str, str], float] | None = None,
    dense_scores: dict[tuple[str, str], float] | None = None,
) -> tuple[HybridCandidate, ...]:
    """BM25·Dense 순위 목록을 `(doc_id, section)` 기준으로 중복 제거하고 RRF 점수로 정렬한다."""
    if rrf_k < 1:
        raise ValueError("rrf_k는 1 이상이어야 한다")

    hit_by_key: dict[tuple[str, str], GuidelineHit] = {}
    rrf_by_key: dict[tuple[str, str], float] = {}
    bm25_rank_by_key: dict[tuple[str, str], int] = {}
    dense_rank_by_key: dict[tuple[str, str], int] = {}

    for rank, hit in enumerate(dense_hits, start=1):
        key = (hit.doc_id, hit.section)
        if key in dense_rank_by_key:
            continue
        dense_rank_by_key[key] = rank
        hit_by_key[key] = hit
        rrf_by_key[key] = rrf_by_key.get(key, 0.0) + dense_weight / (rrf_k + rank)

    for rank, hit in enumerate(bm25_hits, start=1):
        key = (hit.doc_id, hit.section)
        if key in bm25_rank_by_key:
            continue
        bm25_rank_by_key[key] = rank
        if key not in hit_by_key:
            hit_by_key[key] = hit
        rrf_by_key[key] = rrf_by_key.get(key, 0.0) + bm25_weight / (rrf_k + rank)

    candidates = [
        HybridCandidate(
            hit=hit_by_key[key],
            rrf_score=round(score, 8),
            bm25_rank=bm25_rank_by_key.get(key),
            dense_rank=dense_rank_by_key.get(key),
            bm25_score=bm25_scores.get(key) if bm25_scores else None,
            dense_score=dense_scores.get(key) if dense_scores else None,
        )
        for key, score in rrf_by_key.items()
    ]
    candidates.sort(key=lambda c: (-c.rrf_score, c.hit.doc_id, c.hit.section))
    return tuple(candidates)


async def _query_with_optional_scores(
    backend: GuidelineSearch, query: str, limit: int
) -> tuple[tuple[GuidelineHit, ...], dict[tuple[str, str], float]]:
    """백엔드가 `search_with_scores`를 제공하면 점수도 함께 수집하고, 아니면 `search`를 호출한다."""
    scored_fn = getattr(backend, "search_with_scores", None)
    if callable(scored_fn):
        raw = await scored_fn(query, limit=limit)
        # ChromaGuidelineSearch.search_with_scores -> (list[(hit, score, md)], meta)
        # Bm25GuidelineSearch.search_with_scores -> list[(hit, score)]
        items = raw[0] if isinstance(raw, tuple) and len(raw) == 2 else raw
        hits: list[GuidelineHit] = []
        scores: dict[tuple[str, str], float] = {}
        for item in items:
            hit = item[0]
            score = float(item[1])
            hits.append(hit)
            scores[(hit.doc_id, hit.section)] = score
        return tuple(hits), scores

    hits_tuple = await backend.search(query, limit=limit)
    return hits_tuple, {}


class HybridGuidelineSearch:
    """BM25 + Dense(Chroma) RRF 하이브리드 `GuidelineSearch` 구현."""

    def __init__(
        self,
        *,
        bm25_search: GuidelineSearch,
        dense_search: GuidelineSearch,
        candidate_k: int = DEFAULT_CANDIDATE_K,
        rrf_k: int = DEFAULT_RRF_K,
        bm25_weight: float = 1.0,
        dense_weight: float = 1.0,
        fallback_to_bm25_on_dense_error: bool = True,
        require_dense_hit_when_ok: bool = True,
    ) -> None:
        if candidate_k < 1:
            raise ValueError("candidate_k는 1 이상이어야 한다")
        if rrf_k < 1:
            raise ValueError("rrf_k는 1 이상이어야 한다")
        self._bm25 = bm25_search
        self._dense = dense_search
        self.candidate_k = candidate_k
        self.rrf_k = rrf_k
        self.bm25_weight = bm25_weight
        self.dense_weight = dense_weight
        self.fallback_to_bm25_on_dense_error = fallback_to_bm25_on_dense_error
        self.require_dense_hit_when_ok = require_dense_hit_when_ok
        self.last_status: HybridStatus = HybridStatus.OK
        self.last_dense_error: str | None = None

    async def search_with_details(self, query: str, limit: int = 5) -> HybridSearchResult:
        """RRF 후보군·상태·장애 여부를 포함한 하이브리드 검색 상세 결과를 반환한다."""
        if limit < 1:
            raise ValueError("limit은 1 이상이어야 한다")
        cleaned = query.strip() if query else ""
        if not cleaned:
            self.last_status = HybridStatus.OK
            self.last_dense_error = None
            return HybridSearchResult(
                hits=(),
                candidates=(),
                status=HybridStatus.OK,
            )

        fetch_k = max(self.candidate_k, limit)
        bm25_hits, bm25_scores = await _query_with_optional_scores(self._bm25, cleaned, fetch_k)

        dense_hits: tuple[GuidelineHit, ...] = ()
        dense_scores: dict[tuple[str, str], float] = {}
        status = HybridStatus.OK
        dense_error: str | None = None

        try:
            dense_hits, dense_scores = await _query_with_optional_scores(
                self._dense, cleaned, fetch_k
            )
        except Exception as exc:
            dense_error = f"{type(exc).__name__}: {exc}"
            if not self.fallback_to_bm25_on_dense_error:
                self.last_status = HybridStatus.DEGRADED_BM25_FALLBACK
                self.last_dense_error = dense_error
                raise
            status = HybridStatus.DEGRADED_BM25_FALLBACK
            logger.warning(
                "HybridGuidelineSearch dense 검색 실패 — BM25 fallback으로 전환 (%s)",
                dense_error,
            )

        # Dense가 정상 실행되었으나 임계값 통과 결과가 0건이면 범위 밖(OOS) 질의로 간주하고
        # BM25 약한 어휘 잡음이 OOS 차단을 우회하지 않도록 빈 결과를 반환한다.
        if self.require_dense_hit_when_ok and status == HybridStatus.OK and len(dense_hits) == 0:
            self.last_status = status
            self.last_dense_error = None
            return HybridSearchResult(
                hits=(),
                candidates=(),
                status=status,
                dense_error=None,
                bm25_count=len(bm25_hits),
                dense_count=0,
                merged_count=0,
            )

        candidates = fuse_rrf(
            bm25_hits,
            dense_hits,
            rrf_k=self.rrf_k,
            bm25_weight=self.bm25_weight,
            dense_weight=self.dense_weight,
            bm25_scores=bm25_scores,
            dense_scores=dense_scores,
        )
        top_hits = tuple(c.hit for c in candidates[:limit])

        self.last_status = status
        self.last_dense_error = dense_error
        return HybridSearchResult(
            hits=top_hits,
            candidates=candidates,
            status=status,
            dense_error=dense_error,
            bm25_count=len(bm25_hits),
            dense_count=len(dense_hits),
            merged_count=len(candidates),
        )

    async def search(self, query: str, limit: int = 5) -> tuple[GuidelineHit, ...]:
        """`GuidelineSearch` 계약: RRF 결합 상위 `limit`개 가이드라인 구절을 돌려준다."""
        result = await self.search_with_details(query, limit=limit)
        return result.hits

    async def resolve_evidence(
        self, doc_id: str, section: str, *, version_id: str | None = None
    ) -> GuidelineHit | None:
        """`EvidenceRef(doc_id, section)`을 Dense 또는 BM25 승인 색인에서 역조회한다."""
        for backend in (self._dense, self._bm25):
            resolver = getattr(backend, "resolve_evidence", None)
            if not callable(resolver):
                continue
            sig = inspect.signature(resolver)
            if "version_id" in sig.parameters and version_id is not None:
                try:
                    resolved = await resolver(doc_id, section, version_id=version_id)
                except Exception:
                    resolved = None
            else:
                try:
                    resolved = await resolver(doc_id, section)
                except Exception:
                    resolved = None
            if resolved is not None:
                return resolved
        return None
