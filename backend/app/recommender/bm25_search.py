"""외부 API 키 없이 동작하는 순수 파이썬 BM25 기반 `GuidelineSearch` 구현.

팀 가이드의 BM25 제안안을 충족하며, 외부 임베딩 API 장애나 오프라인 환경에서
즉시 `GUIDELINE_SEARCH=bm25`로 전환할 수 있는 경량 대안 검색기다.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Sequence

from app.recommender.guideline_types import GuidelineHit
from app.recommender.query_expander import expand_bilingual_query
from app.recommender.rag_sources import DEFAULT_SOURCES_DIR, GuidelineChunk, load_guideline_chunks

_TOKEN_RE = re.compile(r"[0-9a-zA-Z가-힣]{2,}")


def tokenize(text: str) -> list[str]:
    """한국어·영문·숫자 2글자 이상 토큰을 추출한다."""
    return _TOKEN_RE.findall(text.lower())


class Bm25GuidelineSearch:
    """`GuidelineSearch` 계약을 구현하는 로컬 BM25Okapi 검색기."""

    def __init__(
        self,
        chunks: Sequence[GuidelineChunk],
        *,
        k1: float = 1.5,
        b: float = 0.75,
        enable_bilingual_expand: bool = True,
    ) -> None:
        self._chunks = tuple(chunks)
        self._k1 = k1
        self._b = b
        self._enable_bilingual_expand = enable_bilingual_expand

        self._doc_term_freqs: list[Counter[str]] = []
        self._doc_lengths: list[int] = []
        doc_freq: Counter[str] = Counter()

        for chunk in self._chunks:
            tokens = tokenize(f"{chunk.document_title} {chunk.section} {chunk.text}")
            tf = Counter(tokens)
            self._doc_term_freqs.append(tf)
            self._doc_lengths.append(len(tokens))
            for term in tf:
                doc_freq[term] += 1

        total_docs = len(self._chunks)
        self._avgdl = (sum(self._doc_lengths) / total_docs) if total_docs else 1.0
        self._idf: dict[str, float] = {
            term: math.log(1.0 + (total_docs - df + 0.5) / (df + 0.5))
            for term, df in doc_freq.items()
        }

    @classmethod
    def from_sources_dir(
        cls,
        sources_dir: str | None = None,
        *,
        enable_bilingual_expand: bool = True,
    ) -> Bm25GuidelineSearch:
        """`docs/research/rag-sources/`에서 원문을 읽어 BM25 색인을 구성한다."""
        chunks, _ = load_guideline_chunks(sources_dir or DEFAULT_SOURCES_DIR)
        return cls(chunks, enable_bilingual_expand=enable_bilingual_expand)

    def _score(self, query_tokens: Sequence[str], doc_idx: int) -> float:
        tf_map = self._doc_term_freqs[doc_idx]
        doc_len = self._doc_lengths[doc_idx]
        score = 0.0
        for term in query_tokens:
            freq = tf_map.get(term, 0)
            if freq == 0:
                continue
            idf = self._idf.get(term, 0.0)
            denom = freq + self._k1 * (1.0 - self._b + self._b * (doc_len / self._avgdl))
            score += idf * (freq * (self._k1 + 1.0)) / denom
        return score

    async def search(self, query: str, limit: int = 5) -> tuple[GuidelineHit, ...]:
        """BM25 점수가 0보다 큰 상위 `limit`개 가이드라인 구절을 돌려준다."""
        if limit < 1:
            raise ValueError("limit은 1 이상이어야 한다")
        if not query or not query.strip() or not self._chunks:
            return ()

        effective_query = expand_bilingual_query(query) if self._enable_bilingual_expand else query
        q_tokens = tokenize(effective_query)
        if not q_tokens:
            return ()

        scored: list[tuple[float, int]] = []
        for idx in range(len(self._chunks)):
            s = self._score(q_tokens, idx)
            if s > 0.0:
                scored.append((s, idx))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        hits: list[GuidelineHit] = []
        for _, idx in scored[:limit]:
            chunk = self._chunks[idx]
            if not (chunk.doc_id and chunk.section and chunk.text and chunk.source_url):
                continue
            hits.append(
                GuidelineHit(
                    doc_id=chunk.doc_id,
                    section=chunk.section,
                    text=chunk.text,
                    source_url=chunk.source_url,
                )
            )
        return tuple(hits)
