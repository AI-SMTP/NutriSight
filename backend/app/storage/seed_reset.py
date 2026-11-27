"""리셋 절차와 교체 뒤 정리 (스펙 3.8).

장애 주입 지점: 테스트는 이 모듈의 속성을 덮어쓴다.
- 파일 삭제는 `_unlink_if_exists(path)`로 한다.
- 사진 삭제는 이 모듈에 import한 `clear_photos`, 정리 표시 삭제 연결은 `connect`로 한다.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from app.config import StoragePaths
from app.storage.db import connect
from app.storage.errors import ResetCleanupError
from app.storage.photos import clear_photos
from app.storage.seed_load import CLEANUP_PENDING_KEY

logger = logging.getLogger(__name__)

# SQLite가 DB 본체 옆에 만드는 보조 파일 접미사.
SIDECAR_SUFFIXES = ("-wal", "-shm")

# `ResetCleanupError.failures`에 담는 실패 항목 이름.
CHECKPOINTS_ITEM = "checkpoints.db"
PHOTOS_ITEM = "photos"
CLEANUP_PENDING_ITEM = CLEANUP_PENDING_KEY


def _unlink_if_exists(path: Path) -> None:
    """`path`를 지운다. 없으면 성공으로 친다. 그 밖의 `OSError`는 그대로 던진다."""
    path.unlink(missing_ok=True)


def _with_sidecars(db_path: Path) -> tuple[Path, ...]:
    """DB 본체와 `-wal`·`-shm` 보조 파일 경로."""
    return (db_path, *(db_path.with_name(f"{db_path.name}{s}") for s in SIDECAR_SUFFIXES))


def _remove_checkpoints(paths: StoragePaths) -> bool:
    """대화 DB와 보조 파일을 모두 시도해 지운다. 하나라도 실패하면 False."""
    ok = True
    for path in _with_sidecars(paths.checkpoints_db):
        try:
            _unlink_if_exists(path)
        except OSError:
            logger.exception("대화 DB 파일을 지우지 못했다: %s", path)
            ok = False
    return ok


def _remove_photos(paths: StoragePaths) -> bool:
    """사진 디렉토리의 파일을 지운다. 실패하면 False."""
    try:
        clear_photos(paths.photos_dir)
    except OSError:
        logger.exception("사진 파일을 지우지 못했다: %s", paths.photos_dir)
        return False
    return True


def _delete_cleanup_mark(app_db: Path) -> bool:
    """`seed_meta`의 정리 대기 표시 행을 지우고 커밋한다. 실패하면 False."""
    try:
        with connect(app_db) as conn:
            conn.execute("DELETE FROM seed_meta WHERE key = ?", (CLEANUP_PENDING_KEY,))
    except sqlite3.Error:
        logger.exception("정리 대기 표시를 지우지 못했다: %s", app_db)
        return False
    return True


def finish_cleanup(paths: StoragePaths) -> None:
    """교체 뒤 정리(스펙 3.8 4단계). 대화 DB·사진을 지운 뒤 정리 대기 표시를 지운다.

    두 파일 정리를 모두 시도하고 실패 항목을 모은다. 둘 다 성공했을 때만 표시를 지운다.
    없는 파일·디렉토리는 성공으로 치므로 여러 번 불러도 안전하다. 실패 항목이 있으면 표시를
    남긴 채 `ResetCleanupError`(항목: `checkpoints.db`, `photos`, `cleanup_pending`)를 던진다.
    """
    failures: list[str] = []
    if not _remove_checkpoints(paths):
        failures.append(CHECKPOINTS_ITEM)
    if not _remove_photos(paths):
        failures.append(PHOTOS_ITEM)
    if not failures and not _delete_cleanup_mark(paths.app_db):
        failures.append(CLEANUP_PENDING_ITEM)
    if failures:
        raise ResetCleanupError(tuple(failures))
