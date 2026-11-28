"""앱 시계와 시각 문자열 형식 함수 테스트 (스펙 3.2 "앱이 만드는 시각")."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from app.services.clock import AppClock, bump_after, format_app_timestamp, parse_app_timestamp


class _FakeNow:
    """테스트에서 바꿀 수 있는 가짜 현재 시각."""

    def __init__(self, value: datetime) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value


def test_now_before_anchor_raises_runtime_error():
    clock = AppClock(now_fn=lambda: datetime(2026, 11, 28, 12, 0, 0))

    with pytest.raises(RuntimeError):
        clock.now()


def test_now_adds_demo_offset_to_real_time():
    clock = AppClock(now_fn=lambda: datetime(2026, 11, 28, 23, 59, 50))
    clock.anchor(date(2026, 12, 5), date(2026, 11, 28))

    assert clock.now() == datetime(2026, 12, 5, 23, 59, 50)


def test_now_crosses_midnight_into_next_demo_day():
    fake_now = _FakeNow(datetime(2026, 11, 28, 23, 59, 50))
    clock = AppClock(now_fn=fake_now)
    clock.anchor(date(2026, 12, 5), date(2026, 11, 28))
    first = clock.now()

    fake_now.value = fake_now.value + timedelta(seconds=20)
    second = clock.now()

    assert second == datetime(2026, 12, 6, 0, 0, 10)
    assert second > first


def test_now_preserves_microseconds_of_real_time():
    clock = AppClock(now_fn=lambda: datetime(2026, 11, 28, 9, 30, 0, 123456))
    clock.anchor(date(2026, 12, 5), date(2026, 11, 28))

    assert clock.now() == datetime(2026, 12, 5, 9, 30, 0, 123456)


def test_now_supports_demo_date_before_today():
    clock = AppClock(now_fn=lambda: datetime(2026, 11, 28, 8, 0, 0))
    clock.anchor(date(2026, 11, 20), date(2026, 11, 28))

    assert clock.now() == datetime(2026, 11, 20, 8, 0, 0)


def test_anchor_called_twice_uses_last_offset():
    clock = AppClock(now_fn=lambda: datetime(2026, 11, 28, 10, 0, 0))
    clock.anchor(date(2026, 12, 5), date(2026, 11, 28))
    clock.anchor(date(2026, 12, 1), date(2026, 11, 28))

    assert clock.now() == datetime(2026, 12, 1, 10, 0, 0)


def test_now_reads_now_fn_on_every_call():
    calls: list[int] = []

    def now_fn() -> datetime:
        calls.append(1)
        return datetime(2026, 11, 28, 10, 0, 0)

    clock = AppClock(now_fn=now_fn)
    clock.anchor(date(2026, 12, 5), date(2026, 11, 28))
    clock.now()
    clock.now()

    assert len(calls) == 2


def test_now_has_no_timezone():
    clock = AppClock(now_fn=lambda: datetime(2026, 11, 28, 10, 0, 0))
    clock.anchor(date(2026, 12, 5), date(2026, 11, 28))

    assert clock.now().tzinfo is None


def test_default_now_fn_uses_real_clock():
    clock = AppClock()
    today = date.today()
    clock.anchor(today, today)

    before = datetime.now()
    value = clock.now()
    after = datetime.now()

    assert before <= value <= after


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (datetime(2026, 12, 5, 23, 59, 50), "2026-12-05T23:59:50.000000"),
        (datetime(2026, 12, 5, 7, 3, 9, 42), "2026-12-05T07:03:09.000042"),
        (datetime(2026, 12, 6, 0, 0, 10, 999999), "2026-12-06T00:00:10.999999"),
    ],
)
def test_format_app_timestamp_always_has_six_digit_microseconds(value, expected):
    formatted = format_app_timestamp(value)

    assert formatted == expected


@pytest.mark.parametrize(
    "value",
    [
        datetime(2026, 12, 5, 23, 59, 50),
        datetime(2026, 12, 5, 7, 3, 9, 42),
        datetime(2026, 12, 6, 0, 0, 10, 999999),
    ],
)
def test_parse_app_timestamp_round_trips_with_format(value):
    assert parse_app_timestamp(format_app_timestamp(value)) == value


def test_parse_app_timestamp_reads_stored_string():
    assert parse_app_timestamp("2026-12-05T23:59:50.000001") == datetime(2026, 12, 5, 23, 59, 50, 1)


def test_formatted_strings_sort_in_time_order():
    # 저장 문자열을 SQL에서 문자열로 정렬해도 시간 순서가 맞아야 한다.
    earlier = datetime(2026, 12, 5, 23, 59, 59, 999999)
    later = datetime(2026, 12, 6, 0, 0, 0)

    assert format_app_timestamp(earlier) < format_app_timestamp(later)


def test_bump_after_without_prior_returns_candidate():
    candidate = datetime(2026, 12, 5, 10, 0, 0)

    assert bump_after(candidate, None) == candidate


def test_bump_after_keeps_candidate_later_than_prior():
    candidate = datetime(2026, 12, 5, 10, 0, 1)
    prior = datetime(2026, 12, 5, 10, 0, 0)

    assert bump_after(candidate, prior) == candidate


@pytest.mark.parametrize(
    "candidate",
    [
        datetime(2026, 12, 5, 10, 0, 0),  # 같은 시각
        datetime(2026, 12, 5, 9, 59, 50),  # 시계가 10초 되돌아감
    ],
)
def test_bump_after_moves_past_prior_by_one_microsecond(candidate):
    prior = datetime(2026, 12, 5, 10, 0, 0)

    assert bump_after(candidate, prior) == datetime(2026, 12, 5, 10, 0, 0, 1)


def test_format_app_timestamp_rejects_aware_datetime():
    with pytest.raises(ValueError):
        format_app_timestamp(datetime(2026, 12, 5, 9, 0, tzinfo=UTC))
