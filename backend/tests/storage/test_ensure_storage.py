"""앱 시작 때 저장소 준비(`ensure_storage`) 테스트 (스펙 3.8 자동 시드·복구 경로).

실제 시드를 한 번 적재한 DB(`conftest.py`의 `pending_db`·`seeded_db`)를 테스트마다 복사해 쓴다.
장애 주입·스파이는 함수가 정의된 `app.storage.seed_reset` 모듈의 속성을 덮어쓴다.
"""

from __future__ import annotations

import logging
import shutil
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path

import pytest

from app.config import Settings, StoragePaths
from app.storage import seed_reset
from app.storage.db import connect
from app.storage.errors import ResetCleanupError, StoragePrepareError
from app.storage.photos import new_photo_id, save_photo_bytes
from app.storage.queries import get_demo_date
from app.storage.seed import CLEANUP_PENDING_KEY, ensure_storage
from tests.storage.demo import DEMO
from tests.storage.dump import TableDump, table_dump
from tests.storage.reset_support import (
    app_sidecars,
    existing,
    make_paths,
    spy_unlink,
    tmp_files,
    with_suffixes,
)

# 구현 상수와 독립된 기대값(oracle)이다(`reset_support.py` 참고).
CHECKPOINT_SUFFIXES = ("", "-wal", "-shm")
WARNING_TEXT = "앱을 끄고 리셋하면 오늘 기준으로 다시 맞춘다"
_real_connect = seed_reset.connect


@pytest.fixture
def var_dir(tmp_path: Path) -> Path:
    return tmp_path / "var"


@pytest.fixture
def paths(var_dir: Path) -> StoragePaths:
    return make_paths(var_dir)


def _settings(var_dir: Path, demo_date: str | None = None) -> Settings:
    return Settings(var_dir=var_dir, demo_date=demo_date)


def _add_leftovers(paths: StoragePaths) -> None:
    """대화 DB와 보조 파일, 사진 2장을 남긴다."""
    paths.app_db.parent.mkdir(parents=True, exist_ok=True)
    for path in _checkpoint_files(paths):
        path.write_bytes(b"checkpoint")
    for _ in range(2):
        save_photo_bytes(paths.photos_dir, new_photo_id(), b"jpeg")


def _checkpoint_files(paths: StoragePaths) -> list[Path]:
    return with_suffixes(paths.checkpoints_db, CHECKPOINT_SUFFIXES)


def _photo_files(paths: StoragePaths) -> list[Path]:
    return sorted(paths.photos_dir.iterdir()) if paths.photos_dir.is_dir() else []


def _install_db(source: Path, paths: StoragePaths) -> None:
    paths.app_db.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, paths.app_db)


def _has_mark(paths: StoragePaths) -> bool:
    with connect(paths.app_db) as conn:
        row = conn.execute(
            "SELECT 1 FROM seed_meta WHERE key = ?", (CLEANUP_PENDING_KEY,)
        ).fetchone()
    return row is not None


def _without_mark(dump: TableDump) -> TableDump:
    return {
        **dump,
        "seed_meta": [row for row in dump["seed_meta"] if row[0] != CLEANUP_PENDING_KEY],
    }


def _fail_checkpoints_unlink(monkeypatch: pytest.MonkeyPatch, enabled: list[bool]) -> None:
    """`enabled[0]`이 참인 동안 대화 DB 삭제만 실패시킨다."""
    calls: list[str] = []
    spy_unlink(
        monkeypatch,
        calls,
        fail_when=lambda path: enabled[0] and path.name.startswith("checkpoints.db"),
    )


# app.db 없음: 자동 시드 ---------------------------------------------------------


def test_ensure_storage_seeds_when_app_db_missing_and_removes_leftovers(
    var_dir: Path, paths: StoragePaths, fresh_dump: TableDump
) -> None:
    _add_leftovers(paths)

    ensure_storage(_settings(var_dir), today=DEMO)

    assert table_dump(paths.app_db) == fresh_dump
    assert existing(_checkpoint_files(paths)) == []
    assert _photo_files(paths) == []
    assert not _has_mark(paths)


def test_ensure_storage_seeds_empty_var_with_configured_demo_date(
    var_dir: Path, paths: StoragePaths
) -> None:
    ensure_storage(_settings(var_dir, demo_date="2026-12-05"), today=date(2026, 11, 27))

    with connect(paths.app_db) as conn:
        assert get_demo_date(conn) == DEMO


def test_ensure_storage_without_today_uses_real_today(var_dir: Path, paths: StoragePaths) -> None:
    ensure_storage(_settings(var_dir))

    with connect(paths.app_db) as conn:
        assert get_demo_date(conn) == date.today()


def test_ensure_storage_removes_orphan_sidecars_before_seeding(
    var_dir: Path, paths: StoragePaths, fresh_dump: TableDump
) -> None:
    paths.app_db.parent.mkdir(parents=True)
    for path in app_sidecars(paths):
        path.write_bytes(b"orphan sidecar")

    ensure_storage(_settings(var_dir), today=DEMO)

    assert table_dump(paths.app_db) == fresh_dump


def test_ensure_storage_orphan_sidecar_delete_failure_leaves_no_app_db(
    var_dir: Path, paths: StoragePaths, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths.app_db.parent.mkdir(parents=True)
    for path in app_sidecars(paths):
        path.write_bytes(b"orphan sidecar")
    calls: list[str] = []
    spy_unlink(monkeypatch, calls, fail_when=lambda path: path.name == "app.db-wal")

    with pytest.raises(StoragePrepareError):
        ensure_storage(_settings(var_dir), today=DEMO)

    assert not paths.app_db.exists()
    assert "app.db-wal" in calls


def test_ensure_storage_replaces_leftover_tmp_when_app_db_missing(
    var_dir: Path, paths: StoragePaths, seeded_db: Path, fresh_dump: TableDump
) -> None:
    paths.app_db.parent.mkdir(parents=True)
    tmp = tmp_files(paths)[0]
    shutil.copyfile(seeded_db, tmp)
    with sqlite3.connect(tmp) as conn:
        conn.execute("DELETE FROM alerts")
    conn.close()

    ensure_storage(_settings(var_dir), today=DEMO)

    assert table_dump(paths.app_db) == fresh_dump
    assert existing(tmp_files(paths)) == []


# app.db 있음: 표시 없으면 무접촉 ------------------------------------------------


def test_ensure_storage_existing_db_without_mark_skips_cleanup(
    var_dir: Path,
    paths: StoragePaths,
    seeded_db: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_db(seeded_db, paths)
    _add_leftovers(paths)
    tmp = tmp_files(paths)[0]
    tmp.write_bytes(b"leftover tmp")
    before = table_dump(paths.app_db)
    photos_before = _photo_files(paths)
    cleanup_calls: list[StoragePaths] = []
    monkeypatch.setattr(seed_reset, "finish_cleanup", cleanup_calls.append)

    ensure_storage(_settings(var_dir), today=DEMO)

    assert cleanup_calls == []
    assert table_dump(paths.app_db) == before
    assert tmp.read_bytes() == b"leftover tmp"
    assert _photo_files(paths) == photos_before
    assert existing(_checkpoint_files(paths)) == [p.name for p in _checkpoint_files(paths)]


# app.db 있음 + 정리 대기 표시: 정리 이어 가기 ------------------------------------


def test_ensure_storage_pending_mark_finishes_cleanup(
    var_dir: Path, paths: StoragePaths, pending_db: Path, fresh_dump: TableDump
) -> None:
    _install_db(pending_db, paths)
    _add_leftovers(paths)

    ensure_storage(_settings(var_dir), today=DEMO)

    assert not _has_mark(paths)
    assert table_dump(paths.app_db) == fresh_dump
    assert existing(_checkpoint_files(paths)) == []
    assert _photo_files(paths) == []


def test_ensure_storage_pending_mark_cleanup_failure_raises(
    var_dir: Path,
    paths: StoragePaths,
    pending_db: Path,
    fresh_dump: TableDump,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_db(pending_db, paths)
    _add_leftovers(paths)
    _fail_checkpoints_unlink(monkeypatch, [True])

    with pytest.raises(ResetCleanupError) as info:
        ensure_storage(_settings(var_dir), today=DEMO)

    assert info.value.failures == ("checkpoints.db",)
    assert _has_mark(paths)
    assert _without_mark(table_dump(paths.app_db)) == fresh_dump


def test_ensure_storage_retries_cleanup_after_auto_seed_cleanup_failure(
    var_dir: Path,
    paths: StoragePaths,
    fresh_dump: TableDump,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _add_leftovers(paths)
    failing = [True]
    _fail_checkpoints_unlink(monkeypatch, failing)

    with pytest.raises(ResetCleanupError) as info:
        ensure_storage(_settings(var_dir), today=DEMO)

    assert info.value.failures == ("checkpoints.db",)
    assert paths.app_db.exists()
    assert _has_mark(paths)

    failing[0] = False
    ensure_storage(_settings(var_dir), today=DEMO)

    assert not _has_mark(paths)
    assert table_dump(paths.app_db) == fresh_dump
    assert existing(_checkpoint_files(paths)) == []


class _FailingMarkDelete:
    """정리 대기 표시 DELETE만 실패시키는 연결 대리 객체. 나머지는 실제 연결에 넘긴다."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def execute(self, sql: str, *args: object) -> sqlite3.Cursor:
        if sql.lstrip().upper().startswith("DELETE FROM SEED_META"):
            raise sqlite3.OperationalError("주입한 표시 삭제 실패")
        return self._conn.execute(sql, *args)

    def __getattr__(self, name: str) -> object:
        return getattr(self._conn, name)


def test_ensure_storage_retries_after_mark_delete_failure(
    var_dir: Path,
    paths: StoragePaths,
    pending_db: Path,
    fresh_dump: TableDump,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_db(pending_db, paths)
    _add_leftovers(paths)

    @contextmanager
    def failing_connect(db_path: Path, **kwargs: object) -> Iterator[object]:
        with _real_connect(db_path, **kwargs) as conn:
            yield _FailingMarkDelete(conn)

    monkeypatch.setattr(seed_reset, "connect", failing_connect)

    with pytest.raises(ResetCleanupError) as info:
        ensure_storage(_settings(var_dir), today=DEMO)

    assert info.value.failures == ("cleanup_pending",)
    assert _has_mark(paths)
    assert existing(_checkpoint_files(paths)) == []
    assert _photo_files(paths) == []

    monkeypatch.setattr(seed_reset, "connect", _real_connect)
    ensure_storage(_settings(var_dir), today=DEMO)

    assert not _has_mark(paths)
    assert table_dump(paths.app_db) == fresh_dump


# 시연일 불일치 경고 --------------------------------------------------------------


def test_ensure_storage_warns_when_seed_date_differs_from_today(
    var_dir: Path,
    paths: StoragePaths,
    seeded_db: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _install_db(seeded_db, paths)
    before = table_dump(paths.app_db)
    today = DEMO + timedelta(days=1)

    with caplog.at_level(logging.WARNING, logger="app.storage.seed_reset"):
        ensure_storage(_settings(var_dir), today=today)

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert warnings[0].getMessage() == (
        f"시드 기준일 {DEMO.isoformat()}, 오늘 {today.isoformat()}. {WARNING_TEXT}"
    )
    assert table_dump(paths.app_db) == before


@pytest.mark.parametrize(
    ("demo_date", "today"),
    [("2026-12-01", DEMO + timedelta(days=1)), (None, DEMO)],
    ids=["demo-date-set", "same-day"],
)
def test_ensure_storage_no_date_warning(
    var_dir: Path,
    paths: StoragePaths,
    seeded_db: Path,
    caplog: pytest.LogCaptureFixture,
    demo_date: str | None,
    today: date,
) -> None:
    _install_db(seeded_db, paths)

    with caplog.at_level(logging.WARNING):
        ensure_storage(_settings(var_dir, demo_date=demo_date), today=today)

    assert [r for r in caplog.records if WARNING_TEXT in r.getMessage()] == []
