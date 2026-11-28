"""프로세스 안 이벤트 버스 (스펙 3.7).

`publish`는 어느 스레드에서나 막히지 않고 부를 수 있다. 이벤트는 `bind_loop`로 묶은 루프에
`call_soon_threadsafe`로 넘겨 그 루프 스레드에서 구독자 큐에 넣는다. 구독자 큐가 가득 차면
그 구독만 버스에서 떼고, 반복자는 남은 이벤트를 다 낸 뒤 `SubscriptionOverflowError`를 던진다.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from types import MappingProxyType

logger = logging.getLogger(__name__)

SUBSCRIBER_QUEUE_SIZE = 100


@dataclass(frozen=True)
class Event:
    """버스로 흐르는 이벤트. `name` 예: `"recommendation.updated"`."""

    name: str
    data: Mapping[str, object]

    def __post_init__(self) -> None:
        # 발행 뒤 원본 dict를 바꿔도 구독자가 보는 값이 바뀌지 않도록 읽기 전용 복사본으로 둔다.
        object.__setattr__(self, "data", MappingProxyType(dict(self.data)))


class SubscriptionOverflowError(Exception):
    """구독자 큐가 가득 차 구독이 끝났음을 알린다. 받은 쪽은 다시 구독해 상태를 다시 읽는다."""


class _Subscriber:
    """구독 하나의 큐와 넘침 표식. 루프 스레드에서만 다룬다."""

    def __init__(self) -> None:
        self.queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=SUBSCRIBER_QUEUE_SIZE)
        self.overflowed = False

    async def events(self) -> AsyncIterator[Event]:
        while True:
            # 넘침은 큐가 가득 찼을 때만 생기므로, 큐를 비운 뒤에 표식을 보면 충분하다.
            if self.overflowed and self.queue.empty():
                raise SubscriptionOverflowError("구독자 큐가 가득 차 구독이 끝났다")
            yield await self.queue.get()


class EventBus:
    """구독자마다 크기 `SUBSCRIBER_QUEUE_SIZE`인 큐를 두는 발행·구독 버스."""

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._subscribers: set[_Subscriber] = set()

    @property
    def subscriber_count(self) -> int:
        """현재 붙어 있는 구독 수."""
        return len(self._subscribers)

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """이벤트를 전달할 루프를 묶는다. lifespan 시작 때 실행 중인 루프로 부른다."""
        self._loop = loop

    def publish(self, event: Event) -> None:
        """이벤트를 발행한다. 막히지 않으며 발행 실패로 예외를 올리지 않는다.

        루프를 묶기 전이나 루프가 닫힌 뒤에는 구독자가 있을 수 없으므로 DEBUG 로그만 남기고 버린다.
        """
        loop = self._loop
        if loop is None:
            logger.debug("묶인 루프가 없어 이벤트를 버린다: %s", event.name)
            return
        try:
            loop.call_soon_threadsafe(self._deliver, event)
        except RuntimeError:
            logger.debug("루프가 닫혀 이벤트를 버린다: %s", event.name)

    @asynccontextmanager
    async def subscribe(self) -> AsyncIterator[AsyncIterator[Event]]:
        """구독을 연다. 블록 안에서 받은 반복자로 이벤트를 읽고, 블록을 나가면 구독을 푼다.

        - 묶인 루프 안에서만 부른다. 묶이지 않았거나 다른 루프에서 부르면 `RuntimeError`다.
        - 반복자는 블록 안에서 한 번만 소비한다.
        - 구독 직전 같은 틱에 발행된 이벤트는 받을 수 있다(전달이 루프의 다음 차례에 일어난다).
        """
        if self._loop is None or asyncio.get_running_loop() is not self._loop:
            raise RuntimeError("이벤트 버스를 묶은 루프 안에서만 구독할 수 있다")
        subscriber = _Subscriber()
        self._subscribers.add(subscriber)
        try:
            yield subscriber.events()
        finally:
            self._subscribers.discard(subscriber)

    def _deliver(self, event: Event) -> None:
        # 루프 스레드에서만 실행된다. 순회 중 집합을 바꾸지 않도록 복사본을 돈다.
        for subscriber in tuple(self._subscribers):
            try:
                subscriber.queue.put_nowait(event)
            except asyncio.QueueFull:
                self._subscribers.discard(subscriber)
                subscriber.overflowed = True
                logger.warning(
                    "구독자 큐(%d)가 가득 차 구독을 끊는다: %s", SUBSCRIBER_QUEUE_SIZE, event.name
                )
