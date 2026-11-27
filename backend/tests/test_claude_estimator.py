import base64
import builtins
import json
from dataclasses import replace
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from anthropic import APIConnectionError, APITimeoutError
from anthropic.types import Message
from httpx2 import Request
from PIL import Image

from app.config import REPOSITORY_ROOT, ConfigError, Settings
from app.intake import image_preprocessing
from app.intake.claude_estimator import (
    _INSTRUCTIONS,
    ClaudeIntakeEstimator,
    ClaudeResponseError,
)
from app.intake.fake import FakeEstimator
from app.intake.types import (
    EstimationError,
    EstimationRequest,
    EstimationResult,
    QualityIssue,
    SlotSpec,
    SlotStatus,
)
from app.main import create_app
from tests.contracts.intake import IntakeEstimatorContract


@pytest.fixture
def request_data(tmp_path):
    before, after = tmp_path / "before.jpg", tmp_path / "after.jpg"
    for path in (before, after):
        Image.new("RGB", (1600, 1200)).save(path)
    slots = tuple(SlotSpec(f"slot_{n}", f"Dish {n}", 999.0, str(n)) for n in range(1, 7))
    return EstimationRequest("local-order", before, after, slots)


@pytest.fixture
def payload(request_data):
    return {
        "image_status": "estimated",
        "image_issues": [],
        "slots": [
            {
                "slot_id": slot.slot_id,
                "consumed_tenths": 4,
                "status": "estimated",
                "quality_issues": [],
                "note": "Some food remains.",
            }
            for slot in reversed(request_data.slots)
        ],
    }


def reply(raw, stop_reason="end_turn"):
    return Message.model_validate(
        {
            "id": "msg_mock",
            "type": "message",
            "role": "assistant",
            "model": "mock-sonnet",
            "content": [{"type": "text", "text": raw}],
            "stop_reason": stop_reason,
            "usage": {"input_tokens": 100, "output_tokens": 40, "cache_read_input_tokens": 25},
        }
    )


@pytest.fixture
def create():
    return AsyncMock()


@pytest.fixture
def estimator(create, request_data):
    return ClaudeIntakeEstimator(
        SimpleNamespace(messages=SimpleNamespace(create=create)),
        allowed_image_root=request_data.baseline_image.parent,
    )


@pytest.mark.asyncio
async def test_common_result(estimator, create, request_data, payload):
    create.return_value = reply(json.dumps(payload))
    result = await estimator.estimate(request_data)
    assert isinstance(result, EstimationResult)
    assert result.estimate_basis == "vlm:claude"
    assert result.meal_order_id == request_data.meal_order_id
    assert [slot.slot_id for slot in result.slots] == [slot.slot_id for slot in request_data.slots]
    assert [slot.intake_fraction_est for slot in result.slots] == [0.4] * 6


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "problem",
    [
        "missing",
        "duplicate",
        "range",
        "estimated_null",
        "undeterminable_number",
        "invalid_json",
        "unusable_with_estimates",
        "truncated",
    ],
)
async def test_invalid_response(estimator, create, request_data, payload, problem):
    slot = payload["slots"][0]
    stop_reason = "end_turn"
    if problem == "missing":
        payload["slots"].pop()
    elif problem == "duplicate":
        slot["slot_id"] = payload["slots"][1]["slot_id"]
    elif problem == "range":
        slot["consumed_tenths"] = 11
    elif problem == "estimated_null":
        slot["consumed_tenths"] = None
    elif problem == "undeterminable_number":
        slot["status"] = "not_determinable"
    elif problem == "unusable_with_estimates":
        payload["image_status"] = "not_determinable"
    elif problem == "truncated":
        stop_reason = "max_tokens"
    raw = "{" if problem == "invalid_json" else json.dumps(payload)
    create.return_value = reply(raw, stop_reason)
    with pytest.raises(ClaudeResponseError) as captured:
        await estimator.estimate(request_data)
    assert isinstance(captured.value, EstimationError)
    assert captured.value.raw_response == raw
    assert captured.value.model_id == "mock-sonnet"


@pytest.mark.asyncio
async def test_unusable_images(estimator, create, request_data, payload):
    payload.update(image_status="not_determinable", image_issues=["blur"])
    for slot in payload["slots"]:
        slot.update(status="not_determinable", consumed_tenths=None, quality_issues=["blur"])
    create.return_value = reply(json.dumps(payload))
    result = await estimator.estimate(request_data)
    assert result.image_status is SlotStatus.NOT_DETERMINABLE
    assert result.image_issues == (QualityIssue.BLUR,)
    assert len(result.slots) == 6
    assert all(slot.intake_fraction_est is None for slot in result.slots)


@pytest.mark.asyncio
@pytest.mark.parametrize("error_type", [APIConnectionError, APITimeoutError])
async def test_transport_failure(estimator, create, request_data, error_type):
    create.side_effect = error_type(request=Request("POST", "https://example.test"))
    with pytest.raises(EstimationError, match=error_type.__name__):
        await estimator.estimate(request_data)
    create.assert_awaited_once()


@pytest.mark.asyncio
async def test_bad_image_skips_api(estimator, create, request_data, tmp_path):
    broken = tmp_path / "broken.jpg"
    broken.write_bytes(b"not an image")
    with pytest.raises(ValueError, match="Could not decode"):
        await estimator.estimate(replace(request_data, post_image=broken))
    create.assert_not_awaited()


@pytest.mark.asyncio
async def test_v3_prompt_and_undeterminable_without_quality_code(
    estimator,
    create,
    request_data,
    payload,
):
    slot = payload["slots"][0]
    slot.update(
        status="not_determinable",
        consumed_tenths=None,
        quality_issues=[],
        note="The amount belonging to this slot cannot be compared reliably.",
    )
    create.return_value = reply(json.dumps(payload))
    result = await estimator.estimate(request_data)

    system = create.call_args.kwargs["system"]
    assert system == _INSTRUCTIONS
    for marker in (
        "compartment layout appears different",
        "Uncertain ingredients or an unlisted item alone do not indicate tray_mismatch.",
        "use an empty quality_issues array",
        '"cabbage-like"',
        "does not confirm full consumption",
    ):
        assert marker in system
    last = result.slots[-1]
    assert last.status is SlotStatus.NOT_DETERMINABLE
    assert last.intake_fraction_est is None
    assert last.quality_issues == ()
    assert last.note == slot["note"]


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["baseline_image", "post_image"])
@pytest.mark.parametrize("case", ["relative", "traversal", "absolute", "symlink"])
async def test_image_path_escape(request_data, create, tmp_path, monkeypatch, field, case):
    allowed = tmp_path / "photos"
    allowed.mkdir()
    inside = allowed / "tray.jpg"
    inside.write_bytes(request_data.baseline_image.read_bytes())
    outside = request_data.post_image
    monkeypatch.chdir(tmp_path)
    if case == "relative":
        path = outside.relative_to(tmp_path)
    elif case == "traversal":
        path = allowed / ".." / outside.name
    elif case == "absolute":
        path = outside
    else:
        path = allowed / "escape.jpg"
        try:
            path.symlink_to(outside)
        except (OSError, NotImplementedError) as error:
            pytest.skip(f"Symlink creation unavailable: {error}")

    estimator = ClaudeIntakeEstimator(
        SimpleNamespace(messages=SimpleNamespace(create=create)),
        allowed_image_root=allowed,
    )
    request = replace(request_data, baseline_image=inside, post_image=inside)
    with pytest.raises(ValueError, match="allowed image directory"):
        await estimator.estimate(replace(request, **{field: path}))
    create.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("missing", "could not be resolved"),
        ("directory", "regular file"),
        ("unsupported", "valid JPEG or PNG"),
        ("truncated_jpeg", "valid JPEG or PNG"),
        ("bad_png_crc", "valid JPEG or PNG"),
        ("bytes", "file size limit"),
        ("pixels", "pixel limit"),
        ("side", "dimension"),
        ("pillow_bomb", "Pillow"),
    ],
)
async def test_invalid_image_content(
    estimator,
    create,
    request_data,
    tmp_path,
    monkeypatch,
    case,
    message,
):
    path = tmp_path / "candidate.img"
    if case == "directory":
        path.mkdir()
    elif case == "unsupported":
        Image.new("RGB", (24, 16)).save(path, format="BMP")
    elif case == "truncated_jpeg":
        path.write_bytes(request_data.post_image.read_bytes()[:-64])
    elif case == "bad_png_crc":
        buffer = BytesIO()
        Image.new("RGB", (24, 16)).save(buffer, format="PNG")
        png = bytearray(buffer.getvalue())
        idat = png.index(b"IDAT")
        length = int.from_bytes(png[idat - 4 : idat], "big")
        png[idat + 4 + length] ^= 1
        path.write_bytes(png)
    elif case != "missing":
        path.write_bytes(request_data.post_image.read_bytes())
        if case == "bytes":
            monkeypatch.setattr(image_preprocessing, "MAX_IMAGE_BYTES", path.stat().st_size - 1)
        elif case == "pixels":
            monkeypatch.setattr(image_preprocessing, "MAX_IMAGE_PIXELS", 1_919_999)
        elif case == "side":
            monkeypatch.setattr(image_preprocessing, "MAX_IMAGE_SIDE", 1599)
        else:
            monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 100_000)

    with pytest.raises(ValueError, match=message):
        await estimator.estimate(replace(request_data, post_image=path))
    create.assert_not_awaited()


@pytest.mark.asyncio
async def test_valid_jpeg_and_png_use_existing_preprocessing(
    estimator,
    create,
    request_data,
    payload,
    tmp_path,
):
    png = tmp_path / "tray.png"
    Image.new("RGBA", (24, 16), (255, 0, 0, 0)).save(png)
    create.return_value = reply(json.dumps(payload))
    await estimator.estimate(replace(request_data, post_image=png))
    blocks = create.call_args.kwargs["messages"][0]["content"]
    for index, size in ((1, (1536, 1152)), (3, (24, 16))):
        with Image.open(BytesIO(base64.b64decode(blocks[index]["source"]["data"]))) as image:
            assert image.format == "JPEG" and image.mode == "RGB"
            assert image.size == size
            assert not image.getexif()
            if index == 3:
                assert image.getpixel((0, 0)) == (255, 255, 255)


class TestClaudeIntakeContract(IntakeEstimatorContract):
    @pytest.fixture(params=["success", "slot_not_determinable", "image_not_determinable"])
    def estimator(self, request, estimation_request, tmp_path):
        unusable = request.param == "image_not_determinable"
        slots = []
        for index, slot in enumerate(estimation_request.slots):
            unknown = unusable or (index == 0 and request.param == "slot_not_determinable")
            slots.append(
                {
                    "slot_id": slot.slot_id,
                    "status": "not_determinable" if unknown else "estimated",
                    "consumed_tenths": None if unknown else 4,
                    "quality_issues": ["angle"] if unknown and not unusable else [],
                    "note": "Mock comparison",
                }
            )
        raw = json.dumps(
            {
                "image_status": "not_determinable" if unusable else "estimated",
                "image_issues": ["blur"] if unusable else [],
                "slots": slots,
            }
        )
        client = SimpleNamespace(
            messages=SimpleNamespace(create=AsyncMock(return_value=reply(raw))),
        )
        return ClaudeIntakeEstimator(client, allowed_image_root=tmp_path)


def test_fake_does_not_import_claude(monkeypatch):
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        assert name not in {"anthropic", "app.intake.claude_estimator"}
        return original_import(name, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(builtins, "__import__", guarded_import)
        app = create_app(Settings(_env_file=None, intake_adapter="fake", anthropic_api_key=None))
    assert isinstance(app.state.intake_estimator, FakeEstimator)


@pytest.mark.parametrize("key", [None, "", "   "])
def test_claude_requires_api_key(key):
    settings = Settings(_env_file=None, intake_adapter="claude", anthropic_api_key=key)
    with pytest.raises(ConfigError, match="ANTHROPIC_API_KEY"):
        create_app(settings)


@pytest.mark.asyncio
async def test_claude_wiring_uses_configured_root(monkeypatch, request_data, payload):
    import anthropic

    client = SimpleNamespace(
        messages=SimpleNamespace(create=AsyncMock(return_value=reply(json.dumps(payload)))),
        close=AsyncMock(),
    )
    options = {}

    def create_client(**kwargs):
        options.update(kwargs)
        return client

    monkeypatch.setattr(anthropic, "AsyncAnthropic", create_client)
    settings = Settings(
        _env_file=None,
        intake_adapter="claude",
        anthropic_api_key="mock-key",
        intake_photo_root=request_data.baseline_image.parent,
    )
    app = create_app(settings)
    estimator = app.state.intake_estimator
    assert isinstance(estimator, ClaudeIntakeEstimator)
    assert options == {
        "api_key": "mock-key",
        "base_url": "https://api.anthropic.com",
        "timeout": 60.0,
        "max_retries": 0,
    }
    result = await estimator.estimate(request_data)
    assert result.estimate_basis == "vlm:claude"
    await estimator.aclose()
    client.close.assert_awaited_once()


def test_photo_root_default_is_independent_of_cwd(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("INTAKE_PHOTO_ROOT", raising=False)
    assert Settings(_env_file=None).intake_photo_root == REPOSITORY_ROOT / "var" / "photos"
