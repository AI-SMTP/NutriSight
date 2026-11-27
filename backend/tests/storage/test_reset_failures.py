"""리셋 실패 경로 테스트 (스펙 3.8 1~4단계, T10.2).

기준: 교체 전 실패에서는 기존 `app.db`의 커밋 데이터(본체 + WAL 조회 결과)가 리셋 전과 같고,
임시 파일 삭제를 시도한다. 장애 주입·스파이는 `app.storage.seed_reset` 모듈 속성을 덮어쓴다.
"""

from __future__ import annotations

import copy
import json
import logging
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
from app.storage.errors import (
    DemoDateRangeError,
    ResetBusyError,
    ResetCleanupError,
    SeedError,
    StoragePrepareError,
    StorageReplaceError,
)
from app.storage.seed import CLEANUP_PENDING_KEY, load_seed_file, rebuild_storage
from app.storage.seed_load import build_database as real_build_database
from tests.storage.demo import DEMO
from tests.storage.dump import TableDump, table_dump
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
)
from tests.storage.rows import insert_alert

TMP_NAME = "app.db.tmp"


@pytest.fixture
def paths(tmp_path: Path, seeded_db: Path) -> StoragePaths:
    """커밋된 경고 1행이 WAL에 남은 기존 `app.db`(`app.db-wal`·`app.db-shm` 있음)."""
    result = make_paths(tmp_path / "var")
    install_wal_db(seeded_db, result.app_db)
    return result


@pytest.fixture
def before(tmp_path: Path, paths: StoragePaths) -> TableDump:
    """리셋 전 기존 DB의 조회 결과. 복사본에서 읽어 원본 파일을 바꾸지 않는다."""
    dump = snapshot_dump(paths, tmp_path / "before")
    assert EXTRA_ALERT_ID in alert_ids(dump)
    return dump


def _rebuild(
    paths: StoragePaths, seed_path: Path = DEFAULT_SEED_PATH, demo_date: date = DEMO
) -> None:
    rebuild_storage(paths, seed_path, demo_date, FakeNutritionEngine())


def _spy_build(monkeypatch: pytest.MonkeyPatch, calls: list[str]) -> None:
    def wrapper(db_path: Path, *args: object, **kwargs: object) -> object:
        calls.append(db_path.name)
        return real_build_database(db_path, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(seed_reset, "build_database", wrapper)


def _leave_tmp(paths: StoragePaths, pending_db: Path) -> None:
    shutil.copyfile(pending_db, tmp_files(paths)[0])


# 1단계: 시드·시연일·임시 DB --------------------------------------------------


def _unserved_slot_seed(tmp_path: Path) -> Path:
    """미배식 칸(slot_5)에 칸별 섭취가 있는 시드 파일."""
    data = json.loads(DEFAULT_SEED_PATH.read_text(encoding="utf-8"))
    order = next(o for o in data["meal_orders"] if o["meal_order_id"] == "NS02_D-2_lunch")
    order["slot_intakes"].append({**copy.deepcopy(order["slot_intakes"][0]), "slot_id": "slot_5"})
    path = tmp_path / "bad_seed.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def test_rebuild_storage_unserved_slot_seed_keeps_existing_db(
    tmp_path: Path, paths: StoragePaths, before: TableDump, monkeypatch: pytest.MonkeyPatch
) -> None:
    unlinked: list[str] = []
    built: list[str] = []
    replaced: list[str] = []
    spy_unlink(monkeypatch, unlinked)
    _spy_build(monkeypatch, built)
    spy_replace(monkeypatch, replaced)

    with pytest.raises(SeedError, match="미배식"):
        _rebuild(paths, seed_path=_unserved_slot_seed(tmp_path))

    assert built == []
    assert replaced == []
    assert TMP_NAME in unlinked
    assert existing(tmp_files(paths)) == []
    assert existing(app_sidecars(paths)) == ["app.db-wal", "app.db-shm"]
    assert table_dump(paths.app_db) == before


def test_rebuild_storage_load_integrity_error_cleans_tmp(
    paths: StoragePaths, before: TableDump, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed = load_seed_file(DEFAULT_SEED_PATH)
    duplicated = seed.model_copy(update={"patients": (*seed.patients, seed.patients[0])})
    monkeypatch.setattr(seed_reset, "load_seed_file", lambda path: duplicated)
    unlinked: list[str] = []
    built: list[str] = []
    spy_unlink(monkeypatch, unlinked)
    _spy_build(monkeypatch, built)

    with pytest.raises(SeedError) as info:
        _rebuild(paths)

    assert isinstance(info.value.__cause__, sqlite3.IntegrityError)
    assert built == [TMP_NAME]
    assert unlinked.count(TMP_NAME) == 2  # 1단계 남은 파일 정리 + finally 정리
    assert existing(tmp_files(paths)) == []
    assert table_dump(paths.app_db) == before


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (sqlite3.IntegrityError("주입한 제약 위반"), SeedError),
        (sqlite3.OperationalError("주입한 디스크 가득 참"), StoragePrepareError),
        (OSError("주입한 I/O 오류"), StoragePrepareError),
    ],
    ids=["integrity", "sqlite", "os"],
)
def test_rebuild_storage_build_errors_are_wrapped(
    paths: StoragePaths,
    before: TableDump,
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    expected: type[Exception],
) -> None:
    def failing_build(db_path: Path, *args: object, **kwargs: object) -> None:
        db_path.write_bytes(b"partial")
        raise error

    monkeypatch.setattr(seed_reset, "build_database", failing_build)

    with pytest.raises(expected) as info:
        _rebuild(paths)

    assert info.value.__cause__ is error
    assert existing(tmp_files(paths)) == []
    assert table_dump(paths.app_db) == before


def test_rebuild_storage_demo_date_out_of_range_skips_build(
    paths: StoragePaths, before: TableDump, pending_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _leave_tmp(paths, pending_db)
    unlinked: list[str] = []
    built: list[str] = []
    spy_unlink(monkeypatch, unlinked)
    _spy_build(monkeypatch, built)

    with pytest.raises(DemoDateRangeError):
        _rebuild(paths, demo_date=date(1, 1, 1))

    assert built == []
    assert TMP_NAME in unlinked
    assert existing(tmp_files(paths)) == []
    assert table_dump(paths.app_db) == before


def test_rebuild_storage_leftover_tmp_delete_failure(
    paths: StoragePaths, before: TableDump, pending_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _leave_tmp(paths, pending_db)
    replaced: list[str] = []
    spy_unlink(monkeypatch, [], fail_when=lambda path: path.name == TMP_NAME)
    spy_replace(monkeypatch, replaced)

    with pytest.raises(StoragePrepareError, match=TMP_NAME):
        _rebuild(paths)

    assert replaced == []
    assert table_dump(paths.app_db) == before


def test_rebuild_storage_var_dir_create_failure(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    blocker = tmp_path / "blocker"
    blocker.write_bytes(b"file, not a directory")
    paths = make_paths(blocker / "var")

    with caplog.at_level(logging.ERROR, logger=seed_reset.__name__):
        with pytest.raises(StoragePrepareError, match="저장소 디렉토리") as info:
            _rebuild(paths)

    assert isinstance(info.value.__cause__, OSError)
    # 디렉토리가 없으니 지울 임시 파일도 없다. 삭제 실패 로그를 남기지 않는다.
    assert caplog.records == []


# 2단계: 기존 WAL 반영 --------------------------------------------------------


def test_rebuild_storage_read_snapshot_raises_busy(
    tmp_path: Path, seeded_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = var_paths(tmp_path)
    shutil.copyfile(seeded_db, paths.app_db)
    monkeypatch.setattr(seed_reset, "CHECKPOINT_BUSY_TIMEOUT_MS", 10)
    unlinked: list[str] = []
    replaced: list[str] = []

    with _snapshot_and_late_commit(paths.app_db):
        spy_unlink(monkeypatch, unlinked)
        spy_replace(monkeypatch, replaced)
        with pytest.raises(ResetBusyError):
            _rebuild(paths)
        sidecars_during = existing(app_sidecars(paths))

    assert replaced == []
    assert not {"app.db-wal", "app.db-shm"} & set(unlinked)
    assert sidecars_during == ["app.db-wal", "app.db-shm"]
    assert existing(tmp_files(paths)) == []
    assert {"A_before", "A_after"} <= alert_ids(table_dump(paths.app_db))


@contextmanager
def _snapshot_and_late_commit(app_db: Path) -> Iterator[None]:
    """커밋 1건 → 읽기 스냅샷(`BEGIN; SELECT`) → 다른 연결로 커밋 1건을 더 한 상태를 유지한다."""
    writer = sqlite3.connect(app_db)
    reader = sqlite3.connect(app_db, isolation_level=None)
    try:
        writer.execute("PRAGMA journal_mode = WAL")
        insert_alert(writer, alert_id="A_before", patient_id="NS01")
        writer.commit()
        reader.execute("BEGIN")
        reader.execute("SELECT count(*) FROM alerts").fetchone()
        insert_alert(writer, alert_id="A_after", patient_id="NS01")
        writer.commit()
        yield
    finally:
        reader.close()
        writer.close()


def test_rebuild_storage_sidecar_delete_failure_after_checkpoint(
    paths: StoragePaths, before: TableDump, monkeypatch: pytest.MonkeyPatch
) -> None:
    replaced: list[str] = []
    spy_unlink(monkeypatch, [], fail_when=lambda path: path.name == "app.db-wal")
    spy_replace(monkeypatch, replaced)

    with pytest.raises(StoragePrepareError, match="app.db-wal"):
        _rebuild(paths)

    assert replaced == []
    assert existing(tmp_files(paths)) == []
    assert table_dump(paths.app_db) == before


class _CheckpointProxy:
    """`wal_checkpoint` 실행만 바꾸는 연결 대리 객체.

    `result`가 없으면 체크포인트가 `sqlite3.OperationalError`로 실패하고, 있으면 실제
    체크포인트 대신 그 반환 행을 돌려준다.
    """

    def __init__(
        self, conn: sqlite3.Connection, result: tuple[int, int, int] | None = None
    ) -> None:
        self._conn = conn
        self._result = result

    def execute(self, sql: str, *args: object) -> object:
        if "wal_checkpoint" not in sql:
            return self._conn.execute(sql, *args)
        if self._result is None:
            raise sqlite3.OperationalError("주입한 체크포인트 실패")
        return self._conn.execute("SELECT ?, ?, ?", self._result)

    def __getattr__(self, name: str) -> object:
        return getattr(self._conn, name)


def _inject_connect_error(
    monkeypatch: pytest.MonkeyPatch, where: str, result: tuple[int, int, int] | None = None
) -> None:
    real_connect = seed_reset.connect

    @contextmanager
    def failing(db_path: Path, **kwargs: bool) -> Iterator[object]:
        if where == "connect":
            raise sqlite3.DatabaseError("주입한 연결 실패")
        with real_connect(db_path, **kwargs) as conn:
            yield _CheckpointProxy(conn, result)

    monkeypatch.setattr(seed_reset, "connect", failing)


@pytest.mark.parametrize("where", ["connect", "checkpoint"])
def test_rebuild_storage_existing_db_error_keeps_sidecars(
    paths: StoragePaths, before: TableDump, monkeypatch: pytest.MonkeyPatch, where: str
) -> None:
    _inject_connect_error(monkeypatch, where)
    unlinked: list[str] = []
    replaced: list[str] = []
    spy_unlink(monkeypatch, unlinked)
    spy_replace(monkeypatch, replaced)

    with pytest.raises(StoragePrepareError) as info:
        _rebuild(paths)

    assert isinstance(info.value.__cause__, sqlite3.Error)
    assert replaced == []
    assert not {"app.db-wal", "app.db-shm"} & set(unlinked)
    assert existing(app_sidecars(paths)) == ["app.db-wal", "app.db-shm"]
    assert TMP_NAME in unlinked
    assert existing(tmp_files(paths)) == []
    monkeypatch.undo()
    assert table_dump(paths.app_db) == before


def test_rebuild_storage_corrupt_existing_db_raises_prepare_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = var_paths(tmp_path)
    paths.app_db.write_bytes(b"not a sqlite database" * 100)
    replaced: list[str] = []
    spy_replace(monkeypatch, replaced)

    with pytest.raises(StoragePrepareError):
        _rebuild(paths)

    assert replaced == []
    assert paths.app_db.read_bytes() == b"not a sqlite database" * 100
    assert existing(app_sidecars(paths)) == []
    assert existing(tmp_files(paths)) == []


def test_rebuild_storage_negative_checkpoint_log_raises_prepare_error(
    paths: StoragePaths, before: TableDump, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`log = -1`(WAL 모드가 아님 등)은 반영 여부를 확인할 수 없으므로 교체하지 않는다."""
    _inject_connect_error(monkeypatch, "checkpoint", result=(0, -1, -1))
    unlinked: list[str] = []
    replaced: list[str] = []
    spy_unlink(monkeypatch, unlinked)
    spy_replace(monkeypatch, replaced)

    with pytest.raises(StoragePrepareError, match="log=-1"):
        _rebuild(paths)

    assert replaced == []
    assert not {"app.db-wal", "app.db-shm"} & set(unlinked)
    assert existing(app_sidecars(paths)) == ["app.db-wal", "app.db-shm"]
    assert existing(tmp_files(paths)) == []
    monkeypatch.undo()
    assert table_dump(paths.app_db) == before


def test_rebuild_storage_partial_checkpoint_raises_busy(
    paths: StoragePaths, before: TableDump, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`busy == 0`이어도 `log != checkpointed`이면 반영하지 못한 프레임이 있어 교체하지 않는다."""
    _inject_connect_error(monkeypatch, "checkpoint", result=(0, 5, 3))
    replaced: list[str] = []
    spy_replace(monkeypatch, replaced)

    with pytest.raises(ResetBusyError, match="log=5, checkpointed=3"):
        _rebuild(paths)

    assert replaced == []
    assert existing(app_sidecars(paths)) == ["app.db-wal", "app.db-shm"]
    monkeypatch.undo()
    assert table_dump(paths.app_db) == before


def test_rebuild_storage_checkpoint_connection_keeps_wal_on_close(
    paths: StoragePaths, monkeypatch: pytest.MonkeyPatch
) -> None:
    """2단계 연결은 `checkpoint_on_close=False`로 연다(PRAGMA보다 먼저 플래그를 켠다)."""
    real_connect = seed_reset.connect
    opened: list[tuple[str, dict[str, object]]] = []

    @contextmanager
    def recording(db_path: Path, **kwargs: bool) -> Iterator[sqlite3.Connection]:
        opened.append((Path(db_path).name, kwargs))
        with real_connect(db_path, **kwargs) as conn:
            yield conn

    monkeypatch.setattr(seed_reset, "connect", recording)

    _rebuild(paths)

    assert opened[0] == ("app.db", {"checkpoint_on_close": False})


# 3단계: 본체 없는 보조 파일과 교체 ---------------------------------------------


def test_rebuild_storage_orphan_sidecar_delete_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = var_paths(tmp_path)
    for path in app_sidecars(paths):
        path.write_bytes(b"orphan")
    replaced: list[str] = []
    spy_unlink(monkeypatch, [], fail_when=lambda path: path.name == "app.db-wal")
    spy_replace(monkeypatch, replaced)

    with pytest.raises(StoragePrepareError, match="app.db-wal"):
        _rebuild(paths)

    assert replaced == []
    assert not paths.app_db.exists()
    assert existing(tmp_files(paths)) == []


def test_rebuild_storage_replace_failure_removes_tmp(
    paths: StoragePaths, before: TableDump, monkeypatch: pytest.MonkeyPatch
) -> None:
    spy_replace(monkeypatch, [], fail=True)

    with pytest.raises(StorageReplaceError) as info:
        _rebuild(paths)

    assert isinstance(info.value.__cause__, OSError)
    assert existing(tmp_files(paths)) == []
    assert table_dump(paths.app_db) == before


def test_rebuild_storage_replace_failure_logs_tmp_delete_failure(
    paths: StoragePaths,
    before: TableDump,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    replaced: list[str] = []
    spy_replace(monkeypatch, replaced, fail=True)
    spy_unlink(monkeypatch, [], fail_when=lambda path: path.name == TMP_NAME and bool(replaced))

    with caplog.at_level(logging.ERROR, logger=seed_reset.__name__):
        with pytest.raises(StorageReplaceError):
            _rebuild(paths)

    assert any(TMP_NAME in record.getMessage() for record in caplog.records)
    assert TMP_NAME in existing(tmp_files(paths))
    assert table_dump(paths.app_db) == before


# 4단계: 교체 뒤 정리 ----------------------------------------------------------


def test_rebuild_storage_cleanup_failure_keeps_new_db_and_mark(
    paths: StoragePaths, fresh_dump: TableDump, monkeypatch: pytest.MonkeyPatch
) -> None:
    def failing_clear(photos_dir: Path) -> None:
        raise PermissionError(f"주입한 사진 삭제 실패: {photos_dir}")

    monkeypatch.setattr(seed_reset, "clear_photos", failing_clear)

    with pytest.raises(ResetCleanupError) as info:
        _rebuild(paths)

    dump = table_dump(paths.app_db)
    mark = [row for row in dump["seed_meta"] if row[0] == CLEANUP_PENDING_KEY]
    assert info.value.failures == ("photos",)
    assert mark == [(CLEANUP_PENDING_KEY, "1")]
    assert {**dump, "seed_meta": [r for r in dump["seed_meta"] if r not in mark]} == fresh_dump

    monkeypatch.undo()
    _rebuild(paths)

    assert table_dump(paths.app_db) == fresh_dump
