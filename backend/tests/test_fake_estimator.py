"""`FakeEstimator`의 계약 테스트와 Fake 전용 동작 테스트."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from app.intake import fake as fake_module
from app.intake.fake import FakeEstimator, FakeScenario
from app.intake.types import (
    EstimationError,
    EstimationRequest,
    QualityIssue,
    SlotSpec,
    SlotStatus,
)
from tests.contracts.intake import IntakeEstimatorContract, build_estimation_request

# 구현 상수를 가져오지 않고 기대값을 따로 고정한다 (구현을 자기 자신과 비교하지 않기 위해).
DEFAULT_FRACTIONS = (1.0, 0.8, 0.5, 0.3, 0.0, 0.6)


class TestFakeEstimatorContract(IntakeEstimatorContract):
    # 시나리오마다 계약을 실행해 판단 불가 경로도 계약 테스트가 검증하게 한다.
    @pytest.fixture(params=["success", "slot_not_determinable", "image_not_determinable"])
    def estimator(
        self, request: pytest.FixtureRequest, estimation_request: EstimationRequest
    ) -> FakeEstimator:
        return FakeEstimator(scenarios={estimation_request.meal_order_id: request.param})


@pytest.fixture
def request_6(tmp_path: Path) -> EstimationRequest:
    return build_estimation_request(tmp_path, "NS01_2026-11-23_lunch")


@pytest.fixture
def request_7(request_6: EstimationRequest) -> EstimationRequest:
    extra = SlotSpec(slot_id="slot_7", menu_name="요구르트", served_g=80.0, position="식판 밖")
    return replace(request_6, slots=(*request_6.slots, extra))


async def test_default_success_repeats_fraction_cycle_by_slot_order(
    request_7: EstimationRequest,
) -> None:
    result = await FakeEstimator().estimate(request_7)

    fractions = tuple(slot.intake_fraction_est for slot in result.slots)
    assert fractions == pytest.approx((*DEFAULT_FRACTIONS, 1.0))
    assert tuple(slot.slot_id for slot in result.slots) == tuple(
        spec.slot_id for spec in request_7.slots
    )
    assert all(slot.status is SlotStatus.ESTIMATED for slot in result.slots)
    assert result.estimate_basis == "vlm:fake"
    assert result.image_status is SlotStatus.ESTIMATED
    assert result.image_issues == ()


async def test_slot_not_determinable_marks_only_first_slot(
    request_6: EstimationRequest,
) -> None:
    estimator = FakeEstimator(
        scenarios={request_6.meal_order_id: FakeScenario.SLOT_NOT_DETERMINABLE}
    )

    result = await estimator.estimate(request_6)

    first, *rest = result.slots
    assert first.slot_id == request_6.slots[0].slot_id
    assert first.status is SlotStatus.NOT_DETERMINABLE
    assert first.intake_fraction_est is None
    assert first.quality_issues == (QualityIssue.ANGLE,)
    assert all(slot.status is SlotStatus.ESTIMATED for slot in rest)
    assert tuple(slot.intake_fraction_est for slot in rest) == pytest.approx(DEFAULT_FRACTIONS[1:])
    assert result.image_status is SlotStatus.ESTIMATED


async def test_image_not_determinable_marks_image_and_every_slot(
    request_6: EstimationRequest,
) -> None:
    estimator = FakeEstimator(scenarios={request_6.meal_order_id: "image_not_determinable"})

    result = await estimator.estimate(request_6)

    assert result.image_status is SlotStatus.NOT_DETERMINABLE
    assert result.image_issues == (QualityIssue.BLUR,)
    assert tuple(slot.slot_id for slot in result.slots) == tuple(
        spec.slot_id for spec in request_6.slots
    )
    assert all(slot.status is SlotStatus.NOT_DETERMINABLE for slot in result.slots)
    assert all(slot.intake_fraction_est is None for slot in result.slots)


async def test_error_scenario_raises_estimation_error(request_6: EstimationRequest) -> None:
    estimator = FakeEstimator(scenarios={request_6.meal_order_id: FakeScenario.ERROR})

    with pytest.raises(EstimationError):
        await estimator.estimate(request_6)


async def test_meal_order_not_in_scenarios_succeeds(request_6: EstimationRequest) -> None:
    estimator = FakeEstimator(scenarios={"other_meal_order": FakeScenario.ERROR})

    result = await estimator.estimate(request_6)

    assert result.image_status is SlotStatus.ESTIMATED
    assert all(slot.status is SlotStatus.ESTIMATED for slot in result.slots)


@pytest.mark.parametrize("scenario", ["success", "slot_not_determinable", "image_not_determinable"])
async def test_same_request_gives_equal_result(request_6: EstimationRequest, scenario: str) -> None:
    estimator = FakeEstimator(scenarios={request_6.meal_order_id: scenario})

    first = await estimator.estimate(request_6)
    second = await estimator.estimate(request_6)

    assert first == second


async def test_constructor_copies_scenarios(request_6: EstimationRequest) -> None:
    scenarios = {request_6.meal_order_id: "error"}
    estimator = FakeEstimator(scenarios=scenarios)
    scenarios[request_6.meal_order_id] = "success"

    with pytest.raises(EstimationError):
        await estimator.estimate(request_6)


@pytest.fixture
def recorded_sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """실제로 기다리지 않고 `sleep` 호출 인자만 기록한다."""
    calls: list[float] = []

    async def record_sleep(delay_s: float) -> None:
        calls.append(delay_s)

    monkeypatch.setattr(fake_module, "sleep", record_sleep)
    return calls


@pytest.mark.parametrize(
    ("delay_s", "expected_calls", "expected_latency_ms"),
    [(1.5, [1.5], 1500), (0.0, [], 0)],
)
async def test_delay_sleeps_only_when_positive(
    request_6: EstimationRequest,
    recorded_sleeps: list[float],
    delay_s: float,
    expected_calls: list[float],
    expected_latency_ms: int,
) -> None:
    result = await FakeEstimator(delay_s=delay_s).estimate(request_6)

    assert recorded_sleeps == expected_calls
    assert result.latency_ms == expected_latency_ms


def test_name_is_fake() -> None:
    assert FakeEstimator.name == "fake"


def test_negative_delay_raises_value_error() -> None:
    with pytest.raises(ValueError):
        FakeEstimator(delay_s=-0.1)


def test_unknown_scenario_raises_value_error() -> None:
    with pytest.raises(ValueError):
        FakeEstimator(scenarios={"order_x": "partial"})
