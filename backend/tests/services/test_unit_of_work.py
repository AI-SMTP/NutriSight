"""`run_in_db` 작업 단위 함수 테스트 (스펙 3.2 "연결과 트랜잭션")."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from app.services import unit_of_work
from app.services.unit_of_work import WriteResult, run_in_db
from app.storage.db import connect


@pytest.fixture
def traced(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """`run_in_db`가 여는 연결이 실행한 SQL 문을 모은다(PRAGMA 설정 뒤부터)."""
    statements: list[str] = []
    real_connect = unit_of_work.connect

    @contextmanager
    def tracing_connect(path: Path) -> Iterator[sqlite3.Connection]:
        with real_connect(path) as conn:
            conn.set_trace_callback(statements.append)
            yield conn

    monkeypatch.setattr(unit_of_work, "connect", tracing_connect)
    return statements


def _insert_meta(key: str, value: str) -> Callable[[sqlite3.Connection], None]:
    def fn(conn: sqlite3.Connection) -> None:
        conn.execute("INSERT INTO seed_meta (key, value) VALUES (?, ?)", (key, value))

    return fn


def _meta_keys(db_path: Path) -> list[str]:
    with connect(db_path) as conn:
        return [row["key"] for row in conn.execute("SELECT key FROM seed_meta ORDER BY key")]


def _begins(statements: list[str]) -> list[str]:
    return [s.strip() for s in statements if s.strip().upper().startswith("BEGIN")]


def test_write_mode_begins_immediate_once_and_commits(db_path: Path, traced: list[str]) -> None:
    result = run_in_db(db_path, _insert_meta("a", "1"), mode="write")

    assert result is None
    assert _begins(traced) == ["BEGIN IMMEDIATE"]
    assert traced[0] == "BEGIN IMMEDIATE"
    assert "COMMIT" in traced
    assert _meta_keys(db_path) == ["a"]


def test_write_mode_returns_fn_value(db_path: Path) -> None:
    value = run_in_db(db_path, lambda conn: 42, mode="write")

    assert value == 42


def test_snapshot_mode_begins_deferred_and_hides_later_commits(
    db_path: Path, traced: list[str]
) -> None:
    def fn(conn: sqlite3.Connection) -> tuple[int, int]:
        before = conn.execute("SELECT COUNT(*) FROM seed_meta").fetchone()[0]
        # 첫 조회 뒤 다른 연결이 커밋한다. 스냅샷 안의 두 번째 조회는 이 행을 보지 않아야 한다.
        with connect(db_path) as other:
            other.execute("INSERT INTO seed_meta (key, value) VALUES ('late', 'x')")
        after = conn.execute("SELECT COUNT(*) FROM seed_meta").fetchone()[0]
        return before, after

    before, after = run_in_db(db_path, fn, mode="snapshot")

    assert (before, after) == (0, 0)
    assert _begins(traced) == ["BEGIN DEFERRED"]
    assert traced[0] == "BEGIN DEFERRED"
    assert _meta_keys(db_path) == ["late"]


def test_read_mode_does_not_begin(db_path: Path, traced: list[str]) -> None:
    count = run_in_db(
        db_path,
        lambda conn: conn.execute("SELECT COUNT(*) FROM seed_meta").fetchone()[0],
        mode="read",
    )

    assert count == 0
    assert _begins(traced) == []


def test_read_mode_sees_latest_commit_between_queries(db_path: Path) -> None:
    def fn(conn: sqlite3.Connection) -> tuple[int, int]:
        before = conn.execute("SELECT COUNT(*) FROM seed_meta").fetchone()[0]
        with connect(db_path) as other:
            other.execute("INSERT INTO seed_meta (key, value) VALUES ('late', 'x')")
        after = conn.execute("SELECT COUNT(*) FROM seed_meta").fetchone()[0]
        return before, after

    assert run_in_db(db_path, fn, mode="read") == (0, 1)


class _Boom(Exception):
    pass


def test_write_mode_rolls_back_and_reraises_on_fn_error(db_path: Path) -> None:
    def fn(conn: sqlite3.Connection) -> None:
        conn.execute("INSERT INTO seed_meta (key, value) VALUES ('a', '1')")
        raise _Boom("저장 실패")

    with pytest.raises(_Boom, match="저장 실패"):
        run_in_db(db_path, fn, mode="write")

    assert _meta_keys(db_path) == []


def test_write_keyword_is_rejected(db_path: Path) -> None:
    with pytest.raises(TypeError):
        run_in_db(db_path, lambda conn: None, write=True)  # type: ignore[call-arg]


def test_mode_is_keyword_only(db_path: Path) -> None:
    with pytest.raises(TypeError):
        run_in_db(db_path, lambda conn: None, "write")  # type: ignore[misc]


def test_unknown_mode_is_rejected_without_opening_db(tmp_path: Path) -> None:
    path = tmp_path / "missing.db"

    with pytest.raises(ValueError, match="mode"):
        run_in_db(path, lambda conn: None, mode="writ")  # type: ignore[arg-type]

    assert not path.exists()


def test_write_result_defaults_to_no_events_and_is_frozen() -> None:
    result = WriteResult(value=1)

    assert result.events == ()
    with pytest.raises(AttributeError):
        result.value = 2  # type: ignore[misc]
