"""앱 lifespan의 런타임 단계(버스 루프 묶기·시계 고정)와 종료 정책 테스트 (스펙 3.2 종료 정책).

시드 DB(D=2026-12-05)를 `VAR_DIR`에 복사해 시작한다. 종료 순서를 한 루프 안에서 결정적으로
보기 위해 lifespan 컨텍스트(`app.router.lifespan_context`)를 테스트 루프에서 직접 돌린다.
재시작과 시계 확인은 실제 진입 경로인 `TestClient`로 한다. 기다림은 모두 `TIMEOUT` 상한을 둔다.
"""

from __future__ import annotations

import asyncio
import inspect
import shutil
import threading
from collections.abc import AsyncIterator, Awaitable
from contextlib import AbstractAsyncContextManager
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import wiring
from app.config import ConfigError, Settings, storage_paths
from app.main import create_app
from app.services.generation import create_recommendation
from app.services.ports import ModifiedBy, RecommendationItem
from app.services.runtime import RuntimeClosedError
from app.storage import recommendations as rec_store
from app.storage.app_lock import AppLock
from app.storage.errors import AppLockedError
from tests.app_lock import assert_lock_free, assert_lock_held
from tests.contracts.patient_data import build_items
from tests.services.cards import read_card
from tests.services.gates import ThreadGate
from tests.services.generation import (
    PATIENT,
    TIMEOUT,
    RecordingLocks,
    ScriptedGenerator,
    add_card,
    statuses,
    wait_set,
)
from tests.storage.demo import DEMO

CARD_ID = "rec_shutdown"
GATED = "gated"
# 시드 DB의 `seed_meta.demo_date`(DEMO)와 다른 설정 시연일. 시계가 DB 값을 쓰는지 가린다.
OTHER_DEMO_DATE = "2026-12-01"
# 고정 뒤 시계 날짜로 받는 값. 고정과 확인 사이에 실제 자정을 넘기면 다음 날이 된다.
DEMO_DAYS = {DEMO, DEMO + timedelta(days=1)}


@pytest.fixture
def app_db(monkeypatch: pytest.MonkeyPatch, isolated_var_dir: Path, seeded_db: Path) -> Path:
    """`DEMO_DATE`를 시연일로 고정하고 시드 DB를 `VAR_DIR/app.db`로 복사한다."""
    monkeypatch.setenv("DEMO_DATE", DEMO.isoformat())
    isolated_var_dir.mkdir()
    path = isolated_var_dir / "app.db"
    shutil.copyfile(seeded_db, path)
    return path


@pytest.fixture
def gated_generator(monkeypatch: pytest.MonkeyPatch) -> ScriptedGenerator:
    """풀지 않는 `asyncio.Event`에서 멈추는 생성기를 `RECOMMENDER=gated`로 등록한다."""
    generator = ScriptedGenerator(gate=asyncio.Event())
    monkeypatch.setitem(wiring.RECOMMENDATION_GENERATORS, GATED, lambda settings: generator)
    return generator


def _lifespan(app: FastAPI) -> AbstractAsyncContextManager[None]:
    return app.router.lifespan_context(app)


async def _start_fails(app: FastAPI) -> None:
    """시작만 한다. 시작이 실패해야 하는 테스트에서 `pytest.raises` 안에서 부른다."""
    await _lifespan(app).__aenter__()


class _Running:
    """`__aenter__`·`__aexit__`를 나눠 부르는 lifespan. 종료는 한 번만 한다."""

    def __init__(self, app: FastAPI) -> None:
        self._cm = _lifespan(app)
        self._started = False
        self._stopped = False

    async def start(self) -> None:
        await self._cm.__aenter__()
        self._started = True

    def stop(self) -> Awaitable[bool | None]:
        """종료 코루틴을 돌려준다. 부르는 순간 종료한 것으로 표시해 정리에서 다시 닫지 않는다."""
        if not self._started or self._stopped:
            return asyncio.sleep(0)
        self._stopped = True
        return self._cm.__aexit__(None, None, None)


@pytest.fixture
async def running() -> AsyncIterator[list[_Running]]:
    """테스트가 만든 `_Running`을 모은다. 테스트가 중간에 실패해도 닫지 않은 것을 닫는다."""
    started: list[_Running] = []
    yield started
    for item in started:
        await asyncio.wait_for(item.stop(), TIMEOUT * 2)


async def _start(app: FastAPI, running: list[_Running]) -> _Running:
    item = _Running(app)
    running.append(item)
    await item.start()
    return item


# ---- 시작: 시계 고정·버스 루프 ----


def test_clock_is_not_anchored_before_lifespan(app_db: Path) -> None:
    app = create_app(Settings())

    with pytest.raises(RuntimeError):
        app.state.runtime.clock.now()


def test_clock_is_anchored_to_demo_date_after_start(app_db: Path) -> None:
    app = create_app(Settings())

    with TestClient(app):
        assert app.state.runtime.clock.now().date() in DEMO_DAYS


def test_clock_uses_seed_meta_demo_date_not_setting(
    app_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEMO_DATE", OTHER_DEMO_DATE)
    app = create_app(Settings())

    with TestClient(app):
        assert app.state.runtime.clock.now().date() in DEMO_DAYS


async def test_bus_is_bound_to_running_loop_after_start(app_db: Path) -> None:
    app = create_app(Settings())

    async with _lifespan(app):
        async with app.state.event_bus.subscribe():
            assert app.state.event_bus.subscriber_count == 1


async def test_start_failure_after_lock_closes_runtime_and_releases_lock(
    isolated_var_dir: Path, db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 스키마만 있고 `seed_meta.demo_date`가 없는 DB: 저장소 준비는 통과하고 시계 고정에서 실패한다.
    monkeypatch.setenv("DEMO_DATE", DEMO.isoformat())
    isolated_var_dir.mkdir()
    shutil.copyfile(db_path, isolated_var_dir / "app.db")
    settings = Settings()
    app = create_app(settings)

    with pytest.raises(LookupError):
        await _start_fails(app)

    assert_lock_free(settings)
    assert app.state.runtime.closed
    coro = asyncio.sleep(0)
    with pytest.raises(RuntimeClosedError):
        app.state.runtime.tasks.spawn(coro)
    # 거부된 코루틴은 등록부가 닫는다("never awaited" 경고 없음).
    assert inspect.getcoroutinestate(coro) == inspect.CORO_CLOSED


# ---- 종료 (가): 진행 중인 생성 취소 ----


async def test_shutdown_cancels_waiting_generations_without_cards(
    app_db: Path, gated_generator: ScriptedGenerator, running: list[_Running]
) -> None:
    settings = Settings(recommender=GATED)
    app = create_app(settings)
    lifespan = await _start(app, running)
    locks = RecordingLocks()
    deps = replace(app.state.recommendation_deps, locks=locks)

    # 첫 생성은 생성기 대기, 둘째(같은 환자)는 환자별 잠금 대기 중이다.
    first = asyncio.create_task(create_recommendation(PATIENT, mode="manual", deps=deps))
    await wait_set(gated_generator.entered)
    second = asyncio.create_task(create_recommendation(PATIENT, mode="manual", deps=deps))
    await wait_set(locks.second_request)

    await asyncio.wait_for(lifespan.stop(), TIMEOUT)

    for caller in (first, second):
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(caller, TIMEOUT)
    assert app.state.runtime.tasks.tasks == frozenset()
    assert len(gated_generator.calls) == 1
    assert statuses(app_db, PATIENT) == {}
    assert_lock_free(settings)


# ---- 종료 (나): 실행 중인 쓰기가 끝난 뒤 잠금 해제 ----


async def test_shutdown_waits_running_port_write_before_releasing_lock(
    app_db: Path, monkeypatch: pytest.MonkeyPatch, running: list[_Running]
) -> None:
    add_card(app_db, CARD_ID)
    items: tuple[RecommendationItem, ...] = build_items("doc")
    gate = ThreadGate()
    gate.patch(monkeypatch, rec_store, "update_card_items")
    settings = Settings()
    app = create_app(settings)
    runtime = app.state.runtime

    # 쓰기 실행기 종료(3단계)에 들어온 순간을 알린다.
    shutdown_entered = threading.Event()
    real_shutdown = runtime.writer.shutdown

    def spying_shutdown() -> None:
        shutdown_entered.set()
        real_shutdown()

    monkeypatch.setattr(runtime.writer, "shutdown", spying_shutdown)

    # 잠금을 놓는 순간 카드가 이미 커밋돼 있었는지 기록한다. lifespan은 시작 때 잡은 잠금의
    # `release`를 정리 대상으로 묶으므로 시작 전에 바꾼다.
    items_at_release: list[tuple[RecommendationItem, ...]] = []
    real_release = AppLock.release

    def recording_release(self: AppLock) -> None:
        if self._fd is not None and self._path == storage_paths(settings).app_lock:
            items_at_release.append(read_card(app_db, CARD_ID).items)
        real_release(self)

    monkeypatch.setattr(AppLock, "release", recording_release)
    lifespan = await _start(app, running)
    caller = asyncio.create_task(
        app.state.patient_data.update_recommendation(CARD_ID, items, ModifiedBy.DOCTOR, None)
    )
    await gate.wait_entered()

    stopping = asyncio.ensure_future(lifespan.stop())
    assert await asyncio.to_thread(shutdown_entered.wait, TIMEOUT)

    assert_lock_held(settings)
    assert not stopping.done()
    assert read_card(app_db, CARD_ID).items != items

    gate.release.set()
    await asyncio.wait_for(stopping, TIMEOUT)

    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(caller, TIMEOUT)
    assert read_card(app_db, CARD_ID).items == items
    assert items_at_release == [items]
    assert_lock_free(settings)


# ---- 종료 (다): 같은 설정으로 다시 시작 ----


async def test_restart_with_same_settings_after_shutdown(
    app_db: Path, gated_generator: ScriptedGenerator, running: list[_Running]
) -> None:
    settings = Settings(recommender=GATED)
    first_app = create_app(settings)
    lifespan = await _start(first_app, running)
    pending = asyncio.create_task(
        create_recommendation(PATIENT, mode="manual", deps=first_app.state.recommendation_deps)
    )
    await wait_set(gated_generator.entered)
    await asyncio.wait_for(lifespan.stop(), TIMEOUT)
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(pending, TIMEOUT)

    second_app = create_app(settings)
    async with _lifespan(second_app):
        assert second_app.state.runtime is not first_app.state.runtime
        assert second_app.state.runtime.clock.now().date() in DEMO_DAYS
        assert_lock_held(settings)

    assert_lock_free(settings)


def test_restart_through_test_client(app_db: Path) -> None:
    settings = Settings()

    with TestClient(create_app(settings)) as client:
        assert client.get("/api/health").status_code == 200
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/health").status_code == 200

    assert_lock_free(settings)


# ---- 정리 실패·재진입 ----


@pytest.mark.parametrize(
    ("target", "attr"), [("tasks", "cancel_all"), ("writer", "shutdown")], ids=["tasks", "writer"]
)
async def test_lock_is_released_even_when_runtime_close_fails(
    app_db: Path, monkeypatch: pytest.MonkeyPatch, target: str, attr: str
) -> None:
    settings = Settings()
    app = create_app(settings)

    def broken() -> None:
        raise OSError("정리 실패")

    monkeypatch.setattr(getattr(app.state.runtime, target), attr, broken)

    with pytest.raises(OSError, match="정리 실패"):
        async with _lifespan(app):
            assert_lock_held(settings)

    assert_lock_free(settings)


async def test_entering_lifespan_twice_on_same_app_is_rejected(app_db: Path) -> None:
    settings = Settings()
    app = create_app(settings)
    async with _lifespan(app):
        assert not app.state.runtime.closed

    with pytest.raises(RuntimeError, match="앱 인스턴스는 한 번만 시작한다"):
        await _start_fails(app)

    assert_lock_free(settings)


async def test_app_can_restart_after_start_failed_before_lock(
    app_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 잠금을 잡기 전 실패(시연일 형식 오류·잠금 충돌)는 런타임을 닫지 않는다.
    monkeypatch.setenv("DEMO_DATE", "abc")
    bad_app = create_app(Settings())
    for _ in range(2):
        with pytest.raises(ConfigError):
            await _start_fails(bad_app)
    assert not bad_app.state.runtime.closed

    monkeypatch.setenv("DEMO_DATE", DEMO.isoformat())
    settings = Settings()
    app = create_app(settings)
    held = AppLock(storage_paths(settings).app_lock)
    held.acquire()
    try:
        with pytest.raises(AppLockedError):
            await _start_fails(app)
    finally:
        held.release()

    async with _lifespan(app):
        assert app.state.runtime.clock.now().date() in DEMO_DAYS
    assert app.state.runtime.closed
