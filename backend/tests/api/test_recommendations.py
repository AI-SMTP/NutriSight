"""추천 카드 수정(PATCH)·확정 API의 성공·오류 응답 테스트 (스펙 3.3·3.4).

테스트마다 새 앱(`write_client`)을 쓴다. 실패·중단·종료는 `test_recommendation_writes.py`.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from tests.api.cards import (
    CARD_ID,
    CARD_ITEMS,
    PATIENT,
    STORED_AT,
    THIRD_ITEM,
    add_card_via_app,
    app_db,
    assert_card_still_active,
    confirm_body,
    confirm_url,
    item_input,
    patch_body,
    patch_url,
    read_card,
)
from tests.storage.items import AGENT_ITEM, DOCTOR_ITEM
from tests.support.events import EventRecorder

UPDATED = "recommendation.updated"
CONFIRMED = "prescription.confirmed"


@pytest.fixture
def card_client(write_client: TestClient) -> TestClient:
    """NS05에 `active` 카드(rx1·rx2·rx3)를 넣은 앱 클라이언트."""
    add_card_via_app(write_client)
    return write_client


def _card_json(client: TestClient) -> dict[str, Any]:
    body = client.get(f"/api/patients/{PATIENT}/recommendation").json()
    assert body is not None
    return body


# ---- PATCH 성공 ----


def test_patch_merges_items_and_marks_doctor(card_client: TestClient) -> None:
    items = [
        item_input(AGENT_ITEM, type="ons", title="식사 강화 14일", duration_days=14),
        item_input(THIRD_ITEM, item_id="rx9", type="snack_addition", review_date="2026-12-20"),
    ]

    with EventRecorder(card_client) as recorder:
        response = card_client.patch(patch_url(), json=patch_body(items))
        event = recorder.wait_for(UPDATED)

    assert response.status_code == 200
    body = response.json()
    assert [item["item_id"] for item in body["items"]] == ["rx1", "rx9"]
    kept, added = body["items"]
    assert kept["type"] == "food_fortification"  # 요청의 type은 무시
    assert kept["added_by"] == "agent"
    assert kept["evidence"] == [
        {"doc_id": "espen_geriatrics", "section": "R20"},
        {"doc_id": "espen_geriatrics", "section": "R23"},
    ]
    assert (kept["title"], kept["duration_days"]) == ("식사 강화 14일", 14)
    assert added["type"] == "snack_addition"
    assert added["added_by"] == "doctor"
    assert added["evidence"] == []
    assert added["review_date"] == "2026-12-20"
    assert body["last_modified_by"] == "doctor"
    assert body["thread_id"] is None
    assert body["status"] == "active"
    assert body["updated_at"] > STORED_AT
    assert body["created_at"] == STORED_AT
    assert event.data["recommendation_id"] == CARD_ID
    assert event.data["modified_by"] == "doctor"
    assert event.data["at"] == body["updated_at"]
    assert _card_json(card_client) == body


@pytest.mark.parametrize(
    "overrides",
    [
        {"item_id": "a" * 32},
        {"title": "가" * 100},
        {"detail": ""},
        {"detail": "가" * 1000},
        {"duration_days": 1},
        {"duration_days": 365},
        {"duration_days": None},
        {"review_date": None},
    ],
)
def test_patch_accepts_boundary_values(
    card_client: TestClient, overrides: dict[str, object]
) -> None:
    item = item_input(DOCTOR_ITEM, **overrides)

    response = card_client.patch(patch_url(), json=patch_body([item]))

    assert response.status_code == 200
    saved = response.json()["items"][0]
    for name, value in overrides.items():
        assert saved[name] == value


def test_patch_with_new_updated_at_succeeds_again(card_client: TestClient) -> None:
    first = card_client.patch(patch_url(), json=patch_body([item_input(AGENT_ITEM)])).json()

    second = card_client.patch(
        patch_url(), json=patch_body([item_input(DOCTOR_ITEM)], first["updated_at"])
    )

    assert second.status_code == 200
    assert second.json()["updated_at"] > first["updated_at"]


# ---- PATCH 오류 ----


@pytest.mark.parametrize(
    "expected_updated_at",
    ["2026-11-23T12:00:00.000001", "2026-11-23T12:00:00", "2026-11-23 12:00:00.000000"],
)
def test_patch_stale_returns_409_without_change_or_event(
    card_client: TestClient, write_settings: Settings, expected_updated_at: str
) -> None:
    # 같은 시각이라도 저장 문자열과 글자가 다르면 stale이다(문자열 그대로 비교).
    before = _card_json(card_client)

    with EventRecorder(card_client) as recorder:
        response = card_client.patch(
            patch_url(), json=patch_body([item_input(AGENT_ITEM)], expected_updated_at)
        )
        flushed = recorder.flush()

    assert response.status_code == 409
    assert response.json() == {"detail": "stale"}
    assert flushed == ()
    assert _card_json(card_client) == before
    assert read_card(app_db(write_settings)).items == CARD_ITEMS


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"item_id": "bad id!"}, id="id-format"),
        pytest.param({"item_id": "a" * 33}, id="id-33"),
        pytest.param({"item_id": ""}, id="id-empty"),
        pytest.param({"title": ""}, id="title-empty"),
        pytest.param({"title": "가" * 101}, id="title-101"),
        pytest.param({"detail": "가" * 1001}, id="detail-1001"),
        pytest.param({"duration_days": 0}, id="duration-0"),
        pytest.param({"duration_days": 366}, id="duration-366"),
        pytest.param({"duration_days": True}, id="duration-true"),
        pytest.param({"duration_days": "7"}, id="duration-str"),
        pytest.param({"type": "unknown"}, id="type"),
        pytest.param({"review_date": "12/20"}, id="review-date"),
        pytest.param({"review_date": 0}, id="review-date-int"),
        pytest.param({"review_date": "2026-12-20T00:00:00"}, id="review-date-datetime"),
        pytest.param({"added_by": "doctor"}, id="added-by"),
        pytest.param({"evidence": []}, id="evidence"),
    ],
)
def test_patch_invalid_item_returns_422_without_change(
    card_client: TestClient, overrides: dict[str, object]
) -> None:
    before = _card_json(card_client)

    response = card_client.patch(
        patch_url(), json=patch_body([item_input(AGENT_ITEM, **overrides)])
    )

    assert response.status_code == 422
    assert _card_json(card_client) == before


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(
            patch_body([item_input(AGENT_ITEM), item_input(DOCTOR_ITEM, item_id="rx1")]),
            id="dup-id",
        ),
        pytest.param({"items": [item_input(AGENT_ITEM)]}, id="no-expected"),
        pytest.param(
            {**patch_body([item_input(AGENT_ITEM)]), "status": "confirmed"}, id="extra-top"
        ),
    ],
)
def test_patch_invalid_body_returns_422_without_change(
    card_client: TestClient, body: dict[str, object]
) -> None:
    before = _card_json(card_client)

    response = card_client.patch(patch_url(), json=body)

    assert response.status_code == 422
    assert _card_json(card_client) == before


# ---- PATCH·확정 공통 오류 ----

_NOT_EDITABLE_REQUESTS = [
    pytest.param("PATCH", patch_url(), patch_body([item_input(AGENT_ITEM)]), id="patch"),
    pytest.param("POST", confirm_url(), confirm_body(["rx1"]), id="confirm"),
]
_MISSING_CARD_REQUESTS = [
    pytest.param("PATCH", patch_url("rec_missing"), patch_body([]), id="patch"),
    pytest.param("POST", confirm_url("rec_missing"), confirm_body(["rx1"]), id="confirm"),
]


@pytest.mark.parametrize(("method", "url", "body"), _NOT_EDITABLE_REQUESTS)
def test_confirmed_card_returns_409_not_editable(
    write_client: TestClient, method: str, url: str, body: dict[str, object]
) -> None:
    add_card_via_app(write_client, status="confirmed")

    response = write_client.request(method, url, json=body)

    assert response.status_code == 409
    assert response.json() == {"detail": "not_editable"}


@pytest.mark.parametrize(("method", "url", "body"), _MISSING_CARD_REQUESTS)
def test_unknown_card_returns_404(
    write_client: TestClient, method: str, url: str, body: dict[str, object]
) -> None:
    response = write_client.request(method, url, json=body)

    assert response.status_code == 404


# ---- 확정 성공 ----


def test_confirm_copies_selected_items_in_card_order(
    card_client: TestClient, write_settings: Settings
) -> None:
    with EventRecorder(card_client) as recorder:
        response = card_client.post(confirm_url(), json=confirm_body(["rx3", "rx1", "rx3"]))
        event = recorder.wait_for(CONFIRMED)
        names = recorder.flush()

    assert response.status_code == 201
    body = response.json()
    assert body["prescription_id"].startswith("rx_")
    assert body["patient_id"] == PATIENT
    assert body["recommendation_id"] == CARD_ID
    assert body["status"] == "confirmed"
    assert [item["item_id"] for item in body["items"]] == ["rx1", "rx3"]
    assert body["items"][0]["evidence"] == [
        {"doc_id": "espen_geriatrics", "section": "R20"},
        {"doc_id": "espen_geriatrics", "section": "R23"},
    ]
    assert isinstance(body["confirmed_at"], str)
    assert event.data["prescription_id"] == body["prescription_id"]
    assert [e.name for e in names] == [CONFIRMED]
    card = read_card(app_db(write_settings))
    assert card.status.value == "confirmed"
    assert [item.item_id for item in card.items] == ["rx1", "rx2", "rx3"]  # 고르지 않은 항목 유지


def test_patch_after_confirm_returns_409_not_editable(card_client: TestClient) -> None:
    assert card_client.post(confirm_url(), json=confirm_body(["rx1"])).status_code == 201

    response = card_client.patch(patch_url(), json=patch_body([item_input(AGENT_ITEM)]))

    assert response.status_code == 409
    assert response.json() == {"detail": "not_editable"}


# ---- 확정 오류 ----


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(confirm_body([]), id="empty-ids"),
        pytest.param(confirm_body(["rx1", "nope"]), id="unknown-id"),
        pytest.param({"item_ids": ["rx1"]}, id="no-expected"),
        pytest.param({**confirm_body(["rx1"]), "items": []}, id="extra"),
    ],
)
def test_confirm_invalid_request_returns_422(
    card_client: TestClient, write_settings: Settings, body: dict[str, object]
) -> None:
    with EventRecorder(card_client) as recorder:
        response = card_client.post(confirm_url(), json=body)
        flushed = recorder.flush()

    assert response.status_code == 422
    assert flushed == ()
    assert_card_still_active(app_db(write_settings), updated_at=STORED_AT)


def test_confirm_rejects_more_than_100_item_ids_in_request_validation(
    card_client: TestClient, write_settings: Settings
) -> None:
    # 요청 검증 단계의 422(본문 위치 표시)여야 한다. 서비스의 "없는 item_id" 422와 구분한다.
    response = card_client.post(confirm_url(), json=confirm_body(["rx1"] * 101))

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "item_ids"]
    assert_card_still_active(app_db(write_settings), updated_at=STORED_AT)


def test_confirm_stale_returns_409(card_client: TestClient, write_settings: Settings) -> None:
    response = card_client.post(confirm_url(), json=confirm_body(["rx1"], "2026-11-23T12:00:00"))

    assert response.status_code == 409
    assert response.json() == {"detail": "stale"}
    assert_card_still_active(app_db(write_settings), updated_at=STORED_AT)


def test_confirm_empty_ids_on_unknown_card_returns_422_first(write_client: TestClient) -> None:
    # 판정 순서: 빈 목록 422가 없는 카드 404보다 먼저다.
    response = write_client.post(confirm_url("rec_missing"), json=confirm_body([]))

    assert response.status_code == 422
