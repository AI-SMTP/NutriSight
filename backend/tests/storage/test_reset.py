"""교체 뒤 정리(`finish_cleanup`) 테스트 (스펙 3.8 4단계).

실제 시드를 한 번 적재한 DB(`cleanup_pending=True`)를 테스트마다 복사해 쓴다.
장애 주입은 정리 함수가 정의된 `app.storage.seed_reset` 모듈의 속성을 덮어쓴다.
"""

from __future__ import annotations

import shutil
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from pathlib import Path

import pytest

from app.config import DEFAULT_SEED_PATH, StoragePaths
from app.nutrition.fake import FakeNutritionEngine
from app.storage import seed_reset
from app.storage.db import connect
from app.storage.errors import ResetCleanupError
from app.storage.photos import new_photo_id, save_photo_bytes
from app.storage.seed import CLEANUP_PENDING_KEY, build_database, finish_cleanup, load_seed_file

DEMO = date(2026, 12, 5)
CHECKPOINT_SUFFIXES = ("", "-wal", "-shm")


@pytest.fixture(scope="module")
def pending_db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """실제 시드를 `cleanup_pending=True`로 한 번 적재한 DB. 테스트는 복사본만 쓴다."""
    path = tmp_path_factory.mktemp("pending") / "app.db"
    seed = load_seed_file(DEFAULT_SEED_PATH)
    build_database(path, seed, DEMO, FakeNutritionEngine(), cleanup_pending=True)
    return path


@pytest.fixture
def paths(tmp_path: Path, pending_db: Path) -> StoragePaths:
    """교체 직후 상태: 표시가 있는 `app.db`, 대화 DB와 보조 파일, 사진 2장."""
    var_dir = tmp_path / "var"
    var_dir.mkdir()
    result = StoragePaths(
        app_db=var_dir / "app.db",
        checkpoints_db=var_dir / "checkpoints.db",
        photos_dir=var_dir / "photos",
        app_lock=var_dir / "app.lock",
    )
    shutil.copyfile(pending_db, result.app_db)
    for path in _checkpoint_files(result):
        path.write_bytes(b"checkpoint")
    for _ in range(2):
        save_photo_bytes(result.photos_dir, new_photo_id(), b"jpeg")
    return result


def _checkpoint_files(paths: StoragePaths) -> list[Path]:
    base = paths.checkpoints_db
    return [base.with_name(f"{base.name}{suffix}") for suffix in CHECKPOINT_SUFFIXES]


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
