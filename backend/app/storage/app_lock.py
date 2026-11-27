"""앱과 CLI 리셋이 함께 쓰는 `var/app.lock` 배타 잠금 (스펙 3.8).

`fcntl.flock`은 열린 파일 설명(open file description)마다 잠금을 걸므로, 같은 프로세스에서도
`open()`을 따로 한 두 인스턴스는 서로 충돌한다.
"""

from __future__ import annotations

import fcntl
import os
from pathlib import Path
from types import TracebackType

from app.storage.errors import AppLockedError

_LOCKED_MESSAGE = "다른 앱 또는 리셋이 실행 중이다"


class AppLock:
    """`path`에 대한 배타 잠금. `acquire()`/`release()` 또는 `with` 블록으로 쓴다."""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._fd: int | None = None

    def acquire(self) -> None:
        """잠금을 잡는다. 다른 쪽이 쥐고 있으면 기다리지 않고 `AppLockedError`를 낸다.

        같은 인스턴스로 두 번 잡으면 fd가 새지 않도록 `RuntimeError`를 낸다.
        """
        if self._fd is not None:
            raise RuntimeError("이미 잡은 앱 잠금을 다시 잡으려 했다")
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self._path, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as err:
            os.close(fd)
            raise AppLockedError(_LOCKED_MESSAGE) from err
        except BaseException:
            os.close(fd)
            raise
        self._fd = fd

    def release(self) -> None:
        """잠금을 풀고 파일을 닫는다. 잡지 않았거나 이미 풀었으면 아무것도 하지 않는다."""
        fd = self._fd
        if fd is None:
            return
        self._fd = None
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)

    def __enter__(self) -> AppLock:
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.release()
