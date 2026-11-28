"""`EventRecorder` 도우미 테스트: 구독이 열린 뒤에 블록에 들어오고, 쓰기 실행기가 발행한
이벤트를 받으며, 블록을 나가면 구독이 풀린다. `flush`는 앞선 이벤트를 모두 모으고, 구독이
넘쳐 끊기면 `wait_for`·`flush`·블록 종료가 원인이 보이는 오류를 낸다."""

from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.events.bus import SUBSCRIBER_QUEUE_SIZE, Event, SubscriptionOverflowError
from app.services.unit_of_work import WriteResult
from tests.support.events import EventRecorder, RecorderOverflowError

PING = "test.ping"


def _ping_write(conn: sqlite3.Connection) -> WriteResult[str]:
    """아무것도 쓰지 않고 이벤트 하나를 돌려주는 쓰기 서비스."""
    return WriteResult("ok", (Event(PING, {"n": 1}),))


def test_subscription_is_open_inside_block_and_closed_after(client: TestClient) -> None:
    bus = client.app.state.event_bus
    before = bus.subscriber_count

    with EventRecorder(client):
        assert bus.subscriber_count == before + 1

    assert bus.subscriber_count == before


def test_receives_event_published_by_writer(client: TestClient) -> None:
    with EventRecorder(client) as recorder:
        value = client.app.state.runtime.writer.run_sync(_ping_write)

        event = recorder.wait_for(PING)

    assert value == "ok"
    assert dict(event.data) == {"n": 1}
    assert recorder.names() == (PING,)


def test_receives_event_published_from_test_thread(client: TestClient) -> None:
    with EventRecorder(client) as recorder:
        client.app.state.event_bus.publish(Event("a", {}))
        client.app.state.event_bus.publish(Event("b", {}))

        recorder.wait_for("b")

    assert recorder.names() == ("a", "b")


def test_wait_for_times_out_without_matching_event(client: TestClient) -> None:
    with EventRecorder(client) as recorder, pytest.raises(TimeoutError):
        recorder.wait_for("never", timeout=0.05)


def test_requires_started_client(client: TestClient) -> None:
    with pytest.raises(RuntimeError):
        EventRecorder(TestClient(client.app))


def _flood(client: TestClient) -> None:
    """앱 루프의 한 차례 안에서 큐 크기보다 하나 많이 발행해 구독을 넘치게 한다.

    전달 콜백 101개가 소비자가 깨어나기 전에 모두 실행되므로 넘침이 결정적이다.
    """
    bus = client.app.state.event_bus

    def publish_all() -> None:
        for n in range(SUBSCRIBER_QUEUE_SIZE + 1):
            bus.publish(Event("flood", {"n": n}))

    client.portal.call(publish_all)


def test_flush_returns_events_published_before_without_sentinel(client: TestClient) -> None:
    with EventRecorder(client) as recorder:
        client.app.state.runtime.writer.run_sync(_ping_write)

        flushed = recorder.flush()

    assert [event.name for event in flushed] == [PING]
    assert recorder.names() == (PING,)


def test_flush_is_empty_without_events(client: TestClient) -> None:
    with EventRecorder(client) as recorder:
        assert recorder.flush() == ()


def test_wait_for_reports_overflow(client: TestClient) -> None:
    with pytest.raises(RecorderOverflowError) as caught:
        with EventRecorder(client) as recorder:
            _flood(client)
            recorder.wait_for("never")

    assert isinstance(caught.value.__cause__, SubscriptionOverflowError)


def test_flush_reports_overflow(client: TestClient) -> None:
    with pytest.raises(RecorderOverflowError):
        with EventRecorder(client) as recorder:
            _flood(client)
            recorder.flush()


def test_exit_reports_overflow(client: TestClient) -> None:
    bus = client.app.state.event_bus
    before = bus.subscriber_count

    with pytest.raises(RecorderOverflowError), EventRecorder(client):
        _flood(client)

    assert bus.subscriber_count == before
