"""앱 런타임: 태스크 등록부·쓰기 실행기·`AppRuntime` (스펙 3.2 "앱 런타임").

- `TaskRegistry`는 백그라운드 태스크의 강한 참조를 들고 있다가 끝나면 놓는다. 종료 때
  `close()` → `cancel_all()`로 새 태스크를 막고 남은 태스크를 취소한다.
- `WriteExecutor`는 모든 DB 쓰기를 스레드 하나에서 실행한다. 작업 하나는 "커밋 → 이벤트 발행"
  까지이므로, 호출한 코루틴·스레드가 결과를 받기 전에 사라져도 커밋된 쓰기는 발행까지 끝낸다.
- `AppRuntime`은 버스·태스크 등록부·쓰기 실행기·앱 시계를 묶어 포트와 추천 의존성에 함께 넘긴다.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from collections.abc import Callable, Coroutine
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import Any

from app.events.bus import EventBus
from app.services.clock import AppClock
from app.services.unit_of_work import WriteResult, run_in_db

logger = logging.getLogger(__name__)

_WRITER_THREAD_PREFIX = "db-writer"


class RuntimeClosedError(RuntimeError):
    """종료가 시작된 런타임에 새 태스크를 만들려 했다."""


class TaskRegistry:
    """백그라운드 태스크 집합. 이벤트 루프 스레드에서만 다룬다."""

    def __init__(self) -> None:
        self._tasks: set[asyncio.Task[Any]] = set()
        self._closed = False

    @property
    def tasks(self) -> frozenset[asyncio.Task[Any]]:
        """아직 끝나지 않은 태스크들(복사본)."""
        return frozenset(self._tasks)

    def spawn[T](self, coro: Coroutine[Any, Any, T]) -> asyncio.Task[T]:
        """태스크를 만들어 끝날 때까지 강한 참조를 둔다. `close()` 뒤면 `RuntimeClosedError`."""
        try:
            if self._closed:
                raise RuntimeClosedError("런타임이 종료 중이라 새 태스크를 만들 수 없다")
            task = asyncio.get_running_loop().create_task(coro)
        except BaseException:
            # 태스크가 되지 못한 코루틴이 "never awaited" 경고를 남기지 않게 닫는다.
            coro.close()
            raise
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def run_shielded[T](self, coro: Coroutine[Any, Any, T], *, label: str) -> T:
        """`coro`를 앱 소유 태스크로 돌리고 결과를 기다린다. 호출자가 취소돼도 태스크는 계속 돈다.

        호출자가 취소되면 태스크에 완료 콜백을 붙여, 태스크가 예외로 끝났을 때 `label`과 함께
        ERROR 로그를 남긴다(예외도 회수한다). 태스크 자체가 취소되면 로그를 남기지 않는다.
        `close()` 뒤면 `RuntimeClosedError`.
        """
        task = self.spawn(coro)
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            task.add_done_callback(partial(_log_orphan_failure, label))
            raise

    def close(self) -> None:
        """새 태스크를 받지 않는다."""
        self._closed = True

    async def cancel_all(self) -> None:
        """새 태스크를 막고 남은 태스크를 모두 취소한 뒤 정리가 끝날 때까지 기다린다.

        태스크 예외는 올리지 않는다.
        """
        self.close()
        pending = tuple(self._tasks)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)


def _log_orphan_failure(label: str, task: asyncio.Task[Any]) -> None:
    """호출자가 떠난 태스크가 예외로 끝났으면 ERROR 로그를 남긴다(예외도 회수한다)."""
    if task.cancelled():
        return
    err = task.exception()
    if err is not None:
        logger.error("호출자가 취소된 뒤 앱 소유 태스크가 실패했다: %s", label, exc_info=err)


class WriteExecutor:
    """`ThreadPoolExecutor(max_workers=1)`로 DB 쓰기를 직렬 실행하고 커밋 뒤 이벤트를 발행한다."""

    def __init__(self, db_path: Path, bus: EventBus) -> None:
        self._db_path = db_path
        self._bus = bus
        # 스레드는 첫 작업 때 만들어지므로 생성만으로는 DB·스레드를 건드리지 않는다.
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=_WRITER_THREAD_PREFIX)

    @property
    def db_path(self) -> Path:
        """쓰기가 연결하는 DB 경로(읽기 전용)."""
        return self._db_path

    def _job[T](self, fn: Callable[[sqlite3.Connection], WriteResult[T]]) -> T:
        # 실행기 스레드에서 돈다. 커밋(run_in_db 블록 종료)이 끝난 뒤에만 발행한다.
        result = run_in_db(self._db_path, fn, mode="write")
        # publish는 계약상 예외를 던지지 않으므로, 커밋된 쓰기의 결과 반환을 막지 않는다.
        for event in result.events:
            self._bus.publish(event)
        return result.value

    async def run_write[T](self, fn: Callable[[sqlite3.Connection], WriteResult[T]]) -> T:
        """비동기 경로의 쓰기. 기다리던 코루틴이 취소돼도 이미 시작한 작업은 끝까지 돈다.

        대기열에 있어 아직 시작하지 않은 쓰기는 기다리던 코루틴이 취소되면 함께 취소된다.
        호출자 취소 보호는 `TaskRegistry.run_shielded`가 맡는다(스펙 3.2).
        """
        return await asyncio.wrap_future(self._executor.submit(self._job, fn))

    def run_sync[T](
        self,
        fn: Callable[[sqlite3.Connection], WriteResult[T]],
        *,
        timeout: float | None = None,
    ) -> T:
        """동기 경로의 쓰기. `timeout`(초)이 지나면 `TimeoutError`를 올리지만 작업은 계속 돈다."""
        return self._executor.submit(self._job, fn).result(timeout=timeout)

    def shutdown(self) -> None:
        """실행 중인 작업(커밋·발행)이 끝나기를 기다리고, 아직 시작하지 않은 작업은 버린다."""
        self._executor.shutdown(wait=True, cancel_futures=True)


@dataclass(frozen=True)
class AppRuntime:
    """앱 하나가 공유하는 버스·태스크 등록부·쓰기 실행기·앱 시계."""

    bus: EventBus
    tasks: TaskRegistry
    writer: WriteExecutor
    clock: AppClock

    @classmethod
    def create(cls, db_path: Path, *, now_fn: Callable[[], datetime] = datetime.now) -> AppRuntime:
        """런타임을 만든다. 시계는 시연일 차이가 고정되지 않은 상태다(lifespan이 `anchor`)."""
        bus = EventBus()
        return cls(
            bus=bus,
            tasks=TaskRegistry(),
            writer=WriteExecutor(db_path, bus),
            clock=AppClock(now_fn=now_fn),
        )
