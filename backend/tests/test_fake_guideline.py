"""`FakeGuidelineSearch`의 계약 테스트와 Fake 전용 동작 테스트."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from app.recommender.fake_guideline import FakeGuidelineSearch
from app.recommender.guideline_types import GuidelineHit
from tests.contracts.guideline import GuidelineSearchContract

# 구현 상수를 가져오지 않고 기대값을 따로 고정한다 (구현을 자기 자신과 비교하지 않기 위해).
EXPECTED_PASSAGE_KEYS = (
    ("espen_geriatrics", "R20"),
    ("espen_geriatrics", "R23"),
    ("kjg_elderly_nutrition_2019", "단백질 섭취"),
)


class TestFakeGuidelineContract(GuidelineSearchContract):
    @pytest.fixture
    def search(self) -> FakeGuidelineSearch:
        return FakeGuidelineSearch()


@pytest.mark.parametrize(
    ("limit", "expected_count"),
    [(1, 1), (2, 2), (3, 3), (4, 3), (10, 3)],
)
async def test_result_count_is_min_of_limit_and_three(limit: int, expected_count: int) -> None:
    result = await FakeGuidelineSearch().search("노인 단백질", limit=limit)

    assert len(result) == expected_count


async def test_default_limit_returns_all_three_fixed_passages_in_order() -> None:
    result = await FakeGuidelineSearch().search("노인 단백질")

    assert tuple((hit.doc_id, hit.section) for hit in result) == EXPECTED_PASSAGE_KEYS


@pytest.mark.parametrize("limit", [1, 2, 3, 5])
async def test_same_limit_gives_same_passages_regardless_of_query(limit: int) -> None:
    search = FakeGuidelineSearch()

    first = await search.search("노인 단백질 섭취 부족 식사 강화", limit=limit)
    second = await search.search("욕창 예방 영양", limit=limit)
    empty = await search.search("", limit=limit)

    assert first == second == empty
    assert tuple((hit.doc_id, hit.section) for hit in first) == EXPECTED_PASSAGE_KEYS[:limit]


def test_guideline_hit_is_frozen() -> None:
    hit = GuidelineHit(
        doc_id="espen_geriatrics", section="R20", text="구절", source_url="https://example.org"
    )

    with pytest.raises(FrozenInstanceError):
        hit.text = "변경"  # type: ignore[misc]
