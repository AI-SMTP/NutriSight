"""추천 다시 만들기 API 테스트 (스펙 3.3 `POST /patients/{id}/recommendation/regenerate`, 3.5).

테스트마다 새 앱을 쓴다. 생성기 실패는 `app.state.recommendation_deps`의 생성기를
`FakeRecommendationGenerator(fail=True)`로 바꾼 앱에서 확인한다. 환자 NS05는 시드에 카드가 없고,
시연일 이하 최신 판정은 `alert_NS05_2026-12-04`(수준 none)이다.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.recommender.fake_generator import FakeRecommendationGenerator
from app.services.unit_of_work import WriteResult
from app.storage import recommendations as rec_store
from tests.api.cards import CARD_ID, PATIENT, add_card_via_app, app_db, broken
from tests.services.generation import statuses
from tests.support.events import EventRecorder

CREATED = "recommendation.created"
LATEST_ALERT = "alert_NS05_2026-12-04"
FAILED_CARD_ID = "R0002"
MISSING_PATIENT = "NS99"


def regenerate_url(patient_id: str = PATIENT) -> str:
    """다시 만들기(POST) 경로."""
    return f"/api/patients/{patient_id}/recommendation/regenerate"


def _add_open_cards(client: TestClient) -> None:
    """NS05에 `active` 카드(R0001)와 `failed` 카드(R0002)를 넣는다."""
    add_card_via_app(client)
    add_card_via_app(client, recommendation_id=FAILED_CARD_ID, status="failed", items=())


@pytest.fixture
def failing_client(write_settings: Settings) -> Iterator[TestClient]:
    """생성기가 항상 `GenerationError`를 던지는 앱 클라이언트."""
    app = create_app(write_settings)
    app.state.recommendation_deps = replace(
        app.state.recommendation_deps, generator=FakeRecommendationGenerator(fail=True)
    )
    with TestClient(app) as client:
        yield client


# ---- 성공 ----


def test_regenerate_returns_active_card_and_supersedes_open_cards(
    write_client: TestClient, write_settings: Settings
) -> None:
    _add_open_cards(write_client)

    with EventRecorder(write_client) as recorder:
        response = write_client.post(regenerate_url())
        event = recorder.wait_for(CREATED)

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "active"
    assert body["patient_id"] == PATIENT
    assert body["alert_id"] == LATEST_ALERT
    assert body["last_modified_by"] == "agent"
    assert body["thread_id"] is None
    assert [item["type"] for item in body["items"]] == ["food_fortification", "monitoring_review"]
    assert all(item["added_by"] == "agent" for item in body["items"])
    assert body["recommendation_id"].startswith("rec_")
    assert event.data["recommendation_id"] == body["recommendation_id"]
    assert event.data["status"] == "active"
    assert statuses(app_db(write_settings), PATIENT) == {
        CARD_ID: "superseded",
        FAILED_CARD_ID: "superseded",
        body["recommendation_id"]: "active",
    }
    assert write_client.get(f"/api/patients/{PATIENT}/recommendation").json() == body


def test_regenerate_with_failing_generator_returns_failed_card(
    failing_client: TestClient, write_settings: Settings
) -> None:
    add_card_via_app(failing_client)

    with EventRecorder(failing_client) as recorder:
        response = failing_client.post(regenerate_url())
        event = recorder.wait_for(CREATED)

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "failed"
    assert body["items"] == []
    assert body["cautions"] == []
    assert body["alert_id"] == LATEST_ALERT
    assert event.data["status"] == "failed"
    assert statuses(app_db(write_settings), PATIENT) == {
        CARD_ID: "superseded",
        body["recommendation_id"]: "failed",
    }


def test_regenerate_patient_without_alert_returns_card_without_alert(
    write_client: TestClient, write_settings: Settings
) -> None:
    db = app_db(write_settings)
    # `recommendations.alert_id`가 `alerts`를 참조하므로 판정을 지우려면 그 환자 카드가
    # 없어야 한다(NS05는 시드에 카드가 없다).
    assert statuses(db, PATIENT) == {}

    def delete_alerts(conn: sqlite3.Connection) -> WriteResult[None]:
        conn.execute("DELETE FROM alerts WHERE patient_id = ?", (PATIENT,))
        return WriteResult(None, ())

    write_client.app.state.runtime.writer.run_sync(delete_alerts)

    with EventRecorder(write_client) as recorder:
        response = write_client.post(regenerate_url())
        event = recorder.wait_for(CREATED)

    assert response.status_code == 201
    body = response.json()
    assert body["alert_id"] is None
    assert body["status"] == "active"
    assert event.data["recommendation_id"] == body["recommendation_id"]
    assert event.data["status"] == "active"
    assert statuses(db, PATIENT) == {body["recommendation_id"]: "active"}


# ---- 오류 ----


def test_regenerate_unknown_patient_returns_404_without_card(
    write_client: TestClient, write_settings: Settings
) -> None:
    with EventRecorder(write_client) as recorder:
        response = write_client.post(regenerate_url(MISSING_PATIENT))
        flushed = recorder.flush()

    assert response.status_code == 404
    assert flushed == ()
    assert statuses(app_db(write_settings), MISSING_PATIENT) == {}
    assert statuses(app_db(write_settings), PATIENT) == {}


def test_regenerate_save_failure_returns_500_without_event_or_change(
    lenient_client: TestClient, write_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    _add_open_cards(lenient_client)
    monkeypatch.setattr(rec_store, "insert_card", broken)

    with EventRecorder(lenient_client) as recorder:
        response = lenient_client.post(regenerate_url())
        flushed = recorder.flush()

    assert response.status_code == 500
    assert flushed == ()
    assert statuses(app_db(write_settings), PATIENT) == {
        CARD_ID: "active",
        FAILED_CARD_ID: "failed",
    }


def test_openapi_has_regenerate_post_path(write_client: TestClient) -> None:
    paths = write_client.app.openapi()["paths"]

    assert set(paths[regenerate_url("{patient_id}")]) == {"post"}
