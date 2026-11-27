"""섭취 추정 인터페이스 계약 (`docs/system-architecture.md` 5절).

분석 작업 실행기는 이 인터페이스만 안다. 모델마다 어댑터를 하나씩 만든다.
도메인 실패(판단 불가)는 `status` 값으로, 외부 실패(네트워크·시간 초과)는
`EstimationError`로 나눈다.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class SlotSpec:
    """식판 한 칸의 배식 정보."""

    slot_id: str  # 칸 ID (예: "slot_3"). meal_plan_slots.slot_id
    menu_name: str  # 예: "두부조림"
    served_g: float  # 표준 배식량
    position: str  # 식판 안 위치 설명. meal_plan_slots.position. 좌표를 쓰는 모델은 무시해도 된다.


@dataclass(frozen=True)
class EstimationRequest:
    """환자의 한 끼에 대한 섭취 추정 요청."""

    meal_order_id: str  # 환자의 한 끼 (예: "NS07_2026-11-23_lunch")
    baseline_image: Path  # 끼니의 기준 식전 사진
    post_image: Path  # 환자의 식후 사진
    slots: tuple[SlotSpec, ...]


class SlotStatus(StrEnum):
    """칸 또는 사진 전체의 판단 가능 여부."""

    ESTIMATED = "estimated"
    NOT_DETERMINABLE = "not_determinable"


class QualityIssue(StrEnum):
    """판단 불가의 원인이 된 사진 품질 문제."""

    BLUR = "blur"
    OCCLUDED = "occluded"  # 손·수저 등이 칸을 가림
    ANGLE = "angle"  # 기준 사진과 각도 차이가 큼
    LIGHTING = "lighting"
    TRAY_MISMATCH = "tray_mismatch"  # 기준 사진과 다른 식판·배치로 보임


@dataclass(frozen=True)
class SlotEstimate:
    """칸 하나의 섭취 추정 결과."""

    slot_id: str
    intake_fraction_est: float | None  # 0~1, 0.1 단위. 판단 불가면 None
    status: SlotStatus
    quality_issues: tuple[QualityIssue, ...] = ()
    note: str = ""  # 모델이 남긴 짧은 근거 (분석 로그·평가용)


@dataclass(frozen=True)
class EstimationResult:
    """한 끼의 섭취 추정 결과. `slots`에는 요청한 칸이 빠짐없이 한 번씩 있다."""

    meal_order_id: str
    slots: tuple[SlotEstimate, ...]
    image_status: SlotStatus  # 사진 전체 판단 가능 여부
    image_issues: tuple[QualityIssue, ...]
    estimate_basis: str  # "vlm:<어댑터 이름>"
    model_id: str  # 실제 호출한 모델 ID
    latency_ms: int
    raw_response: str  # 평가·디버깅용 원문


class EstimationError(Exception):
    """외부 호출 실패·시간 초과. 사진 처리 상태를 failed로 만든다."""


class IntakeEstimator(Protocol):
    """섭취 추정 어댑터가 따르는 인터페이스."""

    name: str

    async def estimate(self, request: EstimationRequest) -> EstimationResult: ...
