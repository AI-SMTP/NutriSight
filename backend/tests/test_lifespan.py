"""앱 lifespan의 시연일 검사·앱 잠금·자동 시드 테스트 (스펙 3.8).

`TestClient`를 `with`로 써야 lifespan이 실행된다. 날짜에 의존하지 않도록 `DEMO_DATE`를 고정한다.
`VAR_DIR`는 autouse fixture가 `tmp_path / "var"`로 돌린다.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import DEFAULT_SEED_PATH, ConfigError, Settings, storage_paths
from app.main import create_app
from app.nutrition.fake import FakeNutritionEngine
from app.storage.app_lock import AppLock
from app.storage.db import connect
from app.storage.errors import AppLockedError, ResetCleanupError
from app.storage.seed import CLEANUP_PENDING_KEY, build_database, load_seed_file
from tests.storage.demo import DEMO
from tests.storage.dump import main_file_dump
from tests.storage.reset_support import spy_unlink

BACKEND_DIR = Path(__file__).resolve().parents[1]
DEMO_DATE = DEMO.isoformat()


@pytest.fixture
def demo_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    monkeypatch.setenv("DEMO_DATE", DEMO_DATE)
    return monkeypatch


def _build_seed_db(base: Path, *, cleanup_pending: bool) -> Path:
    path = base / "app.db"
    seed = load_seed_file(DEFAULT_SEED_PATH)
    build_database(path, seed, DEMO, FakeNutritionEngine(), cleanup_pending=cleanup_pending)
    return path


@pytest.fixture(scope="module")
def seeded_db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """정상 시드 DB(표시 없음). 복사해서만 쓴다."""
    return _build_seed_db(tmp_path_factory.mktemp("seeded"), cleanup_pending=False)


@pytest.fixture(scope="module")
def pending_db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """정리 대기 표시가 있는 시드 DB. 복사해서만 쓴다."""
    return _build_seed_db(tmp_path_factory.mktemp("pending"), cleanup_pending=True)


def _var_files(var_dir: Path) -> list[str]:
    if not var_dir.exists():
        return []
    return sorted(str(p.relative_to(var_dir)) for p in var_dir.rglob("*"))


def _has_mark(app_db: Path) -> bool:
    with connect(app_db) as conn:
        row = conn.execute(
            "SELECT 1 FROM seed_meta WHERE key = ?", (CLEANUP_PENDING_KEY,)
        ).fetchone()
    return row is not None


def _assert_lock_free(settings: Settings) -> None:
    lock = AppLock(storage_paths(settings).app_lock)
    lock.acquire()
    lock.release()


def _fail_checkpoints_unlink(monkeypatch: pytest.MonkeyPatch, enabled: list[bool]) -> None:
    calls: list[str] = []
    spy_unlink(
        monkeypatch,
        calls,
        fail_when=lambda path: enabled[0] and path.name.startswith("checkpoints.db"),
    )


def test_lifespan_seeds_empty_var_and_releases_lock(
    demo_env: pytest.MonkeyPatch, isolated_var_dir: Path
) -> None:
    settings = Settings()

    with TestClient(create_app(settings)) as client:
        assert (isolated_var_dir / "app.db").exists()
        response = client.get("/api/health")
        assert response.status_code == 200
        with pytest.raises(AppLockedError):
            AppLock(storage_paths(settings).app_lock).acquire()

    _assert_lock_free(settings)
    assert not _has_mark(isolated_var_dir / "app.db")


def test_lifespan_fails_when_lock_held(
    demo_env: pytest.MonkeyPatch, isolated_var_dir: Path
) -> None:
    settings = Settings()
    held = AppLock(storage_paths(settings).app_lock)
    held.acquire()
    try:
        with pytest.raises(AppLockedError, match="다른 앱 또는 리셋이 실행 중이다"):
            with TestClient(create_app(settings)):
                pass  # pragma: no cover
    finally:
        held.release()

    assert not (isolated_var_dir / "app.db").exists()


@pytest.mark.parametrize("raw", ["abc", ""], ids=["abc", "empty"])
def test_lifespan_bad_demo_date_on_empty_var_creates_nothing(
    monkeypatch: pytest.MonkeyPatch, isolated_var_dir: Path, raw: str
) -> None:
    monkeypatch.setenv("DEMO_DATE", raw)
    application = create_app(Settings())

    with pytest.raises(ConfigError, match=r"시연일 형식이 잘못됐다\(YYYY-MM-DD\)"):
        with TestClient(application):
            pass  # pragma: no cover

    assert _var_files(isolated_var_dir) == []


@pytest.mark.parametrize("raw", ["abc", ""], ids=["abc", "empty"])
def test_lifespan_bad_demo_date_keeps_existing_db(
    monkeypatch: pytest.MonkeyPatch, isolated_var_dir: Path, seeded_db: Path, raw: str
) -> None:
    isolated_var_dir.mkdir()
    app_db = isolated_var_dir / "app.db"
    shutil.copyfile(seeded_db, app_db)
    before_bytes = app_db.read_bytes()
    before_dump = main_file_dump(app_db)
    monkeypatch.setenv("DEMO_DATE", raw)
    application = create_app(Settings())

    with pytest.raises(ConfigError):
        with TestClient(application):
            pass  # pragma: no cover

    assert app_db.read_bytes() == before_bytes
    assert main_file_dump(app_db) == before_dump
    assert _var_files(isolated_var_dir) == ["app.db"]


def test_lifespan_fails_when_pending_cleanup_fails_again(
    demo_env: pytest.MonkeyPatch, isolated_var_dir: Path, pending_db: Path
) -> None:
    isolated_var_dir.mkdir()
    shutil.copyfile(pending_db, isolated_var_dir / "app.db")
    (isolated_var_dir / "checkpoints.db").write_bytes(b"checkpoint")
    _fail_checkpoints_unlink(demo_env, [True])
    settings = Settings()

    with pytest.raises(ResetCleanupError) as info:
        with TestClient(create_app(settings)):
            pass  # pragma: no cover

    assert info.value.failures == ("checkpoints.db",)
    assert _has_mark(isolated_var_dir / "app.db")
    _assert_lock_free(settings)


def test_lifespan_recovers_after_first_start_cleanup_failure(
    demo_env: pytest.MonkeyPatch, isolated_var_dir: Path
) -> None:
    failing = [True]
    _fail_checkpoints_unlink(demo_env, failing)
    settings = Settings()

    with pytest.raises(ResetCleanupError):
        with TestClient(create_app(settings)):
            pass  # pragma: no cover

    _assert_lock_free(settings)
    assert _has_mark(isolated_var_dir / "app.db")

    failing[0] = False
    with TestClient(create_app(Settings())) as client:
        assert client.get("/api/health").status_code == 200

    assert not _has_mark(isolated_var_dir / "app.db")


def test_import_app_main_creates_no_files(tmp_path: Path) -> None:
    var_dir = tmp_path / "import-var"
    env = {
        key: value
        for key, value in os.environ.items()
        if key.upper() not in {"DEMO_DATE", "VAR_DIR"}
    }
    env["VAR_DIR"] = str(var_dir)
    # dotenv의 `VAR_DIR`보다 환경 변수가 우선하므로 import 대상 경로가 `var_dir`로 고정된다.
    result = subprocess.run(
        [sys.executable, "-c", "import app.main; print(app.main.app.title)"],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "NutriSight"
    assert not var_dir.exists()
