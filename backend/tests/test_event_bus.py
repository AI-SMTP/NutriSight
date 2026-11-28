"""프로세스 안 이벤트 버스 동작 테스트 (스펙 3.7)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

import pytest

from app.events import SUBSCRIBER_QUEUE_SIZE, Event, EventBus, SubscriptionOverflowError

_WAIT_S = 2.0


def _event(index: int) -> Event:
    return Event(name="test.event", data={"index": index})


async def _bound_bus() -> EventBus:
    bus = EventBus()
    bus.bind_loop(asyncio.get_running_loop())
    return bus


async def _take(iterator: AsyncIterator[Event], count: int) -> list[Event]:
    received: list[Event] = []
    async with asyncio.timeout(_WAIT_S):
        async for event in iterator:
            received.append(event)
            if len(received) == count:
                break
    return received


async def _wait_until(predicate, timeout_s: float = _WAIT_S) -> None:
    async with asyncio.timeout(timeout_s):
        while not predicate():
            await asyncio.sleep(0)


def _records(caplog, level: int) -> list[logging.LogRecord]:
    return [
        record
        for record in caplog.records
        if record.name == "app.events.bus" and record.levelno == level
    ]


def test_queue_size_constant_is_100():
    assert SUBSCRIBER_QUEUE_SIZE == 100


def test_event_is_frozen():
    event = _event(1)
    with pytest.raises(AttributeError):
        event.name = "other"  # type: ignore[misc]


def test_event_data_is_read_only_copy():
    source = {"index": 1}
    event = Event(name="test.event", data=source)
    source["index"] = 2
    assert event.data["index"] == 1
    with pytest.raises(TypeError):
        event.data["index"] = 3  # type: ignore[index]
    assert event == Event(name="test.event", data={"index": 1})


async def test_subscribe_on_unbound_bus_raises():
    bus = EventBus()
    with pytest.raises(RuntimeError):
        async with bus.subscribe():
            pass


async def test_subscribe_from_other_loop_raises():
    other = asyncio.new_event_loop()
    try:
        bus = EventBus()
        bus.bind_loop(other)
        with pytest.raises(RuntimeError):
            async with bus.subscribe():
                pass
        assert bus.subscriber_count == 0
    finally:
        other.close()


async def test_subscriber_receives_events_in_publish_order():
    bus = await _bound_bus()
    async with bus.subscribe() as events:
        for index in range(5):
            bus.publish(_event(index))
        received = await _take(events, 5)
    assert [event.data["index"] for event in received] == [0, 1, 2, 3, 4]
    assert all(event.name == "test.event" for event in received)


async def test_publish_from_thread_pool_reaches_subscriber():
    # 디버그 모드 루프는 다른 스레드의 비스레드안전 호출(`call_soon`)을 `RuntimeError`로 막는다.
    asyncio.get_running_loop().set_debug(True)
    bus = await _bound_bus()
    async with bus.subscribe() as events:
        await asyncio.to_thread(bus.publish, _event(7))
        received = await _take(events, 1)
    assert received == [_event(7)]


async def test_every_subscriber_receives_each_event():
    bus = await _bound_bus()
    async with bus.subscribe() as first, bus.subscribe() as second:
        bus.publish(_event(1))
        assert await _take(first, 1) == [_event(1)]
        assert await _take(second, 1) == [_event(1)]


async def test_overflow_ends_only_slow_subscription(caplog):
    caplog.set_level(logging.WARNING, logger="app.events.bus")
    bus = await _bound_bus()
    total = SUBSCRIBER_QUEUE_SIZE + 1
    fast_received: list[Event] = []

    async def read_fast(iterator: AsyncIterator[Event]) -> None:
        async for event in iterator:
            fast_received.append(event)
            if len(fast_received) == total:
                return

    async with bus.subscribe() as slow, bus.subscribe() as fast:
        reader = asyncio.create_task(read_fast(fast))
        for index in range(total):
            bus.publish(_event(index))
            await _wait_until(lambda expected=index + 1: len(fast_received) == expected)
        async with asyncio.timeout(_WAIT_S):
            await reader

        slow_received: list[Event] = []
        with pytest.raises(SubscriptionOverflowError):
            async with asyncio.timeout(_WAIT_S):
                async for event in slow:
                    slow_received.append(event)

    assert [event.data["index"] for event in slow_received] == list(range(SUBSCRIBER_QUEUE_SIZE))
    assert [event.data["index"] for event in fast_received] == list(range(total))
    assert len(_records(caplog, logging.WARNING)) == 1

    async with bus.subscribe() as fresh:
        bus.publish(_event(999))
        assert await _take(fresh, 1) == [_event(999)]


async def test_overflowed_subscriber_is_detached_from_bus():
    bus = await _bound_bus()
    async with bus.subscribe() as slow:
        for index in range(SUBSCRIBER_QUEUE_SIZE + 1):
            bus.publish(_event(index))
        await _wait_until(lambda: bus.subscriber_count == 0)

        # 1건을 읽어 큐에 자리를 만든 뒤 발행해도, 떼어진 구독에는 더 쌓이지 않는다.
        received = await _take(slow, 1)
        bus.publish(_event(500))
        for _ in range(3):
            await asyncio.sleep(0)
        with pytest.raises(SubscriptionOverflowError):
            async with asyncio.timeout(_WAIT_S):
                async for event in slow:
                    received.append(event)
    assert 500 not in [event.data["index"] for event in received]
    assert len(received) == SUBSCRIBER_QUEUE_SIZE


async def test_subscription_exit_unsubscribes(caplog):
    caplog.set_level(logging.DEBUG, logger="app.events.bus")
    bus = await _bound_bus()
    async with bus.subscribe():
        pass
    # 구독이 끝난 뒤 큐를 넘기도록 발행해도 아무 일도 없다 (경고 없음, 예외 없음).
    for index in range(SUBSCRIBER_QUEUE_SIZE + 5):
        bus.publish(_event(index))
    await asyncio.sleep(0)
    assert bus.subscriber_count == 0
    assert _records(caplog, logging.WARNING) == []


def test_publish_before_bind_drops_with_debug_log(caplog):
    caplog.set_level(logging.DEBUG, logger="app.events.bus")
    bus = EventBus()
    bus.publish(_event(1))
    assert len(_records(caplog, logging.DEBUG)) == 1
    assert _records(caplog, logging.WARNING) == []


def test_publish_after_loop_closed_drops_with_debug_log(caplog):
    caplog.set_level(logging.DEBUG, logger="app.events.bus")
    loop = asyncio.new_event_loop()
    bus = EventBus()
    bus.bind_loop(loop)
    loop.close()
    bus.publish(_event(1))
    assert len(_records(caplog, logging.DEBUG)) == 1
    assert _records(caplog, logging.WARNING) == []
