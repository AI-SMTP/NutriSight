"""리셋 CLI(`scripts.seed`) 테스트 (스펙 3.8 CLI 항목, 2절 완료 기준).

`VAR_DIR`는 autouse fixture가 `tmp_path / "var"`로 돌린다. 시드 파일 오류·잠금·형식 오류는
실제 호출로 확인하고, 교체 실패는 `seed_reset._replace_file`에, 그 밖의 저장소 오류는
`scripts.seed.reset_storage`에 주입한다.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from app.config import DEFAULT_SEED_PATH, Settings, storage_paths
from app.storage import seed_reset
from app.storage.app_lock import AppLock
from app.storage.db import connect
from app.storage.errors import (
    ResetBusyError,
    ResetCleanupError,
    StoragePrepareError,
)
from app.storage.seed import reset_storage
from scripts import seed as seed_cli
from tests.conftest import disable_dotenv
from tests.storage.dump import TableDump, main_file_dump

DEMO_ARG = "2026-12-05"
# 기존 DB는 CLI 인자와 다른 시연일로 만들어, 리셋이 일어났는지 `seed_meta`로 구분한다.
EXISTING_DEMO = date(2026, 12, 1)
INJECTED_TODAY = date(2026, 11, 27)
FORMAT_MESSAGE = "시연일 형식이 잘못됐다(YYYY-MM-DD)"
LOCKED_MESSAGE = "앱이 실행 중이다. 앱을 끈 뒤 다시 실행하라"
REPLACE_MESSAGE = "새 DB로 바꾸지 못했다. 기존 데이터는 그대로다"
HELP_PHRASE = "앱을 끈 상태에서 실행한다"


# --- 도우미 ---------------------------------------------------------------------


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch: pytest.MonkeyPatch) -> date:
    """CLI가 쓰는 오늘 날짜를 고정한다."""
    monkeypatch.setattr(seed_cli, "_today", lambda: INJECTED_TODAY)
    return INJECTED_TODAY


def _app_db() -> Path:
    return storage_paths(Settings()).app_db


def _app_lock() -> Path:
    return storage_paths(Settings()).app_lock


def _demo_date_in_db(app_db: Path) -> str:
    with connect(app_db) as conn:
        row = conn.execute("SELECT value FROM seed_meta WHERE key = 'demo_date'").fetchone()
    return row["value"]


@pytest.fixture
def existing_db() -> tuple[Path, bytes, TableDump]:
    """`EXISTING_DEMO`로 리셋한 기존 DB. (경로, 파일 바이트, 업무 데이터 덤프)를 돌려준다."""
    reset_storage(Settings(), demo_date=EXISTING_DEMO)
    app_db = _app_db()
    return app_db, app_db.read_bytes(), main_file_dump(app_db)


def _assert_unchanged(existing: tuple[Path, bytes, TableDump]) -> None:
    app_db, before_bytes, before_dump = existing
    assert app_db.read_bytes() == before_bytes
    assert main_file_dump(app_db) == before_dump


def _write_seed(tmp_path: Path, mutate: object) -> Path:
    """실제 시드를 읽어 `mutate(data)`로 고친 사본을 `tmp_path`에 쓰고 경로를 돌려준다."""
    data = json.loads(DEFAULT_SEED_PATH.read_text(encoding="utf-8"))
    mutate(data)  # type: ignore[operator]
    path = tmp_path / "bad_seed.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def _drop_patient_id(data: dict) -> None:
    del data["patients"][0]["patient_id"]


def _order_to_missing_patient(data: dict) -> None:
    data["meal_orders"][0]["patient_id"] = "NS99"


# --- 성공 경로 -------------------------------------------------------------------


def test_main_resets_with_cli_demo_date_and_prints_counts(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert seed_cli.main(["--demo-date", DEMO_ARG]) == 0

    out = capsys.readouterr().out
    assert DEMO_ARG in out
    for label, count in (("patients", 10), ("meal_orders", 240), ("daily_intakes", 70)):
        assert f"{label}: {count}" in out
    assert "alerts: 70" in out
    assert _demo_date_in_db(_app_db()) == DEMO_ARG


def test_main_cli_demo_date_overrides_env_demo_date(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEMO_DATE", "2026-12-01")

    assert seed_cli.main(["--demo-date", DEMO_ARG]) == 0

    assert _demo_date_in_db(_app_db()) == DEMO_ARG


def test_main_uses_injected_today_without_demo_date() -> None:
    assert seed_cli.main([]) == 0

    assert _demo_date_in_db(_app_db()) == INJECTED_TODAY.isoformat()


# --- 시연일 형식·범위 오류 -------------------------------------------------------


FORMAT_CASES = [
    pytest.param(["--demo-date", "2026-13-01"], None, id="cli-bad-month"),
    pytest.param(["--demo-date", ""], None, id="cli-empty"),
    pytest.param([], "abc", id="env-abc"),
    pytest.param([], "", id="env-empty"),
]


@pytest.mark.parametrize(("argv", "env_demo_date"), FORMAT_CASES)
def test_main_rejects_bad_demo_date_format_without_touching_empty_var(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
    env_demo_date: str | None,
) -> None:
    if env_demo_date is not None:
        monkeypatch.setenv("DEMO_DATE", env_demo_date)

    assert seed_cli.main(argv) == 1

    assert FORMAT_MESSAGE in capsys.readouterr().err
    assert not _app_db().exists()
    assert not _app_lock().exists()


@pytest.mark.parametrize(("argv", "env_demo_date"), FORMAT_CASES)
def test_main_rejects_bad_demo_date_format_keeping_existing_db(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    existing_db: tuple[Path, bytes, TableDump],
    argv: list[str],
    env_demo_date: str | None,
) -> None:
    if env_demo_date is not None:
        monkeypatch.setenv("DEMO_DATE", env_demo_date)

    assert seed_cli.main(argv) == 1

    assert FORMAT_MESSAGE in capsys.readouterr().err
    _assert_unchanged(existing_db)


def test_main_rejects_demo_date_out_of_seed_range(
    capsys: pytest.CaptureFixture[str],
    existing_db: tuple[Path, bytes, TableDump],
) -> None:
    assert seed_cli.main(["--demo-date", "0001-01-01"]) == 1

    err = capsys.readouterr().err
    assert "시연일 0001-01-01" in err
    assert "날짜 범위를 벗어난다" in err
    _assert_unchanged(existing_db)


# --- 앱 잠금 ---------------------------------------------------------------------


def test_main_refuses_while_app_lock_held_then_succeeds_after_release(
    capsys: pytest.CaptureFixture[str],
    existing_db: tuple[Path, bytes, TableDump],
) -> None:
    lock = AppLock(_app_lock())
    lock.acquire()
    try:
        code = seed_cli.main(["--demo-date", DEMO_ARG])
    finally:
        lock.release()

    assert code != 0
    assert LOCKED_MESSAGE in capsys.readouterr().err
    _assert_unchanged(existing_db)

    assert seed_cli.main(["--demo-date", DEMO_ARG]) == 0
    assert _demo_date_in_db(_app_db()) == DEMO_ARG


# --- 시드 파일 오류(실제 호출) ----------------------------------------------------


def test_main_reports_missing_seed_path_and_keeps_existing_db(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    existing_db: tuple[Path, bytes, TableDump],
) -> None:
    missing = tmp_path / "no_such_seed.json"
    monkeypatch.setenv("SEED_PATH", str(missing))

    assert seed_cli.main([]) == 1

    err = capsys.readouterr().err
    assert "시드 파일을 읽지 못했다" in err
    assert str(missing) in err
    _assert_unchanged(existing_db)


@pytest.mark.parametrize(
    ("mutate", "expected_location"),
    [
        pytest.param(_drop_patient_id, ("patients", "patient_id"), id="shape"),
        pytest.param(_order_to_missing_patient, ("meal_orders", "NS99"), id="relation"),
    ],
)
def test_main_reports_seed_error_location_and_keeps_existing_db(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    existing_db: tuple[Path, bytes, TableDump],
    mutate: object,
    expected_location: tuple[str, str],
) -> None:
    monkeypatch.setenv("SEED_PATH", str(_write_seed(tmp_path, mutate)))

    assert seed_cli.main([]) == 1

    err = capsys.readouterr().err
    assert "시드" in err
    for part in expected_location:
        assert part in err
    _assert_unchanged(existing_db)


# --- 주입한 저장소 오류 ------------------------------------------------------------


def test_main_reports_replace_failure_and_keeps_existing_data(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    existing_db: tuple[Path, bytes, TableDump],
) -> None:
    def fail_replace(src: Path, dst: Path) -> None:
        raise PermissionError(f"주입한 교체 실패: {src} -> {dst}")

    monkeypatch.setattr(seed_reset, "_replace_file", fail_replace)

    assert seed_cli.main(["--demo-date", DEMO_ARG]) == 1

    assert REPLACE_MESSAGE in capsys.readouterr().err
    app_db, _, before_dump = existing_db
    assert main_file_dump(app_db) == before_dump


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        pytest.param(
            ResetBusyError("busy=1, log=3, checkpointed=0"),
            ("DB를 연 다른 프로그램", "다시 실행하라"),
            id="busy",
        ),
        pytest.param(
            StoragePrepareError("기존 DB 보조 파일을 지우지 못했다: /x/app.db-wal"),
            ("리셋을 준비하지 못했다", "/x/app.db-wal"),
            id="prepare",
        ),
        pytest.param(
            ResetCleanupError(("checkpoints.db", "photos")),
            (
                "DB는 새 시드 상태다. 실패 항목: checkpoints.db, photos. "
                "원인을 고친 뒤 리셋을 다시 하거나 앱을 시작하면 정리를 이어 간다",
            ),
            id="cleanup",
        ),
    ],
)
def test_main_maps_injected_storage_errors_to_exit_1(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    error: Exception,
    expected: tuple[str, ...],
) -> None:
    def raise_error(settings: Settings, *, demo_date: date) -> None:
        raise error

    monkeypatch.setattr(seed_cli, "reset_storage", raise_error)

    assert seed_cli.main(["--demo-date", DEMO_ARG]) == 1

    captured = capsys.readouterr()
    for part in expected:
        assert part in captured.err
    assert captured.out == ""


def test_error_messages_list_subclasses_before_base_classes() -> None:
    classes = list(seed_cli.ERROR_MESSAGES)
    for index, cls in enumerate(classes):
        for later in classes[index + 1 :]:
            assert not issubclass(later, cls), f"{later.__name__}가 {cls.__name__} 뒤에 있다"


# --- 도움말 ---------------------------------------------------------------------


def test_help_mentions_running_with_app_stopped(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        seed_cli.main(["--help"])

    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    assert HELP_PHRASE in out
    assert "--demo-date" in out


# --- dotenv 차단 ------------------------------------------------------------------


def test_main_does_not_read_dotenv_demo_date_or_var_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # ① 임시 dotenv 파일에 DEMO_DATE·VAR_DIR를 쓴다.
    dotenv_var_dir = tmp_path / "dotenv-var"
    dotenv_file = tmp_path / ".env"
    dotenv_file.write_text(f"DEMO_DATE=2030-01-02\nVAR_DIR={dotenv_var_dir}\n", encoding="utf-8")

    # ② 클래스 dotenv 경로를 임시 파일로 두고 환경 변수를 지운다(대조군 확인).
    monkeypatch.setitem(Settings.model_config, "env_file", dotenv_file)
    monkeypatch.delenv("DEMO_DATE", raising=False)
    monkeypatch.delenv("VAR_DIR", raising=False)
    control = Settings()
    assert control.demo_date == "2030-01-02"
    assert control.var_dir == dotenv_var_dir

    # ③ 차단을 적용한다.
    disable_dotenv()

    # ④ DEMO_DATE는 미설정으로 두고 VAR_DIR만 다시 설정한다.
    var_dir = tmp_path / "var"
    monkeypatch.setenv("VAR_DIR", str(var_dir))

    # ⑤ CLI 실행.
    assert seed_cli.main([]) == 0

    assert _demo_date_in_db(var_dir / "app.db") == INJECTED_TODAY.isoformat()
    assert not (dotenv_var_dir / "app.db").exists()
