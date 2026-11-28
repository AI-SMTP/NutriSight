"""Evaluate the final Claude intake adapter using a local JSON request."""

import argparse
import asyncio
import json
from dataclasses import asdict
from pathlib import Path

from anthropic import AsyncAnthropic

from app.config import Settings
from app.intake.claude_estimator import ClaudeIntakeEstimator
from app.intake.types import EstimationError, EstimationRequest, SlotSpec


async def run(request_path: Path, image_root: Path) -> None:
    settings = Settings()
    key = settings.anthropic_api_key

    if key is None or not key.get_secret_value().strip():
        raise ValueError("Set ANTHROPIC_API_KEY before running evaluation")

    request_path = request_path.resolve()
    data = json.loads(request_path.read_text(encoding="utf-8-sig"))

    request = EstimationRequest(
        meal_order_id=data["meal_order_id"],
        baseline_image=request_path.parent / data["baseline_image"],
        post_image=request_path.parent / data["post_image"],
        slots=tuple(SlotSpec(**slot) for slot in data["slots"]),
    )

    async with AsyncAnthropic(
        api_key=key.get_secret_value().strip(),
        base_url="https://api.anthropic.com",
        timeout=60.0,
        max_retries=0,
    ) as client:
        estimator = ClaudeIntakeEstimator(
            client=client,
            allowed_image_root=image_root.resolve(),
        )
        result = await estimator.estimate(request)

    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", type=Path)
    parser.add_argument("--image-root", type=Path, required=True)
    args = parser.parse_args()

    try:
        asyncio.run(run(args.request, args.image_root))
    except (OSError, ValueError, KeyError, TypeError, EstimationError) as error:
        parser.exit(1, f"Intake evaluation failed: {error}\\n")


if __name__ == "__main__":
    main()
