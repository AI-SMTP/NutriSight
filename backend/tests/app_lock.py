"""앱 잠금(`var/app.lock`) 상태를 확인하는 테스트 도우미."""

from __future__ import annotations

import pytest

from app.config import Settings, storage_paths
from app.storage.app_lock import AppLock
from app.storage.errors import AppLockedError


def assert_lock_free(settings: Settings) -> None:
    """다른 인스턴스로 잠금을 잡았다 놓을 수 있다(아무도 쥐고 있지 않다)."""
    lock = AppLock(storage_paths(settings).app_lock)
    lock.acquire()
    lock.release()


def assert_lock_held(settings: Settings) -> None:
    """다른 인스턴스의 잠금 시도가 `AppLockedError`로 실패한다(누군가 쥐고 있다)."""
    other = AppLock(storage_paths(settings).app_lock)
    try:
        with pytest.raises(AppLockedError):
            other.acquire()
    finally:
        other.release()  # 잡혔다면(검사 실패) 다음 단계를 막지 않게 놓는다
