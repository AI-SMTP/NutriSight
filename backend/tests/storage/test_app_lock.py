"""앱 잠금(`var/app.lock`) 테스트 (스펙 3.8)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.storage import app_lock
from app.storage.app_lock import AppLock
from app.storage.errors import AppLockedError


def test_second_lock_on_same_path_raises_while_held(tmp_path: Path) -> None:
    lock_path = tmp_path / "app.lock"
    with AppLock(lock_path), pytest.raises(AppLockedError):
        AppLock(lock_path).acquire()


def test_lock_can_be_reacquired_after_block_ends(tmp_path: Path) -> None:
    lock_path = tmp_path / "app.lock"
    with AppLock(lock_path):
        pass
    with AppLock(lock_path):
        pass


def test_lock_released_when_exception_leaves_block(tmp_path: Path) -> None:
    lock_path = tmp_path / "app.lock"
    with pytest.raises(ValueError, match="실패"), AppLock(lock_path):
        raise ValueError("실패")
    with AppLock(lock_path):
        pass


def test_acquire_creates_missing_parent_dir(tmp_path: Path) -> None:
    lock_path = tmp_path / "var" / "nested" / "app.lock"
    with AppLock(lock_path):
        assert lock_path.exists()


def test_release_is_idempotent(tmp_path: Path) -> None:
    lock = AppLock(tmp_path / "app.lock")
    lock.acquire()
    lock.release()
    lock.release()


def test_release_without_acquire_is_noop(tmp_path: Path) -> None:
    AppLock(tmp_path / "app.lock").release()


def test_failed_acquire_does_not_hold_lock(tmp_path: Path) -> None:
    lock_path = tmp_path / "app.lock"
    holder = AppLock(lock_path)
    holder.acquire()
    loser = AppLock(lock_path)
    with pytest.raises(AppLockedError):
        loser.acquire()
    holder.release()
    # 실패한 인스턴스가 fd를 쥐고 있지 않으므로 같은 인스턴스로 다시 잡을 수 있다.
    loser.acquire()
    with pytest.raises(AppLockedError):
        AppLock(lock_path).acquire()
    loser.release()


def test_locked_error_message_is_korean(tmp_path: Path) -> None:
    lock_path = tmp_path / "app.lock"
    with AppLock(lock_path), pytest.raises(AppLockedError, match="다른 앱 또는 리셋이 실행 중이다"):
        AppLock(lock_path).acquire()


def test_acquire_twice_on_same_instance_raises_runtime_error(tmp_path: Path) -> None:
    lock = AppLock(tmp_path / "app.lock")
    lock.acquire()
    try:
        with pytest.raises(RuntimeError):
            lock.acquire()
    finally:
        lock.release()
    with AppLock(tmp_path / "app.lock"):
        pass


def test_unexpected_flock_error_propagates_and_closes_fd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    closed: list[int] = []
    real_close = os.close

    def failing_flock(fd: int, operation: int) -> None:
        raise OSError("flock 실패")

    def recording_close(fd: int) -> None:
        closed.append(fd)
        real_close(fd)

    monkeypatch.setattr(app_lock.fcntl, "flock", failing_flock)
    monkeypatch.setattr(app_lock.os, "close", recording_close)
    lock = AppLock(tmp_path / "app.lock")
    with pytest.raises(OSError, match="flock 실패"):
        lock.acquire()
    assert len(closed) == 1
    monkeypatch.undo()
    with lock:
        pass
