"""추천 생성기 계약 (`GeneratedCard`, `GenerationError`, `RecommendationGenerator`)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.services.ports import IntakeSummary, RecommendationItem


@dataclass(frozen=True)
class GeneratedCard:
    """생성기가 만든 카드 내용. 저장 전에 `validate_generated_card`로 전체 필드를 확인한다."""

    items: tuple[RecommendationItem, ...]  # 1개 이상, item_id 유일, added_by = agent
    cautions: tuple[str, ...]


class GenerationError(Exception):
    """생성기가 카드를 만들지 못했을 때 던진다."""


class RecommendationGenerator(Protocol):
    """추천 생성기(Fake·실제 에이전트)가 따르는 인터페이스."""

    async def generate(self, patient_id: str, summary: IntakeSummary) -> GeneratedCard:
        """실패하면 GenerationError를 던진다."""
        ...
