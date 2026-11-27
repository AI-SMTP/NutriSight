"""외부 호출 없이 정해진 결과를 돌려주는 `FakeEstimator`.

실행 중 더미 구현이자 계약 테스트 대상이다. 같은 요청에는 항상 같은 결과를 낸다.
"""

from __future__ import annotations

from asyncio import sleep
from collections.abc import Mapping
from enum import StrEnum

from app.intake.types import (
    EstimationError,
    EstimationRequest,
    EstimationResult,
    QualityIssue,
    SlotEstimate,
    SlotSpec,
    SlotStatus,
)

# 칸 순서에 따라 반복해서 돌려주는 섭취 비율 (0~1, 0.1 단위)
DEFAULT_FRACTIONS: tuple[float, ...] = (1.0, 0.8, 0.5, 0.3, 0.0, 0.6)
FAKE_MODEL_ID = "fake"
MS_PER_SECOND = 1000


class FakeScenario(StrEnum):
    """`meal_order_id`별로 지정할 수 있는 결과 종류."""

    SUCCESS = "success"
    SLOT_NOT_DETERMINABLE = "slot_not_determinable"  # 첫 칸만 판단 불가 + angle
    IMAGE_NOT_DETERMINABLE = "image_not_determinable"  # 사진 전체 판단 불가 + blur
    ERROR = "error"  # EstimationError


class FakeEstimator:
    """시나리오 매핑과 지연 시간만으로 동작하는 섭취 추정 더미."""

    name = "fake"

    def __init__(self, scenarios: Mapping[str, str] | None = None, delay_s: float = 0.0) -> None:
        if delay_s < 0:
            raise ValueError("delay_s는 0 이상이어야 한다")
        # 입력 매핑을 고치지 않고, 이후 바깥에서 바뀌어도 영향받지 않도록 복사해 보관한다.
        self._scenarios: dict[str, FakeScenario] = {
            meal_order_id: FakeScenario(kind) for meal_order_id, kind in (scenarios or {}).items()
        }
        self._delay_s = delay_s

    async def estimate(self, request: EstimationRequest) -> EstimationResult:
        """요청의 `meal_order_id`에 지정된 시나리오대로 결과를 만든다."""
        if self._delay_s > 0:
            await sleep(self._delay_s)

        scenario = self._scenarios.get(request.meal_order_id, FakeScenario.SUCCESS)
        if scenario is FakeScenario.ERROR:
            raise EstimationError(f"모의 외부 호출 실패: {request.meal_order_id}")

        image_determinable = scenario is not FakeScenario.IMAGE_NOT_DETERMINABLE
        return EstimationResult(
            meal_order_id=request.meal_order_id,
            slots=tuple(
                _build_slot(index, spec, scenario) for index, spec in enumerate(request.slots)
            ),
            image_status=SlotStatus.ESTIMATED
            if image_determinable
            else SlotStatus.NOT_DETERMINABLE,
            image_issues=() if image_determinable else (QualityIssue.BLUR,),
            estimate_basis=f"vlm:{self.name}",
            model_id=FAKE_MODEL_ID,
            latency_ms=round(self._delay_s * MS_PER_SECOND),
            raw_response=str(scenario),
        )


def _build_slot(index: int, spec: SlotSpec, scenario: FakeScenario) -> SlotEstimate:
    """시나리오에 맞춰 칸 하나의 추정 결과를 만든다."""
    if scenario is FakeScenario.IMAGE_NOT_DETERMINABLE or (
        scenario is FakeScenario.SLOT_NOT_DETERMINABLE and index == 0
    ):
        # 칸 단위 판단 불가만 칸에 원인(angle)을 남긴다. 사진 단위 원인은 image_issues에 있다.
        issues = (QualityIssue.ANGLE,) if scenario is FakeScenario.SLOT_NOT_DETERMINABLE else ()
        return SlotEstimate(
            slot_id=spec.slot_id,
            intake_fraction_est=None,
            status=SlotStatus.NOT_DETERMINABLE,
            quality_issues=issues,
        )
    return SlotEstimate(
        slot_id=spec.slot_id,
        intake_fraction_est=DEFAULT_FRACTIONS[index % len(DEFAULT_FRACTIONS)],
        status=SlotStatus.ESTIMATED,
    )
