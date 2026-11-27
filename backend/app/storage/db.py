"""업무 DB 연결과 스키마 생성 (스펙 3.3·3.4).

모든 연결은 `connect()`로 연다. 연결마다 외래 키·저널 모드·잠금 대기를 같은 값으로 맞춘다.
저장소 함수는 동기 함수이고, 작업 단위마다 짧게 연결한다.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from functools import cache
from importlib.resources import files
from pathlib import Path

SCHEMA_VERSION = 1
BUSY_TIMEOUT_MS = 5000
# PRAGMA 값은 바인딩할 수 없어 문자열로 넣으므로 허용 목록으로 막는다.
JOURNAL_MODES = frozenset({"WAL", "DELETE"})
_SCHEMA_RESOURCE = "schema.sql"


@contextmanager
def connect(db_path: Path, *, journal_mode: str = "WAL") -> Iterator[sqlite3.Connection]:
    """`db_path`에 연결해 PRAGMA를 맞춘 연결을 내준다.

    트랜잭션을 열기 전에 `journal_mode`·`foreign_keys=ON`·`busy_timeout=5000`을 설정하고
    `row_factory`를 `sqlite3.Row`로 둔다. 블록이 정상 종료하면 커밋하고(커밋 중 지연 외래 키
    위반도 예외로 넘긴다), 예외가 나면 롤백한 뒤 예외를 다시 던진다. 연결은 항상 닫는다.

    `journal_mode`는 `WAL`(기본) 또는 `DELETE`(파일 하나로 완결해야 하는 임시 DB)만 받는다.
    """
    mode = journal_mode.upper()
    if mode not in JOURNAL_MODES:
        raise ValueError(f"지원하지 않는 journal_mode: {journal_mode!r}")

    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        # SQLite는 모드를 바꾸지 못해도 오류 없이 현재 모드를 돌려주므로 결과를 확인한다.
        actual = conn.execute(f"PRAGMA journal_mode = {mode}").fetchone()[0]
        if actual.upper() != mode:
            raise sqlite3.OperationalError(f"journal_mode를 {mode}로 바꾸지 못했다: {actual}")
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


@cache
def _read_schema_sql() -> str:
    """패키지 데이터 `schema.sql`의 내용을 읽는다(프로세스마다 한 번)."""
    return files(__package__).joinpath(_SCHEMA_RESOURCE).read_text(encoding="utf-8")


def create_schema(conn: sqlite3.Connection, *, begin: bool = False) -> None:
    """`schema.sql`로 테이블·제약·인덱스를 만든다.

    `executescript`는 실행 전에 열린 트랜잭션을 커밋하므로, `begin=True`이면 스크립트 앞에
    `BEGIN;`을 붙여 스크립트 안에서 트랜잭션을 연다. 그러면 트랜잭션이 열린 채로 돌아와 이후
    행 적재와 DDL이 한 번의 `commit()`·`rollback()`으로 함께 확정되거나 취소된다.
    """
    script = _read_schema_sql()
    conn.executescript(f"BEGIN;\n{script}" if begin else script)
