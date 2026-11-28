"""쓰기 실행기 스레드를 `threading.Event`로 멈추는 테스트 게이트."""

from __future__ import annotations

import asyncio
import threading
from typing import Any

import pytest

from tests.services.generation import TIMEOUT


class ThreadGate:
    """`hold()`를 부른 스레드를 `release`가 켜질 때까지 멈춘다. 기다림은 `TIMEOUT` 상한."""

    def __init__(self) -> None:
        self.entered = threading.Event()
        self.release = threading.Event()

    def hold(self) -> None:
        """들어왔음을 알리고 풀릴 때까지 기다린다. 풀리지 않으면 `TimeoutError`."""
        self.entered.set()
        if not self.release.wait(TIMEOUT):
            raise TimeoutError("게이트가 풀리지 않았다")

    async def wait_entered(self) -> None:
        """다른 스레드가 `hold()`에 들어올 때까지 기다린다."""
        assert await asyncio.to_thread(self.entered.wait, TIMEOUT)

    def patch(self, monkeypatch: pytest.MonkeyPatch, owner: object, name: str) -> None:
        """`owner.name` 호출이 원래 함수를 부르기 전에 `hold()`하게 바꾼다."""
        real = getattr(owner, name)

        def gated(*args: Any, **kwargs: Any) -> Any:
            self.hold()
            return real(*args, **kwargs)

        monkeypatch.setattr(owner, name, gated)
