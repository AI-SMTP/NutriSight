"""교체 뒤 정리(`finish_cleanup`)와 리셋 성공 경로 테스트 (스펙 3.8).

실제 시드를 한 번 적재한 DB(`conftest.py`의 `pending_db`·`seeded_db`)를 테스트마다 복사해 쓴다.
장애 주입·스파이는 함수가 정의된 `app.storage.seed_reset` 모듈의 속성을 덮어쓴다
(`reset_support.py` 참고). 리셋 실패 경로는 `test_reset_failures.py`에 있다.
"""

from __future__ import annotations

import shutil
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path

import pytest

from app import wiring
from app.config import DEFAULT_SEED_PATH, Settings, StoragePaths, storage_paths
from app.nutrition.fake import FakeNutritionEngine
from app.nutrition.types import DailyTarget, TargetSource
from app.storage import seed_reset
from app.storage.app_lock import AppLock
from app.storage.db import connect
from app.storage.errors import AppLockedError, ResetCleanupError
from app.storage.photos import new_photo_id, save_photo_bytes
from app.storage.queries import list_daily_intakes
from app.storage.seed import (
    CLEANUP_PENDING_KEY,
    ResetResult,
    finish_cleanup,
    rebuild_storage,
    reset_storage,
)
from tests.storage.demo import DEMO
from tests.storage.dump import TableDump, main_file_dump, table_dump
from tests.storage.reset_support import (
    EXTRA_ALERT_ID,
    alert_ids,
    app_sidecars,
    existing,
    install_wal_db,
    make_paths,
    snapshot_dump,
    spy_replace,
    spy_unlink,
    tmp_files,
    var_paths,
    with_suffixes,
)
from tests.storage.rows import insert_alert

# 구현 상수와 독립된 기대값(oracle)이다(`reset_support.py` 참고).
CHECKPOINT_SUFFIXES = ("", "-wal", "-shm")
EXPECTED_RESULT = ResetResult(
    demo_date=DEMO, patients=10, meal_orders=240, daily_intakes=70, alerts=70
)


@pytest.fixture
def paths(tmp_path: Path, pending_db: Path) -> StoragePaths:
    """교체 직후 상태: 표시가 있는 `app.db`, 대화 DB와 보조 파일, 사진 2장."""
    result = var_paths(tmp_path)
    shutil.copyfile(pending_db, result.app_db)
    _add_checkpoints_and_photos(result)
    return result


def _add_checkpoints_and_photos(paths: StoragePaths) -> None:
    for path in _checkpoint_files(paths):
        path.write_bytes(b"checkpoint")
    for _ in range(2):
        save_photo_bytes(paths.photos_dir, new_photo_id(), b"jpeg")


def _checkpoint_files(paths: StoragePaths) -> list[Path]:
    return with_suffixes(paths.checkpoints_db, CHECKPOINT_SUFFIXES)


def _photo_files(paths: StoragePaths) -> list[Path]:
    return sorted(paths.photos_dir.iterdir()) if paths.photos_dir.is_dir() else []


def _has_mark(paths: StoragePaths) -> bool:
    with connect(paths.app_db) as conn:
        row = conn.execute(
            "SELECT 1 FROM seed_meta WHERE key = ?", (CLEANUP_PENDING_KEY,)
        ).fetchone()
    return row is not None


def test_fixture_starts_with_mark_files_and_photos(paths: StoragePaths) -> None:
    assert _has_mark(paths)
    assert all(path.exists() for path in _checkpoint_files(paths))
    assert len(_photo_files(paths)) == 2


def test_finish_cleanup_removes_files_and_mark(paths: StoragePaths) -> None:
    finish_cleanup(paths)

    assert not any(path.exists() for path in _checkpoint_files(paths))
    assert _photo_files(paths) == []
    assert not _has_mark(paths)


def test_finish_cleanup_keeps_other_seed_meta_rows(paths: StoragePaths) -> None:
    finish_cleanup(paths)

    with connect(paths.app_db) as conn:
        keys = {row["key"] for row in conn.execute("SELECT key FROM seed_meta")}
    assert {"schema_version", "demo_date", "seeded_at"} <= keys


def test_finish_cleanup_attempts_both_groups_when_both_fail(
    paths: StoragePaths, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    def failing_unlink(path: Path) -> None:
        calls.append(path.name)
        raise PermissionError(f"주입한 삭제 실패: {path}")

    def failing_clear(photos_dir: Path) -> None:
        calls.append("clear_photos")
        raise PermissionError(f"주입한 사진 삭제 실패: {photos_dir}")

    monkeypatch.setattr(seed_reset, "_unlink_if_exists", failing_unlink)
    monkeypatch.setattr(seed_reset, "clear_photos", failing_clear)

    with pytest.raises(ResetCleanupError) as exc_info:
        finish_cleanup(paths)

    assert "checkpoints.db" in calls
    assert "clear_photos" in calls
    assert exc_info.value.failures == ("checkpoints.db", "photos")
    assert "checkpoints.db" in str(exc_info.value)
    assert "photos" in str(exc_info.value)
    assert _has_mark(paths)


def test_finish_cleanup_continues_after_checkpoint_failure(
    paths: StoragePaths, monkeypatch: pytest.MonkeyPatch
) -> None:
    def failing_unlink(path: Path) -> None:
        raise PermissionError(f"주입한 삭제 실패: {path}")

    monkeypatch.setattr(seed_reset, "_unlink_if_exists", failing_unlink)

    with pytest.raises(ResetCleanupError) as exc_info:
        finish_cleanup(paths)

    assert exc_info.value.failures == ("checkpoints.db",)
    assert _photo_files(paths) == []
    assert _has_mark(paths)


def test_finish_cleanup_reports_mark_deletion_failure(
    paths: StoragePaths, monkeypatch: pytest.MonkeyPatch
) -> None:
    @contextmanager
    def failing_connect(db_path: Path, **_: object) -> Iterator[sqlite3.Connection]:
        raise sqlite3.OperationalError(f"주입한 표시 삭제 실패: {db_path}")
        yield  # pragma: no cover

    monkeypatch.setattr(seed_reset, "connect", failing_connect)

    with pytest.raises(ResetCleanupError) as exc_info:
        finish_cleanup(paths)

    assert exc_info.value.failures == ("cleanup_pending",)
    assert not any(path.exists() for path in _checkpoint_files(paths))
    assert _photo_files(paths) == []
    monkeypatch.undo()
    assert _has_mark(paths)


def test_finish_cleanup_twice_succeeds(paths: StoragePaths) -> None:
    finish_cleanup(paths)
    finish_cleanup(paths)

    assert not _has_mark(paths)


def test_finish_cleanup_succeeds_without_files_or_photos_dir(paths: StoragePaths) -> None:
    for path in _checkpoint_files(paths):
        path.unlink()
    shutil.rmtree(paths.photos_dir)

    finish_cleanup(paths)

    assert not paths.photos_dir.exists()
    assert not _has_mark(paths)


def test_finish_cleanup_retry_after_failure_completes(
    paths: StoragePaths, monkeypatch: pytest.MonkeyPatch
) -> None:
    def failing_clear(photos_dir: Path) -> None:
        raise PermissionError(f"주입한 사진 삭제 실패: {photos_dir}")

    monkeypatch.setattr(seed_reset, "clear_photos", failing_clear)
    with pytest.raises(ResetCleanupError):
        finish_cleanup(paths)
    monkeypatch.undo()

    finish_cleanup(paths)

    assert _photo_files(paths) == []
    assert not _has_mark(paths)


def test_unlink_if_exists_removes_file_and_ignores_missing(tmp_path: Path) -> None:
    target = tmp_path / "file"
    target.write_bytes(b"x")

    seed_reset._unlink_if_exists(target)
    seed_reset._unlink_if_exists(target)

    assert not target.exists()


# 리셋 성공 경로 (T10.1) -------------------------------------------------------


def _rebuild(paths: StoragePaths) -> ResetResult:
    return rebuild_storage(paths, DEFAULT_SEED_PATH, DEMO, FakeNutritionEngine())


class _LowTargetEngine(FakeNutritionEngine):
    """목표 1,000 kcal·단백질 40 g을 주는 대체 엔진."""

    def daily_target(self, profile, targets, weights, on):  # type: ignore[override]
        return DailyTarget(energy_kcal=1000.0, protein_g=40.0, source=TargetSource.TEAM_SET)


def test_reset_storage_uses_configured_engine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(wiring.NUTRITION_ENGINES, "alt", lambda settings: _LowTargetEngine())
    settings = Settings(var_dir=tmp_path / "var", nutrition_engine="alt", _env_file=None)

    result = reset_storage(settings, demo_date=DEMO)

    first_day = DEMO - timedelta(days=7)
    with connect(storage_paths(settings).app_db) as conn:
        (row,) = list_daily_intakes(conn, "NS01", first_day, first_day)
    assert result == EXPECTED_RESULT
    assert row.energy_pct == pytest.approx(row.energy_kcal * 3 / row.recorded_meals / 1000 * 100)
    assert row.protein_pct == pytest.approx(row.protein_g * 3 / row.recorded_meals / 40 * 100)


def test_reset_storage_releases_app_lock(tmp_path: Path) -> None:
    settings = Settings(var_dir=tmp_path / "var", _env_file=None)

    reset_storage(settings, demo_date=DEMO)

    with AppLock(storage_paths(settings).app_lock):
        pass


def test_reset_storage_locked_raises_without_touching_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(var_dir=tmp_path / "var", _env_file=None)
    paths = storage_paths(settings)
    built: list[object] = []
    monkeypatch.setattr(seed_reset, "build_database", lambda *args, **kw: built.append(args))

    with AppLock(paths.app_lock), pytest.raises(AppLockedError):
        reset_storage(settings, demo_date=DEMO)

    assert built == []
    assert not paths.app_db.exists()
    assert existing(tmp_files(paths)) == []


def test_rebuild_storage_from_empty_var(tmp_path: Path) -> None:
    paths = make_paths(tmp_path / "var")

    result = _rebuild(paths)

    assert result == EXPECTED_RESULT
    assert not _has_mark(paths)
    assert existing(tmp_files(paths)) == []


def test_rebuild_storage_discards_demo_changes(
    tmp_path: Path, seeded_db: Path, fresh_dump: TableDump
) -> None:
    paths = var_paths(tmp_path)
    shutil.copyfile(seeded_db, paths.app_db)
    with connect(paths.app_db) as conn:
        insert_alert(conn, alert_id=EXTRA_ALERT_ID, patient_id="NS01")
    _add_checkpoints_and_photos(paths)

    _rebuild(paths)

    after = table_dump(paths.app_db)
    assert len(after) == 15
    assert after == fresh_dump
    assert _photo_files(paths) == []
    assert existing(_checkpoint_files(paths)) == []


def test_rebuild_storage_succeeds_with_leftover_committed_tmp(
    tmp_path: Path, seeded_db: Path, pending_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = make_paths(tmp_path / "var")
    install_wal_db(seeded_db, paths.app_db)
    before = snapshot_dump(paths, tmp_path / "before")
    tmp, journal = tmp_files(paths)[:2]
    shutil.copyfile(pending_db, tmp)
    journal.write_bytes(b"stale journal")
    calls: list[str] = []
    seen: list[TableDump] = []
    spy_replace(monkeypatch, calls, before=lambda: seen.append(main_file_dump(paths.app_db)))

    result = _rebuild(paths)

    assert result == EXPECTED_RESULT
    assert seen == [before]
    assert EXTRA_ALERT_ID in alert_ids(before)
    assert existing(tmp_files(paths)) == []
    assert not _has_mark(paths)


def test_rebuild_storage_removes_orphan_sidecars_before_replace(
    tmp_path: Path, seeded_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    donor = make_paths(tmp_path / "donor")
    install_wal_db(seeded_db, donor.app_db)
    paths = var_paths(tmp_path)
    for src, dst in zip(app_sidecars(donor), app_sidecars(paths), strict=True):
        shutil.copyfile(src, dst)
    calls: list[str] = []
    seen: list[list[str]] = []
    spy_replace(monkeypatch, calls, before=lambda: seen.append(existing(app_sidecars(paths))))

    _rebuild(paths)

    dump = table_dump(paths.app_db)
    assert seen == [[]]
    assert EXTRA_ALERT_ID not in alert_ids(dump)
    assert len(dump["alerts"]) == EXPECTED_RESULT.alerts
    with connect(paths.app_db) as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_rebuild_storage_checkpoints_then_removes_sidecars_before_replace(
    tmp_path: Path, seeded_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = make_paths(tmp_path / "var")
    install_wal_db(seeded_db, paths.app_db)
    assert existing(app_sidecars(paths)) == ["app.db-wal", "app.db-shm"]
    events: list[str] = []
    _record_connect(monkeypatch, events)
    spy_unlink(monkeypatch, events)
    seen: list[tuple[list[str], bool]] = []

    def check_before_replace() -> None:
        in_main = EXTRA_ALERT_ID in alert_ids(main_file_dump(paths.app_db))
        seen.append((existing(app_sidecars(paths)), in_main))

    spy_replace(monkeypatch, events, before=check_before_replace)

    _rebuild(paths)

    order = ["open:app.db", "close:app.db", "app.db-wal", "app.db-shm", "replace"]
    assert [e for e in events if e in order][: len(order)] == order
    assert seen == [([], True)]


def _record_connect(monkeypatch: pytest.MonkeyPatch, events: list[str]) -> None:
    """`seed_reset.connect`의 열기·닫기를 기록한다."""
    real_connect = seed_reset.connect

    @contextmanager
    def recording(db_path: Path, **kwargs: str) -> Iterator[sqlite3.Connection]:
        events.append(f"open:{Path(db_path).name}")
        with real_connect(db_path, **kwargs) as conn:
            yield conn
        events.append(f"close:{Path(db_path).name}")

    monkeypatch.setattr(seed_reset, "connect", recording)
