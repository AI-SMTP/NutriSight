"""가이드라인 검색 계약 (`GuidelineHit`, `GuidelineSearch`)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class GuidelineHit:
    """검색된 가이드라인 구절 하나. `doc_id`·`section`은 추천 항목 `evidence`와 같다."""

    doc_id: str
    section: str
    text: str
    source_url: str


class GuidelineSearch(Protocol):
    """가이드라인 검색 어댑터가 따르는 인터페이스."""

    async def search(self, query: str, limit: int = 5) -> tuple[GuidelineHit, ...]:
        """결과 수는 `limit` 이하다. `limit < 1`이면 `ValueError`, 결과가 없으면 빈 tuple."""
        ...
