"""`GuidelineSearch` 계약 테스트 기반 클래스.

구현별 하위 클래스(`Test*`)는 `search` 픽스처만 정의한다. 질의 샘플 픽스처는
기본값을 제공하며 하위 클래스가 덮어쓸 수 있다.

계약은 반환 타입, 결과 수 상한, 필드가 비어 있지 않음, `limit < 1`의 `ValueError`까지만 본다.
검색 품질(순위·관련도)은 실제 구현 트랙의 평가에서 다룬다.
"""

from __future__ import annotations

import pytest

from app.recommender.guideline_types import GuidelineHit, GuidelineSearch

DEFAULT_LIMIT = 5


class GuidelineSearchContract:
    """모든 `GuidelineSearch` 구현이 지켜야 하는 불변 조건."""

    @pytest.fixture
    def search(self) -> GuidelineSearch:
        """하위 클래스가 검증할 구현을 돌려준다."""
        raise NotImplementedError("하위 클래스가 search 픽스처를 정의해야 한다")

    @pytest.fixture
    def query(self) -> str:
        """가이드라인 검색 질의 샘플."""
        return "노인 단백질 섭취 부족 식사 강화"

    async def test_returns_tuple_of_guideline_hits(
        self, search: GuidelineSearch, query: str
    ) -> None:
        result = await search.search(query, limit=DEFAULT_LIMIT)

        assert isinstance(result, tuple)
        assert all(isinstance(hit, GuidelineHit) for hit in result)

    @pytest.mark.parametrize("limit", [1, 2, 5])
    async def test_result_count_does_not_exceed_limit(
        self, search: GuidelineSearch, query: str, limit: int
    ) -> None:
        result = await search.search(query, limit=limit)

        assert len(result) <= limit

    async def test_every_hit_has_non_empty_string_fields(
        self, search: GuidelineSearch, query: str
    ) -> None:
        result = await search.search(query, limit=DEFAULT_LIMIT)

        for hit in result:
            assert isinstance(hit, GuidelineHit)
            for value in (hit.doc_id, hit.section, hit.text, hit.source_url):
                assert isinstance(value, str)
                assert value.strip() != ""

    @pytest.mark.parametrize("limit", [0, -1])
    async def test_limit_below_one_raises_value_error(
        self, search: GuidelineSearch, query: str, limit: int
    ) -> None:
        with pytest.raises(ValueError):
            await search.search(query, limit=limit)

    async def test_default_limit_is_at_most_five(self, search: GuidelineSearch, query: str) -> None:
        result = await search.search(query)

        assert isinstance(result, tuple)
        assert len(result) <= DEFAULT_LIMIT
