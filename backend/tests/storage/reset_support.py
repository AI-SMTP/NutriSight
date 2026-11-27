"""리셋 테스트(`test_reset*.py`)가 함께 쓰는 준비·관찰 도우미.

장애 주입과 스파이는 함수가 정의된 `app.storage.seed_reset` 모듈의 속성을 덮어쓴다.
- 파일 삭제: `seed_reset._unlink_if_exists`
- 교체: `seed_reset._replace_file`
- 임시 DB 적재: `seed_reset.build_database`
"""

from __future__ import annotations

import shutil
import sqlite3
from collections.abc import Callable
from pathlib import Path

import pytest

from app.config import StoragePaths
from app.storage import seed_reset
from tests.storage.dump import TableDump, table_dump
from tests.storage.rows import insert_alert

EXTRA_ALERT_ID = "A_extra"
# 파일 이름 접미사는 `seed_reset`의 상수를 import하지 않고 일부러 따로 적는다. 구현 상수가
# 잘못 바뀌어도 테스트가 함께 바뀌지 않도록 독립된 기대값(oracle)으로 둔다.
SIDECAR_SUFFIXES = ("-wal", "-shm")
TMP_SUFFIXES = ("", "-journal", "-wal", "-shm")

_real_unlink = seed_reset._unlink_if_exists
_real_replace = seed_reset._replace_file


def make_paths(var_dir: Path) -> StoragePaths:
    """`var_dir` 아래 경로 묶음. 디렉토리는 만들지 않는다."""
    return StoragePaths(
        app_db=var_dir / "app.db",
        checkpoints_db=var_dir / "checkpoints.db",
        photos_dir=var_dir / "photos",
        app_lock=var_dir / "app.lock",
    )


def var_paths(tmp_path: Path) -> StoragePaths:
    """`tmp_path / "var"` 경로 묶음. `var` 디렉토리를 만든다."""
    paths = make_paths(tmp_path / "var")
    paths.app_db.parent.mkdir()
    return paths


def with_suffixes(base: Path, suffixes: tuple[str, ...]) -> list[Path]:
    return [base.with_name(f"{base.name}{suffix}") for suffix in suffixes]


def app_sidecars(paths: StoragePaths) -> list[Path]:
    """`app.db-wal`, `app.db-shm`."""
    return with_suffixes(paths.app_db, SIDECAR_SUFFIXES)


def tmp_files(paths: StoragePaths) -> list[Path]:
    """`app.db.tmp`와 그 보조 파일(`-journal`, `-wal`, `-shm`)."""
    tmp = paths.app_db.with_name(f"{paths.app_db.name}.tmp")
    return with_suffixes(tmp, TMP_SUFFIXES)


def existing(files: list[Path]) -> list[str]:
    return [path.name for path in files if path.exists()]


def install_wal_db(base_db: Path, target: Path) -> None:
    """`base_db` 복사본을 WAL 모드로 바꾸고, 경고 1행을 커밋한 뒤 WAL에 남긴 상태로 둔다.

    마지막 연결을 닫으면 SQLite가 WAL을 본체에 반영하고 지우므로, 연결이 열린 동안 본체와
    보조 파일을 복사해 두었다가 닫은 뒤 되돌려 놓는다(강제 종료 뒤와 같은 상태).
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(base_db, target)
    # 복사본은 대상 디렉토리 밖(형제 디렉토리)에 둔다. 리셋 대상 `var` 안에 흔적을 남기지 않는다.
    stage = target.parent.with_name(f"{target.parent.name}_wal_stage")
    stage.mkdir()
    conn = sqlite3.connect(target)
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA wal_autocheckpoint = 0")
        insert_alert(conn, alert_id=EXTRA_ALERT_ID, patient_id="NS01")
        conn.commit()
        for path in [target, *with_suffixes(target, SIDECAR_SUFFIXES)]:
            shutil.copyfile(path, stage / path.name)
    finally:
        conn.close()
    for staged in stage.iterdir():
        shutil.copyfile(staged, target.parent / staged.name)
    shutil.rmtree(stage)


def snapshot_dump(paths: StoragePaths, scratch: Path) -> TableDump:
    """`app.db`와 보조 파일을 `scratch`에 복사해 덤프한다. 원본 파일은 건드리지 않는다."""
    scratch.mkdir()
    for path in [paths.app_db, *app_sidecars(paths)]:
        if path.exists():
            shutil.copyfile(path, scratch / path.name)
    return table_dump(scratch / paths.app_db.name)


def alert_ids(dump: TableDump) -> set[object]:
    return {row[0] for row in dump["alerts"]}


def spy_unlink(
    monkeypatch: pytest.MonkeyPatch,
    calls: list[str],
    fail_when: Callable[[Path], bool] = lambda _: False,
) -> None:
    """`_unlink_if_exists` 호출 파일 이름을 기록한다. `fail_when`이 참이면 실패를 주입한다."""

    def wrapper(path: Path) -> None:
        calls.append(path.name)
        if fail_when(path):
            raise PermissionError(f"주입한 삭제 실패: {path}")
        _real_unlink(path)

    monkeypatch.setattr(seed_reset, "_unlink_if_exists", wrapper)


def spy_replace(
    monkeypatch: pytest.MonkeyPatch,
    calls: list[str],
    before: Callable[[], None] = lambda: None,
    fail: bool = False,
) -> None:
    """`_replace_file` 호출을 기록하고 교체 직전에 `before`를 실행한다.

    `fail`이면 실패를 주입한다.
    """

    def wrapper(src: str | Path, dst: str | Path) -> None:
        calls.append("replace")
        before()
        if fail:
            raise PermissionError(f"주입한 교체 실패: {src} -> {dst}")
        _real_replace(src, dst)

    monkeypatch.setattr(seed_reset, "_replace_file", wrapper)
