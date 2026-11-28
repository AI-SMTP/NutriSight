"""쓰기 테스트용 함수 범위 앱(`write_client`) 동작 테스트."""

from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient

from app.events.bus import Event
from app.services.unit_of_work import WriteResult
from tests.storage.rows import insert_recommendation
from tests.support.events import EventRecorder

CARD_ID = "rec_write_client"
CREATED = "card.created"


def _insert_card(conn: sqlite3.Connection) -> WriteResult[None]:
    insert_recommendation(conn, recommendation_id=CARD_ID, patient_id="NS05")
    return WriteResult(None, (Event(CREATED, {"recommendation_id": CARD_ID}),))


def test_write_client_has_own_db_and_bus(write_client: TestClient, client: TestClient) -> None:
    with EventRecorder(write_client) as recorder:
        write_client.app.state.runtime.writer.run_sync(_insert_card)

        flushed = recorder.flush()

    assert [event.name for event in flushed] == [CREATED]
    written = write_client.get("/api/patients/NS05/recommendation").json()
    assert written["recommendation_id"] == CARD_ID
    assert client.get("/api/patients/NS05/recommendation").json() is None
