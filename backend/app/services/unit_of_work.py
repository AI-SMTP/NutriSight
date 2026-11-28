"""작업 단위 함수 `run_in_db`와 쓰기 결과 `WriteResult` (스펙 3.2 "연결과 트랜잭션").

서비스 계층의 DB 연결은 `run_in_db` 하나로 연다. 트랜잭션 시작(`BEGIN`)도 이 함수 한 곳뿐이므로
쓰기 서비스가 다른 쓰기 서비스를 불러도 같은 트랜잭션 안에서 이어진다. 서비스 함수는
`BEGIN`·`commit`을 부르지 않는다. 커밋·롤백은 `connect()` 블록 종료가 맡는다.

`sqlite3`의 기본 `isolation_level=""`(레거시 트랜잭션 제어)는 트랜잭션이 이미 열려 있으면
암묵적 `BEGIN`을 넣지 않으므로, 여기서 연 `BEGIN IMMEDIATE`·`BEGIN DEFERRED`가 그대로
블록 종료의 `commit()`까지 이어진다.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Literal

from app.events.bus import Event
from app.storage.db import connect

Mode = Literal["read", "snapshot", "write"]

# mode별로 `fn` 앞에 실행할 문. `read`는 트랜잭션을 열지 않는다(조회 하나짜리 읽기).
_BEGIN_BY_MODE: Mapping[str, str | None] = MappingProxyType(
    {
        "read": None,
        "snapshot": "BEGIN DEFERRED",
        "write": "BEGIN IMMEDIATE",
    }
)


@dataclass(frozen=True)
class WriteResult[T]:
    """쓰기 서비스의 반환. 커밋 뒤 쓰기 실행기가 `events`를 순서대로 발행한다."""

    value: T
    events: tuple[Event, ...] = ()


def run_in_db[T](db_path: Path, fn: Callable[[sqlite3.Connection], T], *, mode: Mode) -> T:
    """`db_path`에 연결해 `mode`에 맞게 트랜잭션을 연 뒤 `fn(conn)`의 결과를 돌려준다.

    - `write`: `BEGIN IMMEDIATE`로 쓰기를 직렬화한다. 쓰기 실행기 스레드에서만 부른다.
    - `snapshot`: `BEGIN DEFERRED`로 읽기 트랜잭션을 열어 첫 읽기 시점의 스냅샷을 끝까지 본다.
    - `read`: 트랜잭션을 열지 않는다.

    블록이 끝나면 `connect()`가 커밋하고, `fn`이 예외를 던지면 롤백한 뒤 그대로 다시 던진다.
    `fn` 안에서 `executescript`를 쓰지 않는다(열린 트랜잭션을 먼저 커밋한다).
    """
    if mode not in _BEGIN_BY_MODE:
        raise ValueError(f"지원하지 않는 mode: {mode!r}")
    begin = _BEGIN_BY_MODE[mode]
    with connect(db_path) as conn:
        if begin is not None:
            conn.execute(begin)
        return fn(conn)
