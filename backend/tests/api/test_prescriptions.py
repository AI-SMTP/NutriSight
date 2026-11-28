"""처방 직접 작성·이력 API 테스트 (스펙 3.3 `POST·GET /patients/{id}/prescriptions`, 3.2).

테스트마다 새 앱을 쓴다. 저장 실패는 저장 SQL을 예외로 바꾸고, 요청 중단은 `ThreadGate`로 쓰기
실행기 스레드를 멈춘 뒤 클라이언트가 포기하게 한다. 기다림은 모두 `TIMEOUT` 상한을 둔다.
처방은 확정 뒤 바꾸지 않으므로 처방 수정·삭제 경로가 없음도 확인한다.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.schemas import REQUEST_LIST_MAX
from app.config import Settings
from app.services.clock import format_app_timestamp
from app.storage import recommendations as rec_store
from tests.api.cards import (
    CARD_ITEMS,
    PATIENT,
    STORED_AT,
    add_card_via_app,
    app_db,
    broken,
    count_prescriptions,
    item_input,
    read_card,
    run_abandoned,
)
from tests.services.gates import ThreadGate
from tests.storage.items import AGENT_ITEM, DOCTOR_ITEM
from tests.support.events import EventRecorder

CONFIRMED = "prescription.confirmed"
MISSING_PATIENT = "NS99"
WRITER_THREAD_PREFIX = "db-writer"  # `app.services.runtime`의 쓰기 실행기 스레드 이름 접두어

ITEMS = [
    item_input(AGENT_ITEM, title="식사 강화 7일"),
    item_input(DOCTOR_ITEM, item_id="rx9", review_date="2026-12-20"),
]


def prescriptions_url(patient_id: str = PATIENT) -> str:
    """처방 작성(POST)·이력(GET) 경로."""
    return f"/api/patients/{patient_id}/prescriptions"


def _assert_no_prescription(db: Path) -> None:
    assert count_prescriptions(db) == 0


# ---- 처방 작성 ----


def test_create_prescription_returns_doctor_items_and_leaves_card(
    write_client: TestClient, write_settings: Settings
) -> None:
    add_card_via_app(write_client)

    with EventRecorder(write_client) as recorder:
        response = write_client.post(prescriptions_url(), json={"items": ITEMS})
        event = recorder.wait_for(CONFIRMED)

    assert response.status_code == 201
    body = response.json()
    assert body["prescription_id"].startswith("rx_")
    assert body["patient_id"] == PATIENT
    assert body["recommendation_id"] is None
    assert body["status"] == "confirmed"
    assert [item["item_id"] for item in body["items"]] == ["rx1", "rx9"]
    assert body["items"][0]["title"] == "식사 강화 7일"
    assert body["items"][1]["review_date"] == "2026-12-20"
    assert all(item["added_by"] == "doctor" for item in body["items"])
    assert all(item["evidence"] == [] for item in body["items"])
    assert event.data["prescription_id"] == body["prescription_id"]
    assert event.data["recommendation_id"] is None
    assert event.data["at"] == body["confirmed_at"]

    card = read_card(app_db(write_settings))
    assert card.status.value == "active"
    assert card.items == CARD_ITEMS
    assert format_app_timestamp(card.updated_at) == STORED_AT


@pytest.mark.parametrize(
    "body",
    [
        pytest.param({"items": []}, id="empty-items"),
        pytest.param({}, id="missing-items"),
        pytest.param({"items": [ITEMS[0], ITEMS[0]]}, id="duplicate-item-id"),
        pytest.param({"items": [{**ITEMS[0], "added_by": "agent"}]}, id="added-by-field"),
        pytest.param({"items": [{**ITEMS[0], "title": ""}]}, id="empty-title"),
        pytest.param({"items": ITEMS, "recommendation_id": "R0001"}, id="extra-field"),
    ],
)
def test_create_prescription_invalid_body_returns_422(
    write_client: TestClient, write_settings: Settings, body: dict[str, Any]
) -> None:
    response = write_client.post(prescriptions_url(), json=body)

    assert response.status_code == 422
    assert count_prescriptions(app_db(write_settings)) == 0


def test_create_prescription_over_item_limit_returns_422(
    write_client: TestClient, write_settings: Settings
) -> None:
    items = [item_input(DOCTOR_ITEM, item_id=f"rx{n}") for n in range(REQUEST_LIST_MAX + 1)]

    response = write_client.post(prescriptions_url(), json={"items": items})

    assert response.status_code == 422
    errors = response.json()["detail"]
    assert [(e["loc"], e["type"]) for e in errors] == [(["body", "items"], "too_long")]
    assert count_prescriptions(app_db(write_settings)) == 0


def test_create_prescription_at_item_limit_succeeds(write_client: TestClient) -> None:
    items = [item_input(DOCTOR_ITEM, item_id=f"rx{n}") for n in range(REQUEST_LIST_MAX)]

    response = write_client.post(prescriptions_url(), json={"items": items})

    assert response.status_code == 201
    assert len(response.json()["items"]) == REQUEST_LIST_MAX


def test_create_prescription_unknown_patient_returns_404(
    write_client: TestClient, write_settings: Settings
) -> None:
    with EventRecorder(write_client) as recorder:
        response = write_client.post(prescriptions_url(MISSING_PATIENT), json={"items": ITEMS})
        flushed = recorder.flush()

    assert response.status_code == 404
    assert flushed == ()
    assert count_prescriptions(app_db(write_settings), MISSING_PATIENT) == 0


def test_create_prescription_save_failure_returns_500_without_event(
    lenient_client: TestClient, write_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(rec_store, "insert_prescription", broken)

    with EventRecorder(lenient_client) as recorder:
        response = lenient_client.post(prescriptions_url(), json={"items": ITEMS})
        flushed = recorder.flush()

    assert response.status_code == 500
    assert flushed == ()
    assert count_prescriptions(app_db(write_settings)) == 0


def test_abandoned_create_prescription_still_commits_and_publishes(
    write_client: TestClient,
    write_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    pool: ThreadPoolExecutor,
) -> None:
    db = app_db(write_settings)
    gate = ThreadGate()
    gated_threads: list[str] = []
    real_hold = gate.hold

    def recording_hold() -> None:
        gated_threads.append(threading.current_thread().name)
        real_hold()

    monkeypatch.setattr(gate, "hold", recording_hold)

    event, response = run_abandoned(
        write_client,
        monkeypatch,
        pool,
        gated_name="insert_prescription",
        send=lambda c: c.post(prescriptions_url(), json={"items": ITEMS}),
        event_name=CONFIRMED,
        check_unchanged=lambda: _assert_no_prescription(db),
        gate=gate,
    )

    assert count_prescriptions(db) == 1
    assert event.data["patient_id"] == PATIENT
    assert response.status_code == 201
    # 저장은 요청 스레드가 아니라 쓰기 실행기 스레드에서 돈다.
    assert len(gated_threads) == 1
    assert gated_threads[0].startswith(WRITER_THREAD_PREFIX)


# ---- 이력 ----


def test_list_prescriptions_newest_first(write_client: TestClient) -> None:
    first = write_client.post(prescriptions_url(), json={"items": ITEMS[:1]}).json()
    second = write_client.post(prescriptions_url(), json={"items": ITEMS[1:]}).json()

    response = write_client.get(prescriptions_url())

    assert response.status_code == 200
    body = response.json()
    assert [p["prescription_id"] for p in body] == [
        second["prescription_id"],
        first["prescription_id"],
    ]
    assert body[0]["confirmed_at"] > body[1]["confirmed_at"]
    assert body == [second, first]


def test_list_prescriptions_empty_for_patient_without_prescriptions(
    write_client: TestClient,
) -> None:
    response = write_client.get(prescriptions_url())

    assert response.status_code == 200
    assert response.json() == []


def test_list_prescriptions_unknown_patient_returns_404(write_client: TestClient) -> None:
    assert write_client.get(prescriptions_url(MISSING_PATIENT)).status_code == 404


# ---- 처방 수정·삭제 경로 없음 ----


@pytest.mark.parametrize("method", ["PATCH", "PUT", "DELETE"])
def test_prescription_edit_paths_do_not_exist(write_client: TestClient, method: str) -> None:
    created = write_client.post(prescriptions_url(), json={"items": ITEMS}).json()

    response = write_client.request(
        method, f"/api/prescriptions/{created['prescription_id']}", json={"items": ITEMS}
    )

    assert response.status_code in (404, 405)


def test_openapi_has_no_prescription_edit_paths(write_client: TestClient) -> None:
    paths = write_client.app.openapi()["paths"]

    assert set(paths[prescriptions_url("{patient_id}")]) == {"get", "post"}
    assert not [path for path in paths if path.startswith("/api/prescriptions")]
