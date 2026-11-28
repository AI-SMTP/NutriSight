"""`Settings` 기본값·환경 변수 덮어쓰기·검증, 저장소 경로와 시연일 해석 테스트."""

from __future__ import annotations

import dataclasses
import os
import re
from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

import app.main
from app.config import (
    DEFAULT_FRONTEND_DIST,
    DEFAULT_SEED_PATH,
    DEFAULT_VAR_DIR,
    REPO_ROOT,
    ConfigError,
    Settings,
    StoragePaths,
    resolve_demo_date,
    storage_paths,
)
from app.services.runtime import AppRuntime
from app.wiring import Components, build_components
from tests.conftest import disable_dotenv


def test_settings_defaults_select_sqlite_patient_data_and_fake_others(
    clean_settings_env: pytest.MonkeyPatch,
) -> None:
    settings = Settings(_env_file=None)

    assert settings.intake_adapter == "fake"
    assert settings.nutrition_engine == "fake"
    assert settings.guideline_search == "fake"
    assert settings.patient_data == "sqlite"
    assert settings.recommender == "fake"
    assert settings.fake_intake_delay_s == pytest.approx(2.0)
    assert settings.recommendation_timeout_s == pytest.approx(120.0)


def test_settings_reads_recommendation_overrides(clean_settings_env: pytest.MonkeyPatch) -> None:
    clean_settings_env.setenv("RECOMMENDER", "alt")
    clean_settings_env.setenv("RECOMMENDATION_TIMEOUT_S", "0.5")

    settings = Settings(_env_file=None)

    assert settings.recommender == "alt"
    assert settings.recommendation_timeout_s == pytest.approx(0.5)


@pytest.mark.parametrize("raw", ["0", "-1"])
def test_settings_rejects_non_positive_recommendation_timeout(
    clean_settings_env: pytest.MonkeyPatch, raw: str
) -> None:
    clean_settings_env.setenv("RECOMMENDATION_TIMEOUT_S", raw)

    with pytest.raises(ValidationError, match="recommendation_timeout_s"):
        Settings(_env_file=None)


def test_settings_reads_environment_overrides(clean_settings_env: pytest.MonkeyPatch) -> None:
    clean_settings_env.setenv("INTAKE_ADAPTER", "alt")
    clean_settings_env.setenv("FAKE_INTAKE_DELAY_S", "0.5")

    settings = Settings(_env_file=None)

    assert settings.intake_adapter == "alt"
    assert settings.fake_intake_delay_s == pytest.approx(0.5)


def test_settings_rejects_negative_fake_intake_delay(
    clean_settings_env: pytest.MonkeyPatch,
) -> None:
    clean_settings_env.setenv("FAKE_INTAKE_DELAY_S", "-1")

    with pytest.raises(ValidationError, match="fake_intake_delay_s"):
        Settings(_env_file=None)


# 테스트 파일 위치(backend/tests/)에서 저장소 루트를 따로 계산해 `config.py` 계산과 대조한다.
EXPECTED_REPO_ROOT = Path(__file__).resolve().parents[2]
FORMAT_ERROR_MESSAGE = re.escape("시연일 형식이 잘못됐다(YYYY-MM-DD)")
TODAY = date(2026, 11, 27)


def _list_repo_var_files() -> set[str]:
    """저장소 루트 `var/` 아래 모든 파일·디렉토리(git 무시 파일 포함)의 상대 경로."""
    var_dir = EXPECTED_REPO_ROOT / "var"
    if not var_dir.exists():
        return set()
    return {str(path.relative_to(var_dir)) for path in var_dir.rglob("*")}


def test_settings_default_paths_are_under_repository_root(
    clean_settings_env: pytest.MonkeyPatch,
) -> None:
    before = _list_repo_var_files()

    settings = Settings(_env_file=None)
    paths = storage_paths(settings)

    assert settings.var_dir == EXPECTED_REPO_ROOT / "var"
    assert settings.seed_path == EXPECTED_REPO_ROOT / "data" / "seed" / "demo_seed.json"
    assert settings.demo_date is None
    assert DEFAULT_FRONTEND_DIST == EXPECTED_REPO_ROOT / "frontend" / "dist"
    assert settings.frontend_dist == DEFAULT_FRONTEND_DIST
    assert paths.app_db == EXPECTED_REPO_ROOT / "var" / "app.db"
    assert _list_repo_var_files() == before


def test_default_paths_do_not_depend_on_working_directory(
    clean_settings_env: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    clean_settings_env.chdir(tmp_path)

    settings = Settings(_env_file=None)

    assert REPO_ROOT == EXPECTED_REPO_ROOT
    assert DEFAULT_VAR_DIR == EXPECTED_REPO_ROOT / "var"
    assert DEFAULT_SEED_PATH == EXPECTED_REPO_ROOT / "data" / "seed" / "demo_seed.json"
    assert settings.var_dir == DEFAULT_VAR_DIR
    assert settings.seed_path == DEFAULT_SEED_PATH


def test_settings_reads_storage_environment_overrides(
    clean_settings_env: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    clean_settings_env.setenv("VAR_DIR", str(tmp_path / "custom-var"))
    clean_settings_env.setenv("SEED_PATH", str(tmp_path / "seed.json"))
    clean_settings_env.setenv("DEMO_DATE", "2026-12-01")

    settings = Settings(_env_file=None)

    assert settings.var_dir == tmp_path / "custom-var"
    assert settings.seed_path == tmp_path / "seed.json"
    assert settings.demo_date == "2026-12-01"


def test_storage_paths_are_computed_under_var_dir(tmp_path: Path) -> None:
    var_dir = tmp_path / "var"
    settings = Settings(_env_file=None, var_dir=var_dir)

    paths = storage_paths(settings)

    assert paths == StoragePaths(
        app_db=var_dir / "app.db",
        checkpoints_db=var_dir / "checkpoints.db",
        photos_dir=var_dir / "photos",
        app_lock=var_dir / "app.lock",
    )
    assert not var_dir.exists()


def test_storage_paths_is_immutable(tmp_path: Path) -> None:
    paths = storage_paths(Settings(_env_file=None, var_dir=tmp_path))

    with pytest.raises(dataclasses.FrozenInstanceError):
        paths.app_db = tmp_path / "other.db"  # type: ignore[misc]


def test_resolve_demo_date_prefers_cli_over_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEMO_DATE", "2026-12-01")
    settings = Settings(_env_file=None)

    assert resolve_demo_date("2026-12-05", settings, TODAY) == date(2026, 12, 5)


def test_resolve_demo_date_uses_setting_without_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEMO_DATE", "2026-12-01")
    settings = Settings(_env_file=None)

    assert resolve_demo_date(None, settings, TODAY) == date(2026, 12, 1)


def test_resolve_demo_date_uses_today_when_both_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEMO_DATE", raising=False)
    settings = Settings(_env_file=None)

    assert settings.demo_date is None
    assert resolve_demo_date(None, settings, TODAY) == TODAY


@pytest.mark.parametrize("cli_value", ["2026-13-01", "abc", "2026-1-5", "", "2026-02-30"])
def test_resolve_demo_date_rejects_invalid_cli_value(cli_value: str) -> None:
    settings = Settings(_env_file=None)

    with pytest.raises(ConfigError, match=FORMAT_ERROR_MESSAGE):
        resolve_demo_date(cli_value, settings, TODAY)


@pytest.mark.parametrize("env_value", ["2026-13-01", "abc", "2026-1-5", "", "20261201"])
def test_resolve_demo_date_rejects_invalid_setting(
    monkeypatch: pytest.MonkeyPatch, env_value: str
) -> None:
    monkeypatch.setenv("DEMO_DATE", env_value)
    settings = Settings(_env_file=None)

    with pytest.raises(ConfigError, match=FORMAT_ERROR_MESSAGE):
        resolve_demo_date(None, settings, TODAY)


def test_resolve_demo_date_validates_cli_even_when_setting_is_valid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEMO_DATE", "2026-12-01")
    settings = Settings(_env_file=None)

    with pytest.raises(ConfigError, match=FORMAT_ERROR_MESSAGE):
        resolve_demo_date("", settings, TODAY)


def test_resolve_demo_date_rejects_invalid_setting_even_with_valid_cli(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEMO_DATE", "abc")
    settings = Settings(_env_file=None)

    with pytest.raises(ConfigError, match=FORMAT_ERROR_MESSAGE):
        resolve_demo_date("2026-12-05", settings, TODAY)


@pytest.mark.parametrize(
    ("env_name", "field"),
    [("VAR_DIR", "var_dir"), ("SEED_PATH", "seed_path"), ("FRONTEND_DIST", "frontend_dist")],
)
def test_relative_storage_paths_are_anchored_to_repo_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, env_name: str, field: str
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(env_name, "relative/place")

    assert getattr(Settings(_env_file=None), field) == REPO_ROOT / "relative" / "place"


def test_home_relative_var_dir_is_expanded(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("VAR_DIR", "~/nutrisight-var")

    assert Settings(_env_file=None).var_dir == tmp_path / "nutrisight-var"


def test_collection_frontend_dist_points_to_missing_directory() -> None:
    frontend_dist = Path(os.environ["FRONTEND_DIST"])

    assert not frontend_dist.exists()
    assert Settings().frontend_dist == frontend_dist


def test_autouse_fixture_isolates_var_dir_and_dotenv(tmp_path: Path) -> None:
    assert os.environ["VAR_DIR"] == str(tmp_path / "var")
    assert "DEMO_DATE" not in os.environ
    assert Settings.model_config.get("env_file") is None
    assert Settings().var_dir == tmp_path / "var"


def test_disable_dotenv_blocks_dotenv_values_for_settings_and_create_app(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # ① 임시 dotenv 파일에 DEMO_DATE·VAR_DIR를 쓴다.
    dotenv_var_dir = tmp_path / "dotenv-var"
    dotenv_file = tmp_path / ".env"
    dotenv_file.write_text(f"DEMO_DATE=2030-01-02\nVAR_DIR={dotenv_var_dir}\n", encoding="utf-8")

    # ② 실제 상황 재현: 클래스 dotenv 경로를 임시 파일로 두고 환경 변수를 지운다.
    monkeypatch.setitem(Settings.model_config, "env_file", dotenv_file)
    monkeypatch.delenv("DEMO_DATE", raising=False)
    monkeypatch.delenv("VAR_DIR", raising=False)
    control = Settings()
    assert control.demo_date == "2030-01-02"
    assert control.var_dir == dotenv_var_dir

    # ③ 차단을 적용한다.
    disable_dotenv()

    # ④ Settings()와 create_app()이 dotenv 값을 읽지 않는다.
    blocked = Settings()
    assert blocked.demo_date is None
    assert blocked.var_dir == DEFAULT_VAR_DIR

    captured: list[Settings] = []

    def spy(settings: Settings, runtime: AppRuntime) -> Components:
        captured.append(settings)
        return build_components(settings, runtime)

    monkeypatch.setattr(app.main, "build_components", spy)
    app.main.create_app()

    assert len(captured) == 1
    assert captured[0].demo_date is None
    assert captured[0].var_dir == DEFAULT_VAR_DIR
