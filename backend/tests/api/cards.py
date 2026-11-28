"""API 쓰기 테스트(추천 수정·확정·다시 만들기·처방 작성)가 함께 쓰는 도우미.

카드는 테스트 앱의 쓰기 실행기(`writer.run_sync`)로 넣는다(이벤트 없음). 환자 NS05는 시드에
추천 카드가 없다. 카드 기본 항목은 `rx1`(에이전트, 근거 2개)·`rx2`·`rx3`(의사)다.
쓰기 실패(`broken`)와 요청 중단(`run_abandoned`) 도우미도 여기 둔다. 기다림은 모두 `TIMEOUT` 상한을
둔다(실제 시간 경과에 기대지 않는다).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings, storage_paths
from app.events.bus import Event
from app.services.clock import format_app_timestamp
from app.services.ports import RecommendationItem
from app.services.unit_of_work import WriteResult
from app.storage import recommendations as rec_store
from app.storage.codec import items_to_json
from app.storage.db import connect

# 카드 ID·저장 시각·카드 읽기는 서비스 테스트 도우미를 그대로 쓴다(API 테스트도 여기서 가져간다).
from tests.services.cards import CARD_ID, STORED_AT, read_card
from tests.services.gates import ThreadGate
from tests.services.generation import TIMEOUT
from tests.storage.items import AGENT_ITEM, DOCTOR_ITEM
from tests.storage.rows import insert_recommendation
from tests.support.events import EventRecorder

PATIENT = "NS05"
THIRD_ITEM = replace(DOCTOR_ITEM, item_id="rx3", title="간식 추가")
CARD_ITEMS: tuple[RecommendationItem, ...] = (AGENT_ITEM, DOCTOR_ITEM, THIRD_ITEM)
# 게이트에서 멈춘 요청을 클라이언트가 포기할 때까지 기다리는 시간(초). 짧아도 결과는 같다.
ABANDON_AFTER_S = 0.05


def add_card_via_app(
    client: TestClient,
    *,
    recommendation_id: str = CARD_ID,
    status: str = "active",
    items: tuple[RecommendationItem, ...] = CARD_ITEMS,
) -> None:
    """앱의 쓰기 실행기로 NS05 카드를 넣는다. 이벤트는 발행하지 않는다."""

    def insert(conn: sqlite3.Connection) -> WriteResult[None]:
        insert_recommendation(
            conn,
            recommendation_id=recommendation_id,
            patient_id=PATIENT,
            items=items_to_json(items),
            status=status,
        )
        return WriteResult(None, ())

    client.app.state.runtime.writer.run_sync(insert)


def app_db(settings: Settings) -> Path:
    """앱이 쓰는 `app.db` 경로."""
    return storage_paths(settings).app_db


def count_prescriptions(db: Path, patient_id: str = PATIENT) -> int:
    """그 환자의 처방 행 수."""
    with connect(db) as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM prescriptions WHERE patient_id = ?", (patient_id,)
        ).fetchone()
    return int(row[0])


def assert_card_still_active(
    db: Path,
    *,
    items: tuple[RecommendationItem, ...] | None = None,
    updated_at: str | None = None,
) -> None:
    """카드가 `active`이고 그 환자 처방이 없다. 주면 항목·`updated_at`(저장 문자열)도 확인한다."""
    card = read_card(db)
    assert card.status.value == "active"
    assert count_prescriptions(db) == 0
    if items is not None:
        assert card.items == items
    if updated_at is not None:
        assert format_app_timestamp(card.updated_at) == updated_at


def item_input(item: RecommendationItem, **overrides: object) -> dict[str, object]:
    """항목을 `ItemInput` JSON으로 바꾼다(`added_by`·`evidence` 제외)."""
    body: dict[str, object] = {
        "item_id": item.item_id,
        "type": item.type.value,
        "title": item.title,
        "detail": item.detail,
        "duration_days": item.duration_days,
        "review_date": None if item.review_date is None else item.review_date.isoformat(),
    }
    return {**body, **overrides}


def patch_body(
    items: list[dict[str, object]], expected_updated_at: str = STORED_AT
) -> dict[str, object]:
    """PATCH 요청 본문."""
    return {"items": items, "expected_updated_at": expected_updated_at}


def confirm_body(item_ids: list[str], expected_updated_at: str = STORED_AT) -> dict[str, object]:
    """확정 요청 본문."""
    return {"item_ids": item_ids, "expected_updated_at": expected_updated_at}


def patch_url(recommendation_id: str = CARD_ID) -> str:
    """카드 수정(PATCH) 경로."""
    return f"/api/recommendations/{recommendation_id}"


def confirm_url(recommendation_id: str = CARD_ID) -> str:
    """카드 확정(POST) 경로."""
    return f"/api/recommendations/{recommendation_id}/confirm"


def broken(*_args: Any, **_kwargs: Any) -> Any:
    """저장 SQL 대신 넣어 예외를 던지는 함수."""
    raise RuntimeError("저장 SQL 실패(테스트)")


def run_abandoned(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    pool: ThreadPoolExecutor,
    *,
    gated_name: str,
    send: Callable[[TestClient], httpx.Response],
    event_name: str,
    check_unchanged: Callable[[], None],
    gate: ThreadGate | None = None,
) -> tuple[Event, httpx.Response]:
    """저장 SQL `rec_store.<gated_name>`에서 멈춘 요청을 클라이언트가 포기한 뒤 멈춤을 푼다.

    포기 시점에 `check_unchanged()`로 DB가 그대로임을 확인하고, 받은 이벤트와 (끝까지 처리된)
    응답을 돌려준다. 준비 데이터(카드 등)는 호출자가 먼저 넣는다. 게이트에 기록 등을 덧붙이려면
    `gate`를 넘긴다.
    """
    gate = ThreadGate() if gate is None else gate
    gate.patch(monkeypatch, rec_store, gated_name)

    with EventRecorder(client) as recorder:
        sent = pool.submit(send, client)
        assert gate.entered.wait(TIMEOUT)
        with pytest.raises(TimeoutError):
            sent.result(timeout=ABANDON_AFTER_S)
        check_unchanged()

        gate.release.set()
        event = recorder.wait_for(event_name)

    # 포기한 호출도 서버에서는 끝까지 처리된다(호출 스레드 정리 겸 응답 확인).
    return event, sent.result(timeout=TIMEOUT)
