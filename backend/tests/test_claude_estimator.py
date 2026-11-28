import base64
import builtins
import json
from dataclasses import replace
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from anthropic import APIConnectionError, APITimeoutError, BadRequestError
from anthropic.types import Message
from httpx2 import Request, Response
from PIL import Image

from app.config import REPO_ROOT, ConfigError, Settings, storage_paths
from app.intake import image_preprocessing
from app.intake.claude_estimator import (
    _INSTRUCTIONS,
    ClaudeAPIError,
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
                "intake_fraction_est": 0.4,
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
    assert result.raw_response == json.dumps(payload)
    schema = create.call_args.kwargs["output_config"]["format"]["schema"]
    slot_ref = schema["properties"]["slots"]["items"]["$ref"]
    slot_schema = schema["$defs"][slot_ref.rsplit("/", 1)[-1]]
    fraction_schema = next(
        branch
        for branch in slot_schema["properties"]["intake_fraction_est"]["anyOf"]
        if branch.get("type") == "number"
    )
    assert fraction_schema["enum"] == [
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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "problem",
    [
        "missing",
        "duplicate",
        "extra",
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
    elif problem == "extra":
        payload["slots"].append(
            {
                "slot_id": "slot_extra",
                "intake_fraction_est": 0.1,
                "status": "estimated",
                "quality_issues": [],
                "note": "Unexpected slot.",
            }
        )
    elif problem == "range":
        slot["intake_fraction_est"] = 0.35
    elif problem == "estimated_null":
        slot["intake_fraction_est"] = None
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
        slot.update(status="not_determinable", intake_fraction_est=None, quality_issues=["blur"])
    create.return_value = reply(json.dumps(payload))
    result = await estimator.estimate(request_data)
    assert result.image_status is SlotStatus.NOT_DETERMINABLE
    assert result.image_issues == (QualityIssue.BLUR,)
    assert len(result.slots) == 6
    assert all(slot.intake_fraction_est is None for slot in result.slots)


@pytest.mark.asyncio
@pytest.mark.parametrize("slot_count", [1, 3, 7])
async def test_requested_slot_count_is_dynamic(estimator, create, request_data, slot_count):
    slots = list(request_data.slots)
    if slot_count > len(slots):
        slots.append(SlotSpec("slot_7", "Dish 7", 70.0, "7"))
    slots = tuple(slots[:slot_count])
    request = replace(request_data, slots=slots)
    payload = {
        "image_status": "estimated",
        "image_issues": [],
        "slots": [
            {
                "slot_id": slot.slot_id,
                "intake_fraction_est": 0.4,
                "status": "estimated",
                "quality_issues": [],
                "note": "Some food remains.",
            }
            for slot in reversed(slots)
        ],
    }
    create.return_value = reply(json.dumps(payload))

    result = await estimator.estimate(request)

    assert [slot.slot_id for slot in result.slots] == [slot.slot_id for slot in slots]
    assert [slot.intake_fraction_est for slot in result.slots] == [0.4] * slot_count


@pytest.mark.asyncio
@pytest.mark.parametrize("problem", ["zero", "blank_id", "duplicate_id"])
async def test_invalid_requested_slot_ids_are_rejected(estimator, create, request_data, problem):
    if problem == "zero":
        slots = ()
    elif problem == "blank_id":
        slots = (replace(request_data.slots[0], slot_id=""),)
    else:
        slots = (request_data.slots[0], replace(request_data.slots[1], slot_id="slot_1"))

    with pytest.raises(ValueError):
        await estimator.estimate(replace(request_data, slots=slots))

    create.assert_not_awaited()


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
        intake_fraction_est=None,
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
        "Report intake_fraction_est as a visual fraction from 0.0 to 1.0",
        "0.1 through 0.8",
        "0.9: most of the serving is gone",
    ):
        assert marker in system
    assert "consumed_tenths" not in system
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
                    "intake_fraction_est": None if unknown else 0.4,
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

    photo_root = request_data.baseline_image.parent / "var" / "photos"
    photo_root.mkdir(parents=True)
    baseline = photo_root / "before.jpg"
    post = photo_root / "after.jpg"
    baseline.write_bytes(request_data.baseline_image.read_bytes())
    post.write_bytes(request_data.post_image.read_bytes())
    request = replace(request_data, baseline_image=baseline, post_image=post)
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
        var_dir=photo_root.parent,
    )
    app = create_app(settings)
    estimator = app.state.intake_estimator
    assert isinstance(estimator, ClaudeIntakeEstimator)
    assert estimator._allowed_image_root == photo_root.resolve()
    assert options == {
        "api_key": "mock-key",
        "base_url": "https://api.anthropic.com",
        "timeout": 60.0,
        "max_retries": 0,
    }
    result = await estimator.estimate(request)
    assert result.estimate_basis == "vlm:claude"
    await estimator.aclose()
    client.close.assert_awaited_once()


def test_photo_root_default_is_independent_of_cwd(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("VAR_DIR", raising=False)
    settings = Settings(_env_file=None)
    assert settings.var_dir == REPO_ROOT / "var"
    assert storage_paths(settings).photos_dir == settings.var_dir / "photos"


@pytest.mark.asyncio
async def test_api_error_exposes_only_sanitized_metadata(estimator, create, request_data):
    detail = (
        "Invalid request: x-api-key: sk-ant-test-secret "
        "Authorization: Bearer bearer-test-secret "
        "data:image/jpeg;base64," + "A" * 80
    )
    response = Response(
        400,
        json={
            "type": "error",
            "error": {
                "type": "invalid_request_error",
                "message": detail,
            },
        },
        request=Request("POST", "https://api.anthropic.com/v1/messages"),
    )
    create.side_effect = BadRequestError(
        "Bad request",
        response=response,
        body=response.json(),
    )

    with pytest.raises(ClaudeAPIError) as captured:
        await estimator.estimate(request_data)

    error = captured.value
    assert isinstance(error, EstimationError)
    assert error.http_status_code == 400
    assert error.error_type == "BadRequestError"
    assert error.error_category == "invalid_request_error"
    assert "Invalid request" in (error.error_message or "")
    assert "sk-ant-test-secret" not in (error.error_message or "")
    assert "bearer-test-secret" not in (error.error_message or "")
    assert "data:image/jpeg;base64" not in (error.error_message or "")
    create.assert_awaited_once()
