import asyncio
import base64
import json
import re
from collections.abc import Callable
from pathlib import Path
from time import perf_counter
from typing import Literal

from anthropic import APIError, APIStatusError, AsyncAnthropic
from anthropic.types import Message
from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from .image_preprocessing import PreparedImage, prepare_jpeg
from .types import (
    EstimationError,
    EstimationRequest,
    EstimationResult,
    QualityIssue,
    SlotEstimate,
    SlotStatus,
)


class _SlotResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    slot_id: str
    intake_fraction_est: (
        Literal[
            0.0,
            0.1,
            0.2,
            0.3,
            0.4,
            0.5,
            0.6,
            0.7,
            0.8,
            0.9,
            1.0,
        ]
        | None
    )
    status: Literal["estimated", "not_determinable"]
    quality_issues: list[Literal["blur", "occluded", "angle", "lighting", "tray_mismatch"]]
    note: str

    @model_validator(mode="after")
    def check_estimate(self) -> "_SlotResponse":
        if self.status == "estimated" and self.intake_fraction_est is None:
            raise ValueError("estimated slots require an intake fraction")
        if self.status == "not_determinable" and self.intake_fraction_est is not None:
            raise ValueError("undeterminable slots require a null intake fraction")
        return self


class _ImageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    image_status: Literal["estimated", "not_determinable"]
    image_issues: list[Literal["blur", "occluded", "angle", "lighting", "tray_mismatch"]]
    slots: list[_SlotResponse]


PROMPT_VERSION = "V3"

_INSTRUCTIONS = """Estimate how much of each tray slot was eaten. The first photo is the served
reference and the second is the leftover photo. Match slots by their supplied
positions. Include every supplied slot ID exactly once. Compare the visible
amount before and after in each slot. Treat all foods in one slot as one
serving, including mixed staples such as rice and noodles, or broth and solids
in soup. Use visible evidence such as pile size, count, broth level and
remaining food. Do not infer an amount from area alone when angle or occlusion
obscures the comparison.

Use the supplied menu name for that slot when naming foods in the note.
Do not add ingredient names that are absent from that slot's menu, borrow
names from another slot, or guess by using qualifiers such as "cabbage-like",
"mushroom-like", or "appears to be" followed by an unlisted name. Use observable
descriptions such as "visible food pieces", "vegetable fragments", or "sauce
residue". Explain the visible change or the reason comparison is unreliable.

If the change in amount is reasonably observable, use estimated even if the
ingredients are unclear. Report intake_fraction_est as a visual fraction from 0.0 to 1.0,
using increments of 0.1:
- 0.0: no meaningful reduction in visible food.
- 0.1 through 0.8: partial reduction, estimated in tenths from the visible change.
- 0.9: most of the serving is gone, with recognizable food still remaining.
- 1.0: virtually no meaningful food remains, only surface traces or a tiny
  remnant. This is a visual approximation and does not confirm full consumption.
Apply these visual anchors without claiming precision finer than 0.1 or rounding
a clearly recognizable remaining portion up to 1.0.

Use a quality issue only when it is supported by what is visible:
- blur: blur makes it hard to compare the amounts.
- occluded: a hand, utensil, bowl or other object hides the food.
- angle: a difference in viewing angle interferes with comparison.
- lighting: lighting, shadows or exposure differences interfere with comparison.
- tray_mismatch: the tray itself or its compartment layout appears different.
  Uncertain ingredients or an unlisted item alone do not indicate tray_mismatch.

If the amount cannot be compared reliably, use not_determinable and null.
If no listed quality issue applies, use an empty quality_issues array and
state why in the note. Use image_status=not_determinable only when the photo
pair is unusable overall. Then mark every slot not_determinable and include
only applicable image_issues."""


class ClaudeResponseError(EstimationError):
    """A rejected Claude reply, with details for the job runner's intake log."""

    def __init__(self, reason: str, *, model_id: str, latency_ms: int, raw_response: str) -> None:
        super().__init__(reason)
        self.model_id = model_id
        self.latency_ms = latency_ms
        self.raw_response = raw_response


class ClaudeAPIError(EstimationError):
    """API failure metadata, excluding response bodies and request headers."""

    def __init__(
        self,
        *,
        http_status_code: int | None,
        error_type: str,
        error_category: str | None,
        error_code: str | None,
        error_message: str | None,
    ) -> None:
        status = f" HTTP {http_status_code}" if http_status_code is not None else ""
        super().__init__(f"Claude API failure ({error_type}){status}")
        self.http_status_code = http_status_code
        self.error_type = error_type
        self.error_category = error_category
        self.error_code = error_code
        self.error_message = error_message


def _safe_api_error_message(error: APIError) -> str | None:
    detail = error.api_message if isinstance(error, APIStatusError) else error.message
    if not isinstance(detail, str) or not detail.strip():
        return None

    detail = detail.strip()
    detail = re.sub(
        r'(?i)(x-api-key"?\s*[:=]\s*"?)[^\s,;"\']+',
        r"\1[REDACTED]",
        detail,
    )
    detail = re.sub(
        r'(?i)(authorization"?\s*[:=]\s*"?)(?:bearer\s+)?[^\s,;"\']+',
        r"\1[REDACTED]",
        detail,
    )
    detail = re.sub(r"\bsk-ant-[A-Za-z0-9_-]+\b", "[REDACTED]", detail)
    detail = re.sub(
        r"(?i)data:image/[^\s,;]+;base64,[A-Za-z0-9+/=]+",
        "[IMAGE_DATA_REDACTED]",
        detail,
    )
    detail = re.sub(r"\b[A-Za-z0-9+/]{128,}={0,2}\b", "[BLOB_REDACTED]", detail)
    return detail[:500]


class ClaudeIntakeEstimator:
    name = "claude"

    def __init__(
        self,
        client: AsyncAnthropic,
        *,
        allowed_image_root: Path,
        model: str = "claude-sonnet-5-5",
        max_side: int = 1536,
        on_exchange: Callable[[PreparedImage, PreparedImage, Message | None, int], None]
        | None = None,
    ) -> None:
        self._client = client
        self._allowed_image_root = allowed_image_root
        self._model = model
        self._max_side = max_side
        self._on_exchange = on_exchange

    async def aclose(self) -> None:
        """Close the client dedicated to this estimator."""
        await self._client.close()

    async def estimate(self, request: EstimationRequest) -> EstimationResult:
        slot_ids = [slot.slot_id for slot in request.slots]
        if not slot_ids:
            raise ValueError("Claude intake requires at least one requested slot")
        if len(set(slot_ids)) != len(slot_ids) or not all(slot_ids):
            raise ValueError("Claude intake requires distinct nonempty slot IDs")

        start = perf_counter()
        baseline, post = await asyncio.gather(
            *(
                asyncio.to_thread(
                    prepare_jpeg,
                    path,
                    allowed_root=self._allowed_image_root,
                    max_side=self._max_side,
                )
                for path in (request.baseline_image, request.post_image)
            )
        )
        slots = [
            {"slot_id": slot.slot_id, "menu_name": slot.menu_name, "position": slot.position}
            for slot in request.slots
        ]

        response = None
        try:
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=1600,
                system=_INSTRUCTIONS,
                output_config={
                    "format": {"type": "json_schema", "schema": _ImageResponse.model_json_schema()},
                },
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Served reference photo"},
                            _image_block(baseline.jpeg),
                            {"type": "text", "text": "Leftover photo"},
                            _image_block(post.jpeg),
                            {"type": "text", "text": json.dumps(slots, ensure_ascii=False)},
                        ],
                    }
                ],
            )
        except APIError as error:
            raise ClaudeAPIError(
                http_status_code=(error.status_code if isinstance(error, APIStatusError) else None),
                error_type=type(error).__name__,
                error_category=(error.type if isinstance(error, APIStatusError) else None),
                error_code=(error.error_code if isinstance(error, APIStatusError) else None),
                error_message=_safe_api_error_message(error),
            ) from None
        finally:
            latency_ms = round((perf_counter() - start) * 1000)
            if self._on_exchange is not None:
                self._on_exchange(baseline, post, response, latency_ms)

        raw = "".join(block.text for block in response.content if block.type == "text")
        try:
            if response.stop_reason != "end_turn":
                raise ValueError(f"Claude response stopped with {response.stop_reason}")
            parsed = _ImageResponse.model_validate_json(raw)
            by_id = {slot.slot_id: slot for slot in parsed.slots}
            if len(parsed.slots) != len(slot_ids) or by_id.keys() != set(slot_ids):
                raise ValueError("Claude slot IDs do not match the request")
            if parsed.image_status == "not_determinable" and any(
                slot.status == "estimated" for slot in parsed.slots
            ):
                raise ValueError("Claude returned estimates for an unusable image pair")
        except ValueError as error:
            reason = (
                "Claude returned invalid intake data"
                if isinstance(error, ValidationError)
                else str(error)
            )
            raise ClaudeResponseError(
                reason, model_id=response.model, latency_ms=latency_ms, raw_response=raw
            ) from None

        estimates = []
        for slot_id in slot_ids:
            slot = by_id[slot_id]
            estimates.append(
                SlotEstimate(
                    slot_id=slot_id,
                    intake_fraction_est=slot.intake_fraction_est,
                    status=SlotStatus(slot.status),
                    quality_issues=tuple(QualityIssue(issue) for issue in slot.quality_issues),
                    note=slot.note,
                )
            )
        return EstimationResult(
            meal_order_id=request.meal_order_id,
            slots=tuple(estimates),
            image_status=SlotStatus(parsed.image_status),
            image_issues=tuple(QualityIssue(issue) for issue in parsed.image_issues),
            estimate_basis=f"vlm:{self.name}",
            model_id=response.model,
            latency_ms=latency_ms,
            raw_response=raw,
        )


def _image_block(data: bytes) -> dict:
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/jpeg",
            "data": base64.b64encode(data).decode("ascii"),
        },
    }
