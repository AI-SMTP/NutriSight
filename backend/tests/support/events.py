"""API 테스트가 버스 이벤트를 모으는 도우미 (계획 판단 6).

`TestClient`는 앱을 별도 스레드의 이벤트 루프에서 돌린다. `EventRecorder`는 `client.portal`로 그
루프에 구독 태스크를 띄워 받은 이벤트를 목록에 모은다. `portal.start_task`는 태스크가
`task_status.started()`를 부를 때까지 막히므로, `with` 블록에 들어온 시점에는 구독이 이미 열려
있다(그 뒤 발행한 이벤트는 놓치지 않는다). 기다림은 모두 `timeout` 상한을 둔다.

"이벤트 없음"은 `flush()`로 단언한다. 테스트 스레드에서 센티널을 발행하고 받을 때까지 기다리므로,
그 전에 발행된 이벤트는 모두 목록에 들어와 있다. 구독이 넘쳐 끊기면 `wait_for`·`flush`·블록
종료가 `RecorderOverflowError`를 낸다(원인 `SubscriptionOverflowError`는 `__cause__`).
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import Future
from types import TracebackType
from typing import Self
from uuid import uuid4

import anyio
from anyio.abc import TaskStatus
from fastapi.testclient import TestClient

from app.events.bus import Event, EventBus, SubscriptionOverflowError

DEFAULT_TIMEOUT_S = 5.0
_SENTINEL_PREFIX = "__event_recorder.flush."


class RecorderOverflowError(RuntimeError):
    """구독자 큐가 넘쳐 구독이 끊겼다. 그 뒤 이벤트는 기록되지 않았다."""


class EventRecorder:
    """`with EventRecorder(client) as recorder:` 블록 동안 앱 버스의 이벤트를 모은다.

    클라이언트는 `with TestClient(...)`로 시작된(lifespan이 버스 루프를 묶은) 상태여야 한다.
    블록 종료는 `flush`로 남은 이벤트와 넘침을 확인한 뒤 구독을 푼다.
    """

    def __init__(self, client: TestClient) -> None:
        if client.portal is None:
            raise RuntimeError(
                "EventRecorder는 시작된 TestClient(`with TestClient(...)`)가 필요하다"
            )
        self._portal = client.portal
        self._bus: EventBus = client.app.state.event_bus
        self._events: list[Event] = []
        self._overflow: SubscriptionOverflowError | None = None
        self._changed = threading.Condition()
        self._scope: anyio.CancelScope | None = None
        self._future: Future[None] | None = None

    def __enter__(self) -> Self:
        self._future, _ = self._portal.start_task(self._consume)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        try:
            if exc_type is None:
                self.flush()
        finally:
            if self._scope is not None:
                self._portal.call(self._scope.cancel)
            if self._future is not None:
                # 구독 블록을 나가 버스에서 떨어질 때까지 기다린다.
                self._future.result(timeout=DEFAULT_TIMEOUT_S)

    async def _consume(self, *, task_status: TaskStatus[None] = anyio.TASK_STATUS_IGNORED) -> None:
        with anyio.CancelScope() as scope:
            self._scope = scope
            async with self._bus.subscribe() as events:
                task_status.started()
                try:
                    async for event in events:
                        with self._changed:
                            self._events.append(event)
                            self._changed.notify_all()
                except SubscriptionOverflowError as err:
                    with self._changed:
                        self._overflow = err
                        self._changed.notify_all()

    @property
    def events(self) -> tuple[Event, ...]:
        """지금까지 받은 이벤트(센티널 제외), 받은 순서."""
        with self._changed:
            return tuple(e for e in self._events if not e.name.startswith(_SENTINEL_PREFIX))

    def names(self) -> tuple[str, ...]:
        """지금까지 받은 이벤트 이름, 받은 순서."""
        return tuple(event.name for event in self.events)

    def wait_for(self, name: str, *, timeout: float = DEFAULT_TIMEOUT_S) -> Event:
        """이름이 `name`인 첫 이벤트를 기다려 돌려준다.

        `timeout` 안에 없으면 `TimeoutError`, 그 전에 구독이 넘쳐 끊기면 `RecorderOverflowError`.
        """
        found = self._wait(lambda: self._first(name), timeout)
        if found is None:
            raise TimeoutError(f"{timeout}초 안에 이벤트를 받지 못했다: {name}")
        return found

    def flush(self, *, timeout: float = DEFAULT_TIMEOUT_S) -> tuple[Event, ...]:
        """센티널을 발행해 받을 때까지 기다린 뒤, 센티널을 뺀 받은 이벤트 전체를 돌려준다.

        센티널보다 먼저 발행된 이벤트는 모두 들어 있다. 실패는 `wait_for`와 같다.
        """
        sentinel = f"{_SENTINEL_PREFIX}{uuid4().hex}"
        self._bus.publish(Event(sentinel, {}))
        if self._wait(lambda: self._first(sentinel), timeout) is None:
            raise TimeoutError(f"{timeout}초 안에 flush 센티널을 받지 못했다")
        return self.events

    def _first(self, name: str) -> Event | None:
        # `_changed`를 쥔 상태에서만 부른다.
        return next((event for event in self._events if event.name == name), None)

    def _wait(self, find: Callable[[], Event | None], timeout: float) -> Event | None:
        """`find`가 이벤트를 찾거나 구독이 넘치거나 `timeout`이 지날 때까지 기다린다."""
        with self._changed:
            self._changed.wait_for(lambda: find() is not None or self._overflow, timeout=timeout)
            found = find()
            overflow = self._overflow
        if found is None and overflow is not None:
            raise RecorderOverflowError("구독자 큐가 넘쳐 구독이 끊겼다") from overflow
        return found
