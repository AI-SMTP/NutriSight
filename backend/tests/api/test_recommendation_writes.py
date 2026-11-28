"""추천 수정·확정 API의 쓰기 실패·요청 중단·종료 테스트 (스펙 3.2 쓰기 실행기·종료 정책).

저장 SQL을 예외로 바꾸거나 `ThreadGate`로 쓰기 실행기 스레드를 멈춘다. 클라이언트 호출은 별도
스레드에서 보내고, 기다림은 모두 `TIMEOUT` 상한을 둔다(실제 시간 경과에 기대지 않는다).
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from concurrent.futures import Future, ThreadPoolExecutor, wait
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings, storage_paths
from app.events.bus import Event
from app.main import create_app
from app.storage import recommendations as rec_store
from app.storage.app_lock import AppLock
from tests.api.cards import (
    CARD_ID,
    CARD_ITEMS,
    add_card_via_app,
    app_db,
    assert_card_still_active,
    confirm_body,
    confirm_url,
    count_prescriptions,
    item_input,
    patch_body,
    patch_url,
    read_card,
)
from tests.app_lock import assert_lock_free, assert_lock_held
from tests.services.gates import ThreadGate
from tests.services.generation import TIMEOUT
from tests.storage.items import AGENT_ITEM
from tests.support.events import EventRecorder

UPDATED = "recommendation.updated"
CONFIRMED = "prescription.confirmed"
# 게이트에서 멈춘 요청을 클라이언트가 포기할 때까지 기다리는 시간(초). 짧아도 결과는 같다.
ABANDON_AFTER_S = 0.05

PATCH_ITEMS = [item_input(AGENT_ITEM, title="수정한 제목")]


def _broken(*_args: Any, **_kwargs: Any) -> Any:
    raise RuntimeError("저장 SQL 실패(테스트)")


@pytest.fixture
def pool() -> Iterator[ThreadPoolExecutor]:
    """클라이언트 호출을 보낼 스레드들."""
    executor = ThreadPoolExecutor(max_workers=2)
    yield executor
    executor.shutdown(wait=True)


@pytest.fixture
def lenient_client(write_settings: Settings) -> Iterator[TestClient]:
    """서버 예외를 500 응답으로 돌려주는 앱 클라이언트. NS05 카드(rx1·rx2·rx3)를 넣어 둔다."""
    with TestClient(create_app(write_settings), raise_server_exceptions=False) as client:
        add_card_via_app(client)
        yield client


# ---- 쓰기 실패: 500, 이벤트 없음, DB 그대로 ----


@pytest.mark.parametrize(
    ("broken_name", "send"),
    [
        pytest.param(
            "update_card_items",
            lambda c: c.patch(patch_url(), json=patch_body(PATCH_ITEMS)),
            id="patch",
        ),
        pytest.param(
            "insert_prescription",
            lambda c: c.post(confirm_url(), json=confirm_body(["rx1"])),
            id="confirm",
        ),
    ],
)
def test_write_failure_returns_500_without_event_or_change(
    lenient_client: TestClient,
    write_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    broken_name: str,
    send: Callable[[TestClient], httpx.Response],
) -> None:
    monkeypatch.setattr(rec_store, broken_name, _broken)

    with EventRecorder(lenient_client) as recorder:
        response = send(lenient_client)
        flushed = recorder.flush()

    assert response.status_code == 500
    assert flushed == ()
    assert_card_still_active(app_db(write_settings), items=CARD_ITEMS)


# ---- 요청 중단: 클라이언트가 포기해도 커밋·발행 ----


def _abandon(future: Future[httpx.Response]) -> None:
    """멈춘 요청을 클라이언트 쪽 시간 초과로 포기한다."""
    with pytest.raises(TimeoutError):
        future.result(timeout=ABANDON_AFTER_S)


def _run_abandoned(
    client: TestClient,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    pool: ThreadPoolExecutor,
    *,
    gated_name: str,
    send: Callable[[TestClient], httpx.Response],
    event_name: str,
) -> tuple[Event, httpx.Response]:
    """저장 SQL `gated_name`에서 멈춘 요청을 클라이언트가 포기한 뒤 멈춤을 푼다.

    포기 시점에 카드가 그대로임을 확인하고, 받은 이벤트와 (끝까지 처리된) 응답을 돌려준다.
    """
    add_card_via_app(client)
    gate = ThreadGate()
    gate.patch(monkeypatch, rec_store, gated_name)

    with EventRecorder(client) as recorder:
        sent = pool.submit(send, client)
        assert gate.entered.wait(TIMEOUT)
        _abandon(sent)
        assert_card_still_active(app_db(settings), items=CARD_ITEMS)

        gate.release.set()
        event = recorder.wait_for(event_name)

    # 포기한 호출도 서버에서는 끝까지 처리된다(호출 스레드 정리 겸 응답 확인).
    return event, sent.result(timeout=TIMEOUT)


def test_abandoned_patch_still_commits_and_publishes(
    write_client: TestClient,
    write_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    pool: ThreadPoolExecutor,
) -> None:
    event, response = _run_abandoned(
        write_client,
        write_settings,
        monkeypatch,
        pool,
        gated_name="update_card_items",
        send=lambda c: c.patch(patch_url(), json=patch_body(PATCH_ITEMS)),
        event_name=UPDATED,
    )

    assert event.data["recommendation_id"] == CARD_ID
    assert read_card(app_db(write_settings)).items[0].title == "수정한 제목"
    assert response.status_code == 200


def test_abandoned_confirm_still_commits_and_publishes(
    write_client: TestClient,
    write_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    pool: ThreadPoolExecutor,
) -> None:
    event, response = _run_abandoned(
        write_client,
        write_settings,
        monkeypatch,
        pool,
        gated_name="insert_prescription",
        send=lambda c: c.post(confirm_url(), json=confirm_body(["rx1"])),
        event_name=CONFIRMED,
    )

    assert event.data["recommendation_id"] == CARD_ID
    assert read_card(app_db(write_settings)).status.value == "confirmed"
    assert count_prescriptions(app_db(write_settings)) == 1
    assert response.status_code == 201


# ---- 종료 (나): 동기 PATCH 경로의 실행 중인 쓰기가 끝난 뒤 잠금 해제 ----


def test_shutdown_waits_running_patch_before_releasing_lock(
    write_settings: Settings, monkeypatch: pytest.MonkeyPatch, pool: ThreadPoolExecutor
) -> None:
    db = app_db(write_settings)
    app = create_app(write_settings)
    runtime = app.state.runtime
    gate = ThreadGate()

    # 쓰기 실행기 종료(종료 정책 3단계)에 들어온 순간을 알린다.
    shutdown_entered = threading.Event()
    real_shutdown = runtime.writer.shutdown

    def spying_shutdown() -> None:
        shutdown_entered.set()
        real_shutdown()

    monkeypatch.setattr(runtime.writer, "shutdown", spying_shutdown)

    # 잠금을 놓는 순간 PATCH가 이미 커밋돼 있었는지 기록한다(시작 전에 바꾼다).
    titles_at_release: list[str] = []
    real_release = AppLock.release

    # 첫 기록만 남긴다. 이 테스트에서 잡힌 잠금(`_fd`가 있음)을 처음 놓는 것은 lifespan 종료다.
    # 아래 `assert_lock_free`도 같은 경로의 잠금을 잡았다 놓으므로, 이 조건이 없으면 기록 내용이
    # 단언 순서(`titles_at_release` 확인과 `assert_lock_free`의 선후)에 따라 달라진다.
    def recording_release(self: AppLock) -> None:
        lock_path = storage_paths(write_settings).app_lock
        if not titles_at_release and self._fd is not None and self._path == lock_path:
            titles_at_release.append(read_card(db).items[0].title)
        real_release(self)

    monkeypatch.setattr(AppLock, "release", recording_release)

    client = TestClient(app)
    client.__enter__()
    stopping: Future[Any] | None = None
    try:
        add_card_via_app(client)
        gate.patch(monkeypatch, rec_store, "update_card_items")
        sent = pool.submit(client.patch, patch_url(), json=patch_body(PATCH_ITEMS))
        assert gate.entered.wait(TIMEOUT)

        # PATCH를 보낸 스레드를 기다리지 않고 종료를 시작한다.
        stopping = pool.submit(client.__exit__, None, None, None)
        assert shutdown_entered.wait(TIMEOUT)

        assert_lock_held(write_settings)
        assert not stopping.done()
        assert read_card(db).items == CARD_ITEMS

        gate.release.set()
        stopping.result(timeout=TIMEOUT)
    finally:
        gate.release.set()
        if stopping is None:
            client.__exit__(None, None, None)

    assert read_card(db).items[0].title == "수정한 제목"
    assert titles_at_release == ["수정한 제목"]
    assert_lock_free(write_settings)
    # 종료 뒤 클라이언트 응답은 정하지 않는다(테스트 서버가 이미 닫혔다). 호출 스레드만 정리한다.
    done, _ = wait([sent], timeout=TIMEOUT)
    assert done == {sent}
