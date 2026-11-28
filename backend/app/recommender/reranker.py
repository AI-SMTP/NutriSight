"""Cross-Encoder Reranker 인터페이스, ONNX CPU 어댑터 및 안전한 Fallback 검색 래퍼.

설계 원칙:
- Reranker는 1단계 검색(BM25/Dense/Hybrid)이 반환한 후보(`GuidelineHit`)의 순위만 재정렬한다.
- 원문 식별자(`doc_id`, `section`, `source_url`, `text`)를 절대 변조하거나
  새 인용을 생성하지 않는다.
- 긴 구절·표 주석이 모델 최대 토큰을 초과해 잘릴 경우 `truncated_count`와 로그로
  명시적 경고를 남긴다.
- 모델 파일 누락·런타임 미설치·추론 오류 시 예외로 전체 RAG를 중단하지 않고
  `RERANK_UNAVAILABLE` 상태와 함께 1단계 검증 순위로 안전하게 fallback한다.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import math
import time
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

from app.recommender.guideline_types import GuidelineHit, GuidelineSearch

logger = logging.getLogger(__name__)

DEFAULT_BGE_ONNX_MODEL_NAME = "BAAI/bge-reranker-v2-m3 (ONNX INT8)"
DEFAULT_BGE_ONNX_DIR = (
    Path(__file__).resolve().parents[2] / "var" / "models" / "bge-reranker-v2-m3-onnx-int8"
)
DEFAULT_MAX_TOKENS = 512
DEFAULT_RERANK_CANDIDATES = 10


class RerankStatus(StrEnum):
    """Reranker 실행 상태."""

    OK = "ok"
    RERANK_UNAVAILABLE = "rerank_unavailable"


@dataclass(frozen=True)
class RerankScore:
    """단일 후보 구절의 재정렬 점수 및 절단 여부."""

    hit: GuidelineHit
    score: float
    original_rank: int
    truncated: bool = False


@dataclass(frozen=True)
class RerankResult:
    """Reranker 실행 결과."""

    status: RerankStatus
    hits: tuple[GuidelineHit, ...]
    scored: tuple[RerankScore, ...]
    model_name: str
    truncated_count: int = 0
    fallback_reason: str | None = None
    latency_ms: float = 0.0


class HitReranker(Protocol):
    """후보 `GuidelineHit` 목록의 순위를 재정렬하는 Reranker 계약."""

    model_name: str

    async def rerank(
        self,
        query: str,
        candidates: Sequence[GuidelineHit],
        *,
        limit: int = 3,
    ) -> RerankResult:
        """`candidates` 중 상위 `limit`개를 재정렬해 반환한다."""
        ...


def _sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


class OnnxBgeReranker:
    """`onnxruntime` + `tokenizers` 기반 로컬 CPU `BAAI/bge-reranker-v2-m3` ONNX Reranker.

    - PyTorch 없이 백엔드 기본 의존성(`onnxruntime`, `tokenizers`, `numpy`)만으로 동작한다.
    - batch size 1로 추론해 결정적 점수와 안정적인 CPU 메모리 사용량을 유지한다.
    - 모델 파일이나 런타임이 없으면 예외를 던지지 않고
      `RERANK_UNAVAILABLE`로 fallback 신호를 반환한다.
    """

    def __init__(
        self,
        *,
        model_dir: str | Path = DEFAULT_BGE_ONNX_DIR,
        model_filename: str = "model_int8.onnx",
        tokenizer_filename: str = "tokenizer.json",
        model_name: str = DEFAULT_BGE_ONNX_MODEL_NAME,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        intra_op_num_threads: int = 2,
    ) -> None:
        self.model_dir = Path(model_dir)
        self.model_filename = model_filename
        self.tokenizer_filename = tokenizer_filename
        self.model_name = model_name
        self.max_tokens = max_tokens
        self.intra_op_num_threads = intra_op_num_threads
        self._session: Any | None = None
        self._tokenizer: Any | None = None
        self._input_names: set[str] = set()

    def _ensure_loaded(self) -> tuple[Any, Any]:
        if self._session is not None and self._tokenizer is not None:
            return self._session, self._tokenizer

        model_path = self.model_dir / self.model_filename
        tokenizer_path = self.model_dir / self.tokenizer_filename
        if not model_path.exists() or not tokenizer_path.exists():
            raise FileNotFoundError(
                f"ONNX Reranker 모델 파일이 없다: {model_path} / {tokenizer_path}"
            )

        import onnxruntime as ort
        from tokenizers import Tokenizer

        sess_options = ort.SessionOptions()
        sess_options.intra_op_num_threads = self.intra_op_num_threads
        sess_options.inter_op_num_threads = 1
        sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

        session = ort.InferenceSession(
            str(model_path),
            sess_options=sess_options,
            providers=["CPUExecutionProvider"],
        )
        tokenizer = Tokenizer.from_file(str(tokenizer_path))
        tokenizer.no_padding()
        tokenizer.no_truncation()

        self._session = session
        self._tokenizer = tokenizer
        self._input_names = {inp.name for inp in session.get_inputs()}
        return session, tokenizer

    def _rerank_sync(
        self,
        query: str,
        candidates: Sequence[GuidelineHit],
        *,
        limit: int,
    ) -> RerankResult:
        t0 = time.perf_counter()
        if not candidates:
            return RerankResult(
                status=RerankStatus.OK,
                hits=(),
                scored=(),
                model_name=self.model_name,
                latency_ms=0.0,
            )

        try:
            session, tokenizer = self._ensure_loaded()
            import numpy as np
        except Exception as exc:
            elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            reason = f"RERANK_UNAVAILABLE ({type(exc).__name__}): {exc}"
            logger.warning("OnnxBgeReranker 로드 실패 — 1단계 순위 fallback (%s)", reason)
            fallback_hits = tuple(candidates[:limit])
            return RerankResult(
                status=RerankStatus.RERANK_UNAVAILABLE,
                hits=fallback_hits,
                scored=tuple(
                    RerankScore(hit=h, score=0.0, original_rank=idx, truncated=False)
                    for idx, h in enumerate(fallback_hits, start=1)
                ),
                model_name=self.model_name,
                fallback_reason=reason,
                latency_ms=elapsed_ms,
            )

        scored_items: list[RerankScore] = []
        truncated_count = 0

        try:
            for orig_rank, hit in enumerate(candidates, start=1):
                passage = f"[{hit.doc_id} {hit.section}] {hit.text}"
                encoded = tokenizer.encode(query, passage)
                ids = encoded.ids
                mask = encoded.attention_mask
                truncated = False
                if len(ids) > self.max_tokens:
                    truncated = True
                    truncated_count += 1
                    # 마지막 SEP 토큰을 보존하면서 최대 길이로 절단
                    ids = ids[: self.max_tokens - 1] + [ids[-1]]
                    mask = mask[: self.max_tokens]

                feed: dict[str, Any] = {
                    "input_ids": np.asarray([ids], dtype=np.int64),
                    "attention_mask": np.asarray([mask], dtype=np.int64),
                }
                if "token_type_ids" in self._input_names:
                    type_ids = encoded.type_ids[: len(ids)]
                    feed["token_type_ids"] = np.asarray([type_ids], dtype=np.int64)

                outputs = session.run(None, feed)
                logit = float(np.asarray(outputs[0]).reshape(-1)[0])
                prob = round(_sigmoid(logit), 6)
                scored_items.append(
                    RerankScore(
                        hit=hit,
                        score=prob,
                        original_rank=orig_rank,
                        truncated=truncated,
                    )
                )
        except Exception as exc:
            elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            reason = f"RERANK_UNAVAILABLE ({type(exc).__name__}): {exc}"
            logger.warning("OnnxBgeReranker 추론 실패 — 1단계 순위 fallback (%s)", reason)
            fallback_hits = tuple(candidates[:limit])
            return RerankResult(
                status=RerankStatus.RERANK_UNAVAILABLE,
                hits=fallback_hits,
                scored=tuple(
                    RerankScore(hit=h, score=0.0, original_rank=idx, truncated=False)
                    for idx, h in enumerate(fallback_hits, start=1)
                ),
                model_name=self.model_name,
                fallback_reason=reason,
                latency_ms=elapsed_ms,
            )

        if truncated_count > 0:
            logger.warning(
                "OnnxBgeReranker 입력 절단 발생: %d/%d개 후보가 max_tokens=%d를 초과함",
                truncated_count,
                len(candidates),
                self.max_tokens,
            )

        # 점수 내림차순, 동점 시 1단계 원래 순위 오름차순으로 결정적 정렬
        scored_items.sort(key=lambda item: (-item.score, item.original_rank))
        top_scored = tuple(scored_items[:limit])
        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        return RerankResult(
            status=RerankStatus.OK,
            hits=tuple(item.hit for item in top_scored),
            scored=top_scored,
            model_name=self.model_name,
            truncated_count=truncated_count,
            latency_ms=elapsed_ms,
        )

    async def rerank(
        self,
        query: str,
        candidates: Sequence[GuidelineHit],
        *,
        limit: int = 3,
    ) -> RerankResult:
        if limit < 1:
            raise ValueError("limit은 1 이상이어야 한다")
        return await asyncio.to_thread(self._rerank_sync, query, candidates, limit=limit)


class RerankedGuidelineSearch:
    """1단계 검색기(`GuidelineSearch`) + `HitReranker`를 결합하는 2단계 검색기.

    - Reranker가 `RERANK_UNAVAILABLE`를 반환하거나 예외를 던져도
      1단계 검증 순위로 안전하게 fallback한다.
    - `resolve_evidence`를 1단계 검색기에 그대로 위임해 인용 무결성 검증 계약을 유지한다.
    """

    def __init__(
        self,
        *,
        base_search: GuidelineSearch,
        reranker: HitReranker,
        rerank_top_n: int = DEFAULT_RERANK_CANDIDATES,
    ) -> None:
        if rerank_top_n < 1:
            raise ValueError("rerank_top_n은 1 이상이어야 한다")
        self._base = base_search
        self._reranker = reranker
        self.rerank_top_n = rerank_top_n
        self.last_rerank_result: RerankResult | None = None

    async def search_with_details(self, query: str, limit: int = 5) -> RerankResult:
        """1단계 후보 조회 후 Reranker 재정렬 결과와 상태(OK/RERANK_UNAVAILABLE)를 반환한다."""
        if limit < 1:
            raise ValueError("limit은 1 이상이어야 한다")
        cleaned = query.strip() if query else ""
        if not cleaned:
            empty = RerankResult(
                status=RerankStatus.OK,
                hits=(),
                scored=(),
                model_name=self._reranker.model_name,
            )
            self.last_rerank_result = empty
            return empty

        fetch_k = max(self.rerank_top_n, limit)
        candidates = await self._base.search(cleaned, limit=fetch_k)
        if not candidates:
            empty = RerankResult(
                status=RerankStatus.OK,
                hits=(),
                scored=(),
                model_name=self._reranker.model_name,
            )
            self.last_rerank_result = empty
            return empty

        try:
            result = await self._reranker.rerank(cleaned, candidates, limit=limit)
        except Exception as exc:
            reason = f"RERANK_UNAVAILABLE ({type(exc).__name__}): {exc}"
            logger.warning("RerankedGuidelineSearch 예외 — 1단계 순위 fallback (%s)", reason)
            fallback_hits = tuple(candidates[:limit])
            result = RerankResult(
                status=RerankStatus.RERANK_UNAVAILABLE,
                hits=fallback_hits,
                scored=tuple(
                    RerankScore(hit=h, score=0.0, original_rank=idx, truncated=False)
                    for idx, h in enumerate(fallback_hits, start=1)
                ),
                model_name=self._reranker.model_name,
                fallback_reason=reason,
            )

        # 불변성 방어: Reranker가 원본 후보 외의 항목을 반환하지 못하게 교차 검증
        allowed = {(h.doc_id, h.section): h for h in candidates}
        verified_hits = tuple(
            allowed[(h.doc_id, h.section)] for h in result.hits if (h.doc_id, h.section) in allowed
        )[:limit]
        if len(verified_hits) != len(result.hits):
            logger.error("Reranker가 원본 후보 외 인용을 반환해 1단계 순위로 fallback합니다.")
            fallback_hits = tuple(candidates[:limit])
            result = RerankResult(
                status=RerankStatus.RERANK_UNAVAILABLE,
                hits=fallback_hits,
                scored=tuple(
                    RerankScore(hit=h, score=0.0, original_rank=idx, truncated=False)
                    for idx, h in enumerate(fallback_hits, start=1)
                ),
                model_name=self._reranker.model_name,
                fallback_reason="RERANK_UNAVAILABLE: unverified_candidate_detected",
                latency_ms=result.latency_ms,
            )

        self.last_rerank_result = result
        return result

    async def search(self, query: str, limit: int = 5) -> tuple[GuidelineHit, ...]:
        """`GuidelineSearch` 계약: 재정렬 상위 `limit`개 가이드라인 구절을 돌려준다."""
        result = await self.search_with_details(query, limit=limit)
        return result.hits

    async def resolve_evidence(
        self, doc_id: str, section: str, *, version_id: str | None = None
    ) -> GuidelineHit | None:
        """`EvidenceRef(doc_id, section)` 역조회를 1단계 검색기에 위임한다."""
        resolver: Any = getattr(self._base, "resolve_evidence", None)
        if not inspect.iscoroutinefunction(resolver):
            return None
        sig = inspect.signature(resolver)
        if "version_id" in sig.parameters and version_id is not None:
            return await resolver(doc_id, section, version_id=version_id)
        return await resolver(doc_id, section)
