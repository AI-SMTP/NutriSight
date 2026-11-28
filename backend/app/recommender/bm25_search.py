"""외부 API 키 없이 동작하는 순수 파이썬 BM25 기반 `GuidelineSearch` 구현 (v0.2).

개선 사항:
- Unicode NFKC 정규화 및 임상 단위(`g/kg`, `kcal/kg`, `mL`, `50%` 등) 보존
- 한국어 조사·어미 보수적 어간 추출 (`욕창을` → `욕창`, 오분절 `환자→환` 방지)
- 한국어 임상 복합명사 분해·결합 변형 (`경구영양보충` ↔ `경구 영양 보충`, `욕창예방` ↔ `욕창 예방`)
- 매니페스트 승인 정책(`require_approved=True`) 및 `resolve_evidence` 역추적 지원
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from app.recommender.guideline_types import GuidelineHit
from app.recommender.query_expander import expand_bilingual_query
from app.recommender.rag_sources import (
    DEFAULT_MANIFEST_PATH,
    DEFAULT_SOURCES_DIR,
    GuidelineChunk,
    load_guideline_chunks,
)

# 임상 단위(g/kg, kcal/kg, 30g, 50%)와 일반 한·영·숫자 토큰을 함께 보존
_UNIT_TOKEN_RE = re.compile(
    r"(?<!\w)(?:kcal/kg|g/kg|ml/day|\d+(?:\.\d+)?%)(?!\w)",
    re.IGNORECASE,
)
_WORD_TOKEN_RE = re.compile(r"[0-9a-zA-Z가-힣]{2,}")
_HANGUL_ONLY_RE = re.compile(r"^[가-힣]+$")

# 긴 조사부터 매칭하되 명사 어근을 훼손하기 쉬운 1음절('자', '식')은 제외한다.
_SAFE_KO_SUFFIXES: tuple[str, ...] = (
    "에서는",
    "으로는",
    "에게서",
    "에서도",
    "으로도",
    "부터",
    "까지",
    "에서",
    "으로",
    "에게",
    "에는",
    "에도",
    "보다",
    "처럼",
    "하고",
    "이며",
    "이다",
    "한다",
    "하는",
    "되는",
    "은",
    "는",
    "이",
    "가",
    "을",
    "를",
    "의",
    "에",
    "로",
    "와",
    "과",
    "도",
    "만",
)

# 한국어 임상 복합명사 사전 (붙여쓰기 ↔ 띄어쓰기 양방향 정합)
_COMPOUND_SPLITS: dict[str, tuple[str, ...]] = {
    "경구영양보충": ("경구", "영양", "보충"),
    "경구영양보충제": ("경구", "영양", "보충"),
    "영양관리팀": ("영양", "관리", "팀"),
    "영양불량": ("영양", "불량"),
    "영양부족": ("영양", "부족"),
    "영양사정": ("영양", "사정"),
    "욕창예방": ("욕창", "예방"),
    "욕창관리": ("욕창", "관리"),
    "식사강화": ("식사", "강화"),
    "강화식": ("강화", "식사"),
    "식사보조": ("식사", "보조"),
    "섭취부족": ("섭취", "부족"),
    "섭취감소": ("섭취", "감소"),
    "단백질섭취": ("단백질", "섭취"),
    "체중감소": ("체중", "감소"),
    "연하곤란": ("연하", "곤란"),
    "치료식": ("치료", "식이"),
    "제한식": ("제한", "식이"),
    "고단백": ("단백질", "고단백"),
    "인지저하": ("인지", "저하"),
    "식욕저하": ("식욕", "저하"),
    "수분섭취": ("수분", "섭취"),
    "수분섭취량": ("수분", "섭취"),
}


def _strip_korean_suffix(word: str) -> str | None:
    """보수적 한국어 조사 제거: 3음절 이상 순수 한글 단어에서만 2음절 이상 어간이 남을 때만 적용."""
    if len(word) < 3 or not _HANGUL_ONLY_RE.match(word):
        return None
    for suffix in _SAFE_KO_SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 2:
            return word[: -len(suffix)]
    return None


def tokenize(text: str) -> list[str]:
    """NFKC 정규화 + 임상 단위 보존 + 보수적 한국어 조사·복합명사 정규화 토큰화."""
    normalized = unicodedata.normalize("NFKC", text).lower()
    tokens: list[str] = []

    for unit in _UNIT_TOKEN_RE.findall(normalized):
        tokens.append(unit.lower())

    raw_words = _WORD_TOKEN_RE.findall(normalized)
    base_words: list[str] = []
    for word in raw_words:
        tokens.append(word)
        stem = _strip_korean_suffix(word)
        base = stem if stem is not None else word
        base_words.append(base)
        if stem is not None:
            tokens.append(stem)

        # 복합명사 분해 변형 추가
        if base in _COMPOUND_SPLITS:
            for part in _COMPOUND_SPLITS[base]:
                if len(part) >= 2 and part != base:
                    tokens.append(part)

    # 조사 제거된 인접 한글 2단어가 복합명사 사전에 있으면 결합형 토큰 추가
    for idx in range(len(base_words) - 1):
        joined = base_words[idx] + base_words[idx + 1]
        if joined in _COMPOUND_SPLITS:
            tokens.append(joined)

    return tokens


class Bm25GuidelineSearch:
    """`GuidelineSearch` 계약을 구현하는 로컬 BM25Okapi 검색기."""

    def __init__(
        self,
        chunks: Sequence[GuidelineChunk],
        *,
        k1: float = 1.5,
        b: float = 0.75,
        min_score: float = 0.0,
        enable_bilingual_expand: bool = True,
    ) -> None:
        self._chunks = tuple(chunks)
        self._k1 = k1
        self._b = b
        self._min_score = min_score
        self._enable_bilingual_expand = enable_bilingual_expand

        self._evidence_index: dict[tuple[str, str], GuidelineHit] = {}
        self._doc_term_freqs: list[Counter[str]] = []
        self._doc_lengths: list[int] = []
        doc_freq: Counter[str] = Counter()

        for chunk in self._chunks:
            key = (chunk.doc_id, chunk.section)
            if key in self._evidence_index:
                raise ValueError(f"중복된 근거 식별자 감지: {key}")
            self._evidence_index[key] = GuidelineHit(
                doc_id=chunk.doc_id,
                section=chunk.section,
                text=chunk.text,
                source_url=chunk.source_url,
            )

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
        sources_dir: str | Path | None = None,
        *,
        manifest_path: str | Path = DEFAULT_MANIFEST_PATH,
        require_approved: bool = True,
        min_score: float = 0.0,
        enable_bilingual_expand: bool = True,
    ) -> Bm25GuidelineSearch:
        """매니페스트 승인 정책을 통과한 원문에서 BM25 색인을 구성한다."""
        resolved_dir = sources_dir or DEFAULT_SOURCES_DIR
        chunks, report = load_guideline_chunks(
            resolved_dir,
            manifest_path=manifest_path,
            require_approved=require_approved,
            fail_on_approved_issue=True,
        )
        if not chunks:
            raise ValueError(
                f"BM25 색인을 구성할 승인 원문 청크가 0개입니다: {resolved_dir} "
                f"(미승인/누락={report.get('missing_or_unapproved_doc_ids')})"
            )
        return cls(chunks, min_score=min_score, enable_bilingual_expand=enable_bilingual_expand)

    def _score(self, query_terms: Sequence[str], doc_idx: int) -> float:
        tf_map = self._doc_term_freqs[doc_idx]
        doc_len = self._doc_lengths[doc_idx]
        score = 0.0
        # 질의 내 중복 확장 토큰에 의한 점수 과증폭을 방지하기 위해 고유 질의 토큰 기준 집계
        for term in dict.fromkeys(query_terms):
            freq = tf_map.get(term, 0)
            if freq == 0:
                continue
            idf = self._idf.get(term, 0.0)
            denom = freq + self._k1 * (1.0 - self._b + self._b * (doc_len / self._avgdl))
            score += idf * (freq * (self._k1 + 1.0)) / denom
        return score

    async def search_with_scores(
        self, query: str, limit: int = 5
    ) -> list[tuple[GuidelineHit, float]]:
        """평가·진단용: BM25 점수와 함께 상위 `limit`개 결과를 반환한다."""
        if limit < 1:
            raise ValueError("limit은 1 이상이어야 한다")
        if not query or not query.strip() or not self._chunks:
            return []

        effective_query = expand_bilingual_query(query) if self._enable_bilingual_expand else query
        q_tokens = tokenize(effective_query)
        if not q_tokens:
            return []

        scored: list[tuple[float, int]] = []
        for idx in range(len(self._chunks)):
            s = self._score(q_tokens, idx)
            if s > self._min_score:
                scored.append((s, idx))

        scored.sort(key=lambda pair: (-pair[0], self._chunks[pair[1]].chunk_id))
        results: list[tuple[GuidelineHit, float]] = []
        for s, idx in scored[:limit]:
            chunk = self._chunks[idx]
            if not (chunk.doc_id and chunk.section and chunk.text and chunk.source_url):
                continue
            results.append(
                (
                    GuidelineHit(
                        doc_id=chunk.doc_id,
                        section=chunk.section,
                        text=chunk.text,
                        source_url=chunk.source_url,
                    ),
                    round(s, 4),
                )
            )
        return results

    async def search(self, query: str, limit: int = 5) -> tuple[GuidelineHit, ...]:
        """BM25 점수가 임계값을 초과하는 상위 `limit`개 가이드라인 구절을 돌려준다."""
        scored = await self.search_with_scores(query, limit=limit)
        return tuple(hit for hit, _ in scored)

    async def resolve_evidence(self, doc_id: str, section: str) -> GuidelineHit | None:
        """`EvidenceRef(doc_id, section)`에서 정확한 단일 원문 청크를 역추적한다."""
        return self._evidence_index.get((doc_id.strip(), section.strip()))
