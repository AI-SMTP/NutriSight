"""시연일 기준 앱 시계와 시각 문자열 형식 함수 (스펙 3.2 "앱이 만드는 시각").

앱이 저장하는 시각(`recommendations.created_at`·`updated_at`, `prescriptions.confirmed_at`)은
`실제 현재 시각 + 시연일 차이`다. 시연일 차이는 lifespan 시작 때 `anchor`로 한 번 고정하므로
앱이 자정을 넘겨 계속 돌면 시연일 다음 날짜로 넘어가며 시간 순서가 유지된다.
저장 문자열은 시간대 없는 `YYYY-MM-DDTHH:MM:SS.ffffff`이며, 문자열 정렬이 시간 순서와 같다.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timedelta

_ONE_MICROSECOND = timedelta(microseconds=1)


class AppClock:
    """실제 시각에 시연일 차이를 더해 돌려주는 시계. 고정 전에는 시각을 내주지 않는다."""

    def __init__(self, now_fn: Callable[[], datetime] = datetime.now) -> None:
        self._now_fn = now_fn
        self._offset: timedelta | None = None

    def anchor(self, demo_date: date, today: date) -> None:
        """시연일 차이(`demo_date - today`, 일 단위)를 고정한다. 다시 부르면 마지막 값을 쓴다."""
        self._offset = timedelta(days=(demo_date - today).days)

    def now(self) -> datetime:
        """시연일 차이를 더한 현재 시각(시간대 없음). `anchor` 전이면 `RuntimeError`."""
        if self._offset is None:
            raise RuntimeError(
                "AppClock.anchor()로 시연일 차이를 고정하기 전에는 시각을 쓸 수 없다"
            )
        return self._now_fn() + self._offset


def format_app_timestamp(dt: datetime) -> str:
    """저장용 문자열 `YYYY-MM-DDTHH:MM:SS.ffffff`로 바꾼다. 마이크로초가 0이어도 6자리를 쓴다.

    시간대 있는 값은 오프셋이 붙어 문자열 정렬 계약이 깨지므로 `ValueError`로 거부한다.
    """
    if dt.tzinfo is not None:
        raise ValueError(f"앱 시각은 시간대 없는 값이어야 한다: {dt!r}")
    return dt.isoformat(timespec="microseconds")


def parse_app_timestamp(raw: str) -> datetime:
    """`format_app_timestamp`가 만든 저장 문자열을 `datetime`으로 되돌린다."""
    return datetime.fromisoformat(raw)


def bump_after(candidate: datetime, prior: datetime | None) -> datetime:
    """단조 증가 보정. `candidate`가 `prior` 이하이면 `prior + 1µs`를 돌려준다."""
    if prior is None or candidate > prior:
        return candidate
    return prior + _ONE_MICROSECOND
