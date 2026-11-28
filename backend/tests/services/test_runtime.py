"""앱 런타임 테스트: 태스크 등록부·쓰기 실행기·`AppRuntime` (스펙 3.2 "앱 런타임").

스레드·취소 시나리오는 `threading.Event`로 작업을 멈추고 풀어 결정적으로 만든다. 기다림은 모두
`TIMEOUT` 상한을 두며, 실제 시간 경과(sleep)에 결과가 기대지 않는다.
"""

from __future__ import annotations

import asyncio
import inspect
import sqlite3
import threading
from collections.abc import AsyncIterator, Callable, Coroutine, Iterator
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pytest

from app.events.bus import Event, EventBus
from app.services.clock import AppClock
from app.services.runtime import AppRuntime, RuntimeClosedError, TaskRegistry, WriteExecutor
from app.services.unit_of_work import WriteResult
from app.storage.db import connect

TIMEOUT = 5.0


def _meta_keys(db_path: Path) -> list[str]:
    with connect(db_path) as conn:
        return [row["key"] for row in conn.execute("SELECT key FROM seed_meta ORDER BY key")]


def _insert(conn: sqlite3.Connection, key: str) -> None:
    conn.execute("INSERT INTO seed_meta (key, value) VALUES (?, 'v')", (key,))


class _RecordingBus(EventBus):
    """발행 순간의 스레드와 그때 다른 연결에서 보이는 커밋 상태를 기록한다."""

    def __init__(self, db_path: Path) -> None:
        super().__init__()
        self._db_path = db_path
        self.published: list[tuple[str, list[str], int]] = []

    def publish(self, event: Event) -> None:
        self.published.append((event.name, _meta_keys(self._db_path), threading.get_ident()))
        super().publish(event)


@pytest.fixture
def bus(db_path: Path) -> _RecordingBus:
    return _RecordingBus(db_path)


@pytest.fixture
def writer(db_path: Path, bus: _RecordingBus) -> Iterator[WriteExecutor]:
    executor = WriteExecutor(db_path, bus)
    yield executor
    executor.shutdown()


async def _next(events: AsyncIterator[Event]) -> Event:
    return await asyncio.wait_for(anext(events), TIMEOUT)


def _bind(bus: EventBus) -> None:
    bus.bind_loop(asyncio.get_running_loop())


async def _noop() -> None:
    return None


def _assert_closed(coro: Coroutine[Any, Any, Any]) -> None:
    assert inspect.getcoroutinestate(coro) == inspect.CORO_CLOSED


# --- TaskRegistry -------------------------------------------------------------------------------


async def test_spawn_keeps_task_until_done() -> None:
    registry = TaskRegistry()
    gate = asyncio.Event()

    async def work() -> int:
        await gate.wait()
        return 7

    task = registry.spawn(work())

    assert isinstance(task, asyncio.Task)
    assert task in registry.tasks
    gate.set()
    assert await task == 7
    await asyncio.sleep(0)
    assert registry.tasks == frozenset()


async def test_spawn_removes_task_that_failed() -> None:
    registry = TaskRegistry()

    async def fail() -> None:
        raise ValueError("실패")

    task = registry.spawn(fail())
    with pytest.raises(ValueError):
        await task
    await asyncio.sleep(0)

    assert registry.tasks == frozenset()


async def test_spawn_after_close_raises_and_closes_coroutine() -> None:
    registry = TaskRegistry()
    registry.close()

    coro = _noop()
    with pytest.raises(RuntimeClosedError):
        registry.spawn(coro)

    _assert_closed(coro)
    assert registry.tasks == frozenset()


async def test_cancel_all_cancels_pending_tasks_and_waits_for_cleanup() -> None:
    registry = TaskRegistry()
    cleaned: list[str] = []

    async def forever(name: str) -> None:
        try:
            await asyncio.Event().wait()
        finally:
            # 정리에 루프 차례가 몇 번 필요해도 cancel_all이 끝까지 기다려야 한다.
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            cleaned.append(name)

    first = registry.spawn(forever("a"))
    second = registry.spawn(forever("b"))
    await asyncio.sleep(0)

    await asyncio.wait_for(registry.cancel_all(), TIMEOUT)

    assert first.cancelled() and second.cancelled()
    assert sorted(cleaned) == ["a", "b"]
    assert registry.tasks == frozenset()


async def test_cancel_all_with_no_tasks_returns() -> None:
    registry = TaskRegistry()

    await asyncio.wait_for(registry.cancel_all(), TIMEOUT)

    assert registry.tasks == frozenset()


async def test_cancel_all_closes_registry() -> None:
    registry = TaskRegistry()

    await asyncio.wait_for(registry.cancel_all(), TIMEOUT)

    coro = _noop()
    with pytest.raises(RuntimeClosedError):
        registry.spawn(coro)
    _assert_closed(coro)


def test_spawn_without_running_loop_raises_and_closes_coroutine() -> None:
    registry = TaskRegistry()

    coro = _noop()
    with pytest.raises(RuntimeError):
        registry.spawn(coro)

    _assert_closed(coro)
    assert registry.tasks == frozenset()


# --- WriteExecutor ------------------------------------------------------------------------------


async def test_run_write_publishes_events_after_commit_and_returns_value(
    db_path: Path, bus: _RecordingBus, writer: WriteExecutor
) -> None:
    _bind(bus)

    def fn(conn: sqlite3.Connection) -> WriteResult[str]:
        _insert(conn, "a")
        return WriteResult("ok", (Event("first", {"n": 1}), Event("second", {"n": 2})))

    async with bus.subscribe() as events:
        value = await writer.run_write(fn)

        assert value == "ok"
        assert [(await _next(events)).name for _ in range(2)] == ["first", "second"]

    # 발행 순간 다른 연결에서 이미 커밋된 행이 보인다 = 커밋 뒤에 발행했다.
    assert [(name, keys) for name, keys, _ in bus.published] == [
        ("first", ["a"]),
        ("second", ["a"]),
    ]


async def test_run_write_runs_on_one_dedicated_thread_and_publishes_there(
    bus: _RecordingBus, writer: WriteExecutor
) -> None:
    _bind(bus)
    threads: list[int] = []

    def fn(conn: sqlite3.Connection) -> WriteResult[None]:
        threads.append(threading.get_ident())
        return WriteResult(None, (Event("e", {}),))

    await writer.run_write(fn)
    await writer.run_write(fn)
    await asyncio.to_thread(writer.run_sync, fn)

    caller = threading.get_ident()
    assert len(set(threads)) == 1
    assert threads[0] != caller
    assert {thread for _, _, thread in bus.published} == {threads[0]}


async def test_run_write_error_leaves_db_unchanged_and_publishes_nothing(
    db_path: Path, bus: _RecordingBus, writer: WriteExecutor
) -> None:
    _bind(bus)

    def failing(conn: sqlite3.Connection) -> WriteResult[None]:
        _insert(conn, "a")
        raise RuntimeError("저장 실패")

    def succeeding(conn: sqlite3.Connection) -> WriteResult[None]:
        return WriteResult(None, (Event("after", {}),))

    async with bus.subscribe() as events:
        with pytest.raises(RuntimeError, match="저장 실패"):
            await writer.run_write(failing)
        await writer.run_write(succeeding)

        # 실패한 작업의 이벤트가 있었다면 "after"보다 먼저 도착했을 것이다.
        assert (await _next(events)).name == "after"

    assert _meta_keys(db_path) == []
    assert [name for name, _, _ in bus.published] == ["after"]


async def test_run_sync_returns_value_and_propagates_error(
    db_path: Path, writer: WriteExecutor
) -> None:
    def fn(conn: sqlite3.Connection) -> WriteResult[int]:
        _insert(conn, "a")
        return WriteResult(3)

    def failing(conn: sqlite3.Connection) -> WriteResult[int]:
        raise LookupError("없음")

    assert await asyncio.to_thread(writer.run_sync, fn) == 3
    with pytest.raises(LookupError):
        await asyncio.to_thread(writer.run_sync, failing)
    assert _meta_keys(db_path) == ["a"]


class _Gate:
    """쓰기 실행기 스레드 안에서 작업을 멈춰 두고 테스트가 푸는 문."""

    def __init__(self) -> None:
        self._started = threading.Event()
        self._released = threading.Event()

    def blocking_write(
        self, key: str, event_name: str
    ) -> Callable[[sqlite3.Connection], WriteResult[str]]:
        """행을 넣고 멈춘 뒤, 풀리면 `key`와 이벤트 `event_name`을 돌려주는 쓰기 함수."""

        def fn(conn: sqlite3.Connection) -> WriteResult[str]:
            _insert(conn, key)
            self._started.set()
            if not self._released.wait(TIMEOUT):
                raise TimeoutError("테스트가 작업을 풀지 않았다")
            return WriteResult(key, (Event(event_name, {"key": key}),))

        return fn

    async def wait_started(self) -> None:
        assert await asyncio.to_thread(self._started.wait, TIMEOUT)

    def release(self) -> None:
        self._released.set()


@dataclass(frozen=True)
class _RunningAndQueued:
    """멈춘 쓰기 하나(`running`)와 그 뒤 대기열에 들어간 쓰기 하나(`pending`)."""

    gate: _Gate
    running: asyncio.Task[str]
    pending: asyncio.Task[None]
    queued_ran: threading.Event


async def _start_running_and_queued(writer: WriteExecutor) -> _RunningAndQueued:
    gate = _Gate()
    queued_ran = threading.Event()

    def queued(conn: sqlite3.Connection) -> WriteResult[None]:
        queued_ran.set()
        _insert(conn, "queued")
        return WriteResult(None, (Event("queued", {}),))

    running = asyncio.create_task(writer.run_write(gate.blocking_write("a", "running")))
    await gate.wait_started()
    pending = asyncio.create_task(writer.run_write(queued))
    await asyncio.sleep(0)  # pending이 실행기 대기열에 작업을 넣을 차례
    return _RunningAndQueued(gate, running, pending, queued_ran)


async def test_cancelled_caller_does_not_stop_running_write(
    db_path: Path, bus: _RecordingBus, writer: WriteExecutor
) -> None:
    _bind(bus)
    gate = _Gate()

    async with bus.subscribe() as events:
        task = asyncio.create_task(writer.run_write(gate.blocking_write("a", "done")))
        await gate.wait_started()

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert _meta_keys(db_path) == []

        gate.release()
        event = await _next(events)

    assert event.name == "done"
    assert _meta_keys(db_path) == ["a"]


async def test_abandoned_sync_caller_does_not_stop_running_write(
    db_path: Path, bus: _RecordingBus, writer: WriteExecutor
) -> None:
    _bind(bus)
    gate = _Gate()
    outcomes: list[BaseException] = []

    def caller() -> None:
        try:
            writer.run_sync(gate.blocking_write("a", "done"), timeout=0.01)
        except TimeoutError as err:
            outcomes.append(err)

    async with bus.subscribe() as events:
        thread = threading.Thread(target=caller)
        thread.start()
        await gate.wait_started()
        await asyncio.to_thread(thread.join, TIMEOUT)
        assert not thread.is_alive()
        assert len(outcomes) == 1
        assert _meta_keys(db_path) == []

        gate.release()
        event = await _next(events)

    assert event.name == "done"
    assert _meta_keys(db_path) == ["a"]


async def test_shutdown_waits_for_running_write_and_drops_queued_ones(
    db_path: Path, bus: _RecordingBus, writer: WriteExecutor
) -> None:
    _bind(bus)

    async with bus.subscribe() as events:
        scenario = await _start_running_and_queued(writer)

        stopper = threading.Thread(target=writer.shutdown)
        stopper.start()

        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(scenario.pending, TIMEOUT)
        # 실행 중인 작업이 멈춰 있는 동안 shutdown은 돌아오지 않는다.
        assert stopper.is_alive()

        scenario.gate.release()
        await asyncio.to_thread(stopper.join, TIMEOUT)
        assert not stopper.is_alive()
        assert await asyncio.wait_for(scenario.running, TIMEOUT) == "a"
        event = await _next(events)

    assert event.name == "running"
    assert not scenario.queued_ran.is_set()
    assert _meta_keys(db_path) == ["a"]
    assert [name for name, _, _ in bus.published] == ["running"]


async def test_cancelled_caller_drops_queued_write(
    db_path: Path, bus: _RecordingBus, writer: WriteExecutor
) -> None:
    _bind(bus)

    async with bus.subscribe() as events:
        scenario = await _start_running_and_queued(writer)

        scenario.pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await scenario.pending

        scenario.gate.release()
        assert await asyncio.wait_for(scenario.running, TIMEOUT) == "a"
        assert (await _next(events)).name == "running"
        # 실행기는 스레드 하나라 이 작업이 끝났다면 앞의 대기열 작업은 이미 처리(또는 취소)됐다.
        await writer.run_write(lambda conn: WriteResult(None))

    assert not scenario.queued_ran.is_set()
    assert _meta_keys(db_path) == ["a"]
    assert [name for name, _, _ in bus.published] == ["running"]


def test_write_after_shutdown_is_rejected(db_path: Path, bus: _RecordingBus) -> None:
    executor = WriteExecutor(db_path, bus)
    executor.shutdown()

    with pytest.raises(RuntimeError):
        executor.run_sync(lambda conn: WriteResult(None))
    assert _meta_keys(db_path) == []


# --- AppRuntime ---------------------------------------------------------------------------------


def test_create_builds_unanchored_runtime_without_touching_db(tmp_path: Path) -> None:
    path = tmp_path / "app.db"

    runtime = AppRuntime.create(path, now_fn=lambda: datetime(2026, 11, 28, 9, 0))
    try:
        assert isinstance(runtime.bus, EventBus)
        assert isinstance(runtime.tasks, TaskRegistry)
        assert isinstance(runtime.writer, WriteExecutor)
        assert isinstance(runtime.clock, AppClock)
        assert not path.exists()
        with pytest.raises(RuntimeError):
            runtime.clock.now()

        runtime.clock.anchor(date(2026, 12, 5), date(2026, 11, 28))
        assert runtime.clock.now() == datetime(2026, 12, 5, 9, 0)
        with pytest.raises(AttributeError):
            runtime.bus = EventBus()  # type: ignore[misc]
    finally:
        runtime.writer.shutdown()


async def test_create_wires_writer_to_db_path_and_runtime_bus(db_path: Path) -> None:
    runtime = AppRuntime.create(db_path)
    runtime.bus.bind_loop(asyncio.get_running_loop())
    try:
        async with runtime.bus.subscribe() as events:
            await runtime.writer.run_write(
                lambda conn: WriteResult(_insert(conn, "a"), (Event("saved", {}),))
            )
            assert (await _next(events)).name == "saved"
        assert _meta_keys(db_path) == ["a"]
    finally:
        runtime.writer.shutdown()


def test_create_defaults_now_fn_to_real_clock(tmp_path: Path) -> None:
    runtime = AppRuntime.create(tmp_path / "app.db")
    try:
        today = date.today()
        runtime.clock.anchor(today, today)
        assert runtime.clock.now().date() in {today, date.fromordinal(today.toordinal() + 1)}
    finally:
        runtime.writer.shutdown()
