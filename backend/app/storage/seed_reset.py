"""원자적 리셋 절차와 교체 뒤 정리 (스펙 3.8).

`rebuild_storage` 순서: 1 준비(시드 검증 → 시연일 범위 → 남은 임시 파일 삭제 → 임시 DB 적재)
→ 2 기존 WAL 반영(체크포인트 → 연결 닫기 → 보조 파일 삭제) → 3 본체 없는 보조 파일 삭제 →
`_replace_file`(`os.replace`) 교체 → 4 정리(`finish_cleanup`) → 5 행 수 반환.
교체 전에 실패하면 기존 `app.db`의 커밋 데이터는 그대로이고 임시 파일 삭제를 시도한다.

장애 주입 지점: 테스트는 이 모듈의 속성을 덮어쓴다.
- 파일 삭제는 `_unlink_if_exists(path)`, 교체는 `_replace_file(src, dst)`로 한다.
- 체크포인트 대기 시간은 모듈 상수 `CHECKPOINT_BUSY_TIMEOUT_MS`다.
- 이 모듈에 import한 `load_seed_file`·`build_database`·`clear_photos`·`connect`도 덮어쓸 수 있다.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from app.config import Settings, StoragePaths, resolve_demo_date, storage_paths
from app.nutrition.types import NutritionEngine
from app.storage.app_lock import AppLock
from app.storage.db import connect
from app.storage.errors import (
    ResetBusyError,
    ResetCleanupError,
    SeedError,
    StoragePrepareError,
    StorageReplaceError,
)
from app.storage.photos import clear_photos
from app.storage.queries import get_demo_date
from app.storage.seed_file import check_demo_date_range, load_seed_file
from app.storage.seed_load import CLEANUP_PENDING_KEY, SeedCounts, build_database, build_engine

logger = logging.getLogger(__name__)

# 리셋 2단계 체크포인트가 다른 연결을 기다리는 최대 시간(밀리초).
CHECKPOINT_BUSY_TIMEOUT_MS = 5000

# SQLite가 DB 본체 옆에 만드는 보조 파일 접미사.
SIDECAR_SUFFIXES = ("-wal", "-shm")
# 임시 DB(`journal_mode=DELETE`로 만든다)와 강제 종료 뒤 남을 수 있는 보조 파일 접미사.
TMP_SUFFIX = ".tmp"
TMP_SIDECAR_SUFFIXES = ("-journal", *SIDECAR_SUFFIXES)

# `ResetCleanupError.failures`에 담는 실패 항목 이름.
CHECKPOINTS_ITEM = "checkpoints.db"
PHOTOS_ITEM = "photos"
CLEANUP_PENDING_ITEM = CLEANUP_PENDING_KEY


@dataclass(frozen=True)
class ResetResult:
    """리셋으로 새로 적재한 시연일과 주요 테이블 행 수."""

    demo_date: date
    patients: int
    meal_orders: int
    daily_intakes: int
    alerts: int


# --- 파일 경로·삭제 --------------------------------------------------------------


def _unlink_if_exists(path: Path) -> None:
    """`path`를 지운다. 없으면 성공으로 친다. 그 밖의 `OSError`는 그대로 던진다."""
    path.unlink(missing_ok=True)


def _with_suffixes(base: Path, suffixes: Iterable[str]) -> tuple[Path, ...]:
    return tuple(base.with_name(f"{base.name}{suffix}") for suffix in suffixes)


def _with_sidecars(db_path: Path) -> tuple[Path, ...]:
    """DB 본체와 `-wal`·`-shm` 보조 파일 경로."""
    return (db_path, *_with_suffixes(db_path, SIDECAR_SUFFIXES))


def _tmp_db(paths: StoragePaths) -> Path:
    return paths.app_db.with_name(f"{paths.app_db.name}{TMP_SUFFIX}")


def _tmp_files(paths: StoragePaths) -> tuple[Path, ...]:
    """`app.db.tmp`와 `-journal`·`-wal`·`-shm`."""
    tmp = _tmp_db(paths)
    return (tmp, *_with_suffixes(tmp, TMP_SIDECAR_SUFFIXES))


def _remove_or_raise(files: Iterable[Path], what: str) -> None:
    """파일을 차례로 지운다. 하나라도 실패하면 `StoragePrepareError`로 멈춘다."""
    for path in files:
        try:
            _unlink_if_exists(path)
        except OSError as err:
            raise StoragePrepareError(f"{what}을 지우지 못했다: {path}") from err


def _replace_file(src: Path, dst: Path) -> None:
    """`src`를 `dst`로 원자적으로 옮긴다(`os.replace`). 테스트의 교체 장애 주입 지점이다."""
    os.replace(src, dst)


def _discard_tmp(paths: StoragePaths) -> None:
    """교체 전 실패 뒤 임시 파일 삭제를 시도한다. 실패는 로그로만 남긴다(원래 예외 우선).

    저장소 디렉토리가 없거나 디렉토리가 아니면 지울 임시 파일도 없으므로 아무것도 하지 않는다.
    """
    if not paths.app_db.parent.is_dir():
        return
    for path in _tmp_files(paths):
        try:
            _unlink_if_exists(path)
        except OSError:
            logger.exception("임시 파일을 지우지 못했다: %s", path)


# --- 리셋 1~3단계 ---------------------------------------------------------------


def _prepare_tmp(
    paths: StoragePaths, seed_path: Path, demo_date: date, engine: NutritionEngine
) -> SeedCounts:
    """1단계: 시드 검증과 시연일 범위 검사 뒤 남은 임시 파일을 지우고 임시 DB를 만든다."""
    seed = load_seed_file(seed_path)
    check_demo_date_range(seed, demo_date)
    try:
        paths.app_db.parent.mkdir(parents=True, exist_ok=True)
    except OSError as err:
        raise StoragePrepareError(
            f"저장소 디렉토리를 만들지 못했다: {paths.app_db.parent}"
        ) from err
    _remove_or_raise(_tmp_files(paths), "남은 임시 파일")
    tmp = _tmp_db(paths)
    try:
        return build_database(tmp, seed, demo_date, engine, cleanup_pending=True)
    except sqlite3.IntegrityError as err:
        raise SeedError(f"임시 DB 적재 중 제약 위반: {err}") from err
    except (sqlite3.Error, OSError) as err:
        raise StoragePrepareError(f"임시 DB를 만들지 못했다: {tmp}: {err}") from err


def _checkpoint_existing(app_db: Path) -> None:
    """2단계: 기존 `app.db`의 WAL을 본체에 모두 반영하고 연결을 닫은 뒤 보조 파일을 지운다.

    반환 행 판정은 `_check_checkpoint_result`가 한다. 연결·체크포인트의 `sqlite3.Error`는
    `StoragePrepareError`다. 실패하면 보조 파일을 지우지 않는다. 연결은
    `checkpoint_on_close=False`로 열어, 어떤 PRAGMA보다 먼저 닫을 때의 자동 체크포인트를 끈다.
    그래서 실패 경로에서 닫아도 SQLite가 보조 파일을 지우지 않고, 성공 경로의 삭제는 이 함수가 한다.
    """
    if not app_db.exists():
        return
    try:
        with connect(app_db, checkpoint_on_close=False) as conn:
            conn.execute(f"PRAGMA busy_timeout = {int(CHECKPOINT_BUSY_TIMEOUT_MS)}")
            busy, log, checkpointed = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
    except sqlite3.Error as err:
        raise StoragePrepareError(f"기존 DB의 WAL을 반영하지 못했다: {app_db}: {err}") from err
    _check_checkpoint_result(app_db, busy, log, checkpointed)
    _remove_or_raise(_with_suffixes(app_db, SIDECAR_SUFFIXES), "기존 DB 보조 파일")


def _check_checkpoint_result(app_db: Path, busy: int, log: int, checkpointed: int) -> None:
    """`wal_checkpoint(TRUNCATE)` 반환 행이 성공(`busy == 0`, `log == checkpointed >= 0`)인지 본다.

    다른 연결 때문에 반영하지 못했으면(`busy != 0` 또는 `log != checkpointed`) `ResetBusyError`다.
    `log < 0`(WAL 모드가 아니거나 WAL을 열지 못함)은 반영 여부를 확인할 수 없는 상태라 대기로
    풀리지 않으므로 `StoragePrepareError`로 둔다. `busy`를 먼저 본다.
    """
    detail = f"busy={busy}, log={log}, checkpointed={checkpointed}"
    busy_message = (
        f"기존 DB의 WAL을 모두 반영하지 못했다({detail}). "
        "DB를 연 다른 프로그램을 닫은 뒤 다시 실행하라"
    )
    if busy != 0:
        raise ResetBusyError(busy_message)
    if log < 0:
        raise StoragePrepareError(f"기존 DB의 WAL 상태를 확인하지 못했다({detail}): {app_db}")
    if log != checkpointed:
        raise ResetBusyError(busy_message)


def _remove_orphan_sidecars(app_db: Path) -> None:
    """3단계 앞부분: 본체 없이 남은 `app.db-wal`·`app.db-shm`이 새 DB에 붙지 않게 지운다."""
    if not app_db.exists():
        _remove_or_raise(_with_suffixes(app_db, SIDECAR_SUFFIXES), "본체 없는 보조 파일")


def _install(tmp: Path, app_db: Path) -> None:
    """3단계: 같은 디렉토리 안의 원자적 교체. 실패하면 `StorageReplaceError`."""
    try:
        _replace_file(tmp, app_db)
    except OSError as err:
        raise StorageReplaceError(f"임시 DB로 {app_db}를 교체하지 못했다: {err}") from err


# --- 진입점 ---------------------------------------------------------------------


def rebuild_storage(
    paths: StoragePaths, seed_path: Path, demo_date: date, engine: NutritionEngine
) -> ResetResult:
    """시드로 `app.db`를 원자적으로 다시 만들고 대화 DB·사진을 정리한다(스펙 3.8 1~5단계).

    앱 잠금을 쥔 상태에서만 부른다. 교체 전 실패(`SeedError`, `DemoDateRangeError`,
    `StoragePrepareError`, `ResetBusyError`, `StorageReplaceError`)에서는 기존 DB를 그대로 두고
    임시 파일 삭제를 시도한다. 교체 뒤 정리 실패는 새 DB와 정리 대기 표시를 남기고
    `ResetCleanupError`를 던진다.
    """
    replaced = False
    try:
        counts = _prepare_tmp(paths, seed_path, demo_date, engine)
        _checkpoint_existing(paths.app_db)
        _remove_orphan_sidecars(paths.app_db)
        _install(_tmp_db(paths), paths.app_db)
        replaced = True
    finally:
        if not replaced:
            _discard_tmp(paths)
    finish_cleanup(paths)
    return ResetResult(
        demo_date=demo_date,
        patients=counts.patients,
        meal_orders=counts.meal_orders,
        daily_intakes=counts.daily_intakes,
        alerts=counts.alerts,
    )


def reset_storage(settings: Settings, *, demo_date: date) -> ResetResult:
    """CLI 리셋 진입점. 앱 잠금을 잡고 설정의 경로·시드·엔진으로 `rebuild_storage`를 부른다.

    잠금을 잡지 못하면 DB를 건드리지 않고 `AppLockedError`를 그대로 전달한다.
    """
    paths = storage_paths(settings)
    with AppLock(paths.app_lock):
        return rebuild_storage(paths, settings.seed_path, demo_date, build_engine(settings))


# --- 4단계: 교체 뒤 정리 ---------------------------------------------------------


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


# --- 앱 시작: 자동 시드와 정리 이어 가기 -------------------------------------------


def ensure_storage(settings: Settings, *, today: date | None = None) -> None:
    """앱 시작 때 저장소를 쓸 수 있는 상태로 맞춘다(스펙 3.8 자동 시드·복구 경로).

    lifespan이 앱 잠금을 잡은 뒤에 부른다. 시연일은 `resolve_demo_date(None, settings, today)`다.
    - `app.db`가 없으면 `rebuild_storage`로 시드 상태를 만든다. 남은 사진·대화 DB·보조 파일·
      임시 파일도 이 절차가 지운다.
    - `app.db`가 있으면 업무 데이터와 남은 `app.db.tmp`를 건드리지 않는다. 정리 대기 표시가 있을
      때만 `finish_cleanup`을 다시 실행한다(실패하면 `ResetCleanupError`).
    - `DEMO_DATE`가 없고 `seed_meta.demo_date`가 오늘과 다르면 WARNING 로그를 남긴다.
    """
    current = today or date.today()
    demo_date = resolve_demo_date(None, settings, current)
    paths = storage_paths(settings)
    if not paths.app_db.exists():
        rebuild_storage(paths, settings.seed_path, demo_date, build_engine(settings))
        return
    pending, seeded_date = _read_seed_state(paths.app_db, read_date=settings.demo_date is None)
    if seeded_date is not None and seeded_date != current:
        logger.warning(
            "시드 기준일 %s, 오늘 %s. 앱을 끄고 리셋하면 오늘 기준으로 다시 맞춘다",
            seeded_date.isoformat(),
            current.isoformat(),
        )
    if pending:
        finish_cleanup(paths)


def _read_seed_state(app_db: Path, *, read_date: bool) -> tuple[bool, date | None]:
    """`seed_meta`에서 정리 대기 표시 여부와(`read_date`이면) 시연일을 읽는다."""
    with connect(app_db) as conn:
        row = conn.execute(
            "SELECT 1 FROM seed_meta WHERE key = ?", (CLEANUP_PENDING_KEY,)
        ).fetchone()
        seeded_date = get_demo_date(conn) if read_date else None
    return row is not None, seeded_date
