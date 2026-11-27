"""`IntakeEstimator` 계약 테스트 기반 클래스.

구현별 하위 클래스(`Test*`)는 `estimator` 픽스처만 정의한다.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

import pytest

from app.intake.types import (
    EstimationRequest,
    EstimationResult,
    IntakeEstimator,
    QualityIssue,
    SlotEstimate,
    SlotSpec,
    SlotStatus,
)

IMAGE_SIZE_PX = 8
FRACTION_STEP_TOLERANCE = 1e-9

_SLOT_LAYOUT: tuple[SlotSpec, ...] = (
    SlotSpec(slot_id="slot_1", menu_name="쌀밥", served_g=210.0, position="아랫줄 왼쪽"),
    SlotSpec(slot_id="slot_2", menu_name="미역국", served_g=250.0, position="아랫줄 오른쪽"),
    SlotSpec(slot_id="slot_3", menu_name="두부조림", served_g=60.0, position="윗줄 1 (왼쪽 끝)"),
    SlotSpec(slot_id="slot_4", menu_name="시금치나물", served_g=40.0, position="윗줄 2"),
    SlotSpec(slot_id="slot_5", menu_name="배추김치", served_g=40.0, position="윗줄 3"),
    SlotSpec(slot_id="slot_6", menu_name="생선구이", served_g=70.0, position="윗줄 4 (오른쪽 끝)"),
)


def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    """PNG 청크 하나(길이·종류·데이터·CRC)를 만든다."""
    crc = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", crc)


def solid_png_bytes(rgb: tuple[int, int, int], size_px: int = IMAGE_SIZE_PX) -> bytes:
    """표준 라이브러리만으로 단색 RGB PNG 바이트를 만든다."""
    header = struct.pack(">IIBBBBB", size_px, size_px, 8, 2, 0, 0, 0)
    row = b"\x00" + bytes(rgb) * size_px  # 필터 0 + 픽셀
    pixels = zlib.compress(row * size_px)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", header)
        + _png_chunk(b"IDAT", pixels)
        + _png_chunk(b"IEND", b"")
    )


def build_estimation_request(tmp_path: Path, meal_order_id: str) -> EstimationRequest:
    """`tmp_path`에 합성 식전·식후 사진 2장을 쓰고 6칸 배치 요청을 만든다."""
    baseline_image = tmp_path / "baseline.png"
    post_image = tmp_path / "post.png"
    baseline_image.write_bytes(solid_png_bytes((230, 200, 120)))
    post_image.write_bytes(solid_png_bytes((90, 140, 200)))
    return EstimationRequest(
        meal_order_id=meal_order_id,
        baseline_image=baseline_image,
        post_image=post_image,
        slots=_SLOT_LAYOUT,
    )


class IntakeEstimatorContract:
    """모든 `IntakeEstimator` 구현이 지켜야 하는 불변 조건."""

    @pytest.fixture
    def estimator(self) -> IntakeEstimator:
        """하위 클래스가 검증할 구현을 돌려준다."""
        raise NotImplementedError("하위 클래스가 estimator 픽스처를 정의해야 한다")

    @pytest.fixture
    def estimation_request(self, tmp_path: Path) -> EstimationRequest:
        """합성 이미지 2장과 6칸 배치로 만든 기본 요청."""
        return build_estimation_request(tmp_path, "NS07_2026-11-23_lunch")

    async def test_every_requested_slot_appears_exactly_once(
        self, estimator: IntakeEstimator, estimation_request: EstimationRequest
    ) -> None:
        result = await estimator.estimate(estimation_request)
        requested_ids = sorted(slot.slot_id for slot in estimation_request.slots)
        returned_ids = sorted(slot.slot_id for slot in result.slots)
        assert returned_ids == requested_ids

    async def test_estimated_fraction_is_within_range_and_in_tenths(
        self, estimator: IntakeEstimator, estimation_request: EstimationRequest
    ) -> None:
        result = await estimator.estimate(estimation_request)
        for slot in result.slots:
            if slot.status == SlotStatus.NOT_DETERMINABLE:
                continue
            fraction = slot.intake_fraction_est
            assert fraction is not None
            assert 0.0 <= fraction <= 1.0
            assert abs(round(fraction * 10) - fraction * 10) <= FRACTION_STEP_TOLERANCE

    async def test_not_determinable_slot_has_no_fraction(
        self, estimator: IntakeEstimator, estimation_request: EstimationRequest
    ) -> None:
        result = await estimator.estimate(estimation_request)
        for slot in result.slots:
            if slot.status == SlotStatus.NOT_DETERMINABLE:
                assert slot.intake_fraction_est is None

    async def test_estimate_basis_starts_with_vlm_prefix(
        self, estimator: IntakeEstimator, estimation_request: EstimationRequest
    ) -> None:
        result = await estimator.estimate(estimation_request)
        assert result.estimate_basis.startswith("vlm:")

    async def test_meal_order_id_matches_request(
        self, estimator: IntakeEstimator, estimation_request: EstimationRequest
    ) -> None:
        result = await estimator.estimate(estimation_request)
        assert result.meal_order_id == estimation_request.meal_order_id

    async def test_result_type_and_slots_tuple(
        self, estimator: IntakeEstimator, estimation_request: EstimationRequest
    ) -> None:
        result = await estimator.estimate(estimation_request)
        assert isinstance(result, EstimationResult)
        assert isinstance(result.slots, tuple)
        assert all(isinstance(slot, SlotEstimate) for slot in result.slots)
        assert all(isinstance(slot.status, SlotStatus) for slot in result.slots)
        assert isinstance(result.image_status, SlotStatus)
        # 모델 응답 문자열을 그대로 넣지 않고 열거형으로 바꿔야 한다.
        assert isinstance(result.image_issues, tuple)
        assert all(isinstance(issue, QualityIssue) for issue in result.image_issues)
        for slot in result.slots:
            assert isinstance(slot.quality_issues, tuple)
            assert all(isinstance(issue, QualityIssue) for issue in slot.quality_issues)
