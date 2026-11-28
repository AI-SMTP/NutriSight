"""`RecommendationGenerator` 계약 테스트 기반 클래스.

구현별 하위 클래스(`Test*`)는 다음 픽스처 두 개를 정의한다.

- `generator`: 검증할 생성기 구현.
- `summary`: 생성기에 넘길 섭취 요약(`IntakeSummary`).

생성기 호출은 `card` 픽스처에서 테스트마다 한 번만 한다.

계약은 결과가 `GeneratedCard`이고 항목이 1개 이상, `item_id`가 유일, 모든 항목이
`added_by = agent`, 공통 검증 규칙(`validate_generated_items`)을 통과하는지까지만 본다.
추천 내용의 임상적 적절성은 실제 구현 트랙의 평가에서 다룬다.
"""

from __future__ import annotations

import pytest

from app.recommender.generator_types import GeneratedCard, RecommendationGenerator
from app.services.item_rules import validate_generated_items
from app.services.ports import AddedBy, IntakeSummary


class RecommendationGeneratorContract:
    """모든 `RecommendationGenerator` 구현이 지켜야 하는 불변 조건."""

    @pytest.fixture
    def generator(self) -> RecommendationGenerator:
        """하위 클래스가 검증할 구현을 돌려준다."""
        raise NotImplementedError("하위 클래스가 generator 픽스처를 정의해야 한다")

    @pytest.fixture
    def summary(self) -> IntakeSummary:
        """하위 클래스가 생성기 입력 요약을 돌려준다."""
        raise NotImplementedError("하위 클래스가 summary 픽스처를 정의해야 한다")

    @pytest.fixture
    async def card(
        self, generator: RecommendationGenerator, summary: IntakeSummary
    ) -> GeneratedCard:
        """생성기를 한 번만 호출한 결과. 실제 구현의 호출 비용을 줄이려고 테스트마다 공유한다."""
        return await generator.generate(summary.patient_id, summary)

    def test_returns_generated_card(self, card: object) -> None:
        assert isinstance(card, GeneratedCard)
        assert isinstance(card.items, tuple)
        assert isinstance(card.cautions, tuple)

    def test_has_at_least_one_item(self, card: GeneratedCard) -> None:
        assert len(card.items) >= 1

    def test_item_ids_are_unique(self, card: GeneratedCard) -> None:
        ids = [item.item_id for item in card.items]
        assert len(ids) == len(set(ids))

    def test_every_item_is_added_by_agent(self, card: GeneratedCard) -> None:
        assert all(item.added_by is AddedBy.AGENT for item in card.items)

    def test_passes_generated_item_rules(self, card: GeneratedCard) -> None:
        validate_generated_items(card.items, card.cautions)
