"""테스트 전역 설정.

모듈 수준 `app = create_app()`은 테스트 수집 중에 실행된다. 사용자 셸 값이나 로컬 `.env`가
수집 시점의 앱과 헬스체크 결과를 바꾸지 못하도록, 앱 모듈을 import하기 전에 아래를 먼저 한다.

1. `os.environ`에서 설정 환경 변수(`DEMO_DATE` 포함)를 대소문자와 상관없이 지운다.
2. 구현 선택 환경 변수 7개(구현 이름 5개와 `FAKE_INTAKE_DELAY_S`·`RECOMMENDATION_TIMEOUT_S`)와
   `SEED_PATH`·`VAR_DIR`·`FRONTEND_DIST`를 기본값으로 고정한다.
   수집용 `VAR_DIR`는 계산만 한 임시 경로로, 디렉토리를 만들지 않는다. 모듈 수준 앱은
   lifespan을 실행하지 않아 이 경로에 쓰지 않고, 파일을 쓰는 테스트는 autouse fixture가
   `tmp_path / "var"`로 덮어쓴다. 수집용 `FRONTEND_DIST`는 없는 경로라 정적 제공이 꺼진다.
3. `Settings`의 dotenv 읽기를 끈다. 그래서 `backend/.env`의 `DEMO_DATE`·`VAR_DIR`가 어떤
   진입점에서도 다시 읽히지 않는다.

다른 값이 필요한 테스트는 `monkeypatch.setenv`로 덮어쓴다.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from app.config import DEFAULT_SEED_PATH, Settings
from app.nutrition.fake import FakeNutritionEngine
from app.storage.db import connect, create_schema
from app.storage.seed import build_database, load_seed_file
from tests.storage.demo import DEMO

SETTING_ENV_DEFAULTS: dict[str, str] = {
    "INTAKE_ADAPTER": "fake",
    "NUTRITION_ENGINE": "fake",
    "GUIDELINE_SEARCH": "fake",
    "PATIENT_DATA": "sqlite",
    "RECOMMENDER": "fake",
    "FAKE_INTAKE_DELAY_S": "2.0",
    "RECOMMENDATION_TIMEOUT_S": "120",
    "SEED_PATH": str(DEFAULT_SEED_PATH),
    "VAR_DIR": str(Path(tempfile.gettempdir()) / "nutrisight-test-collect-var"),
    # 존재하지 않는 경로로 고정해 수집 시점의 앱이 저장소의 `frontend/dist`에 영향받지 않게 한다.
    "FRONTEND_DIST": "/nonexistent/nutrisight-frontend-dist",
}
# 테스트가 지우는 설정 환경 변수 전체. `Settings` 필드에서 만들어 새 설정이 빠지지 않게 한다.
SETTING_ENV_NAMES: tuple[str, ...] = tuple(name.upper() for name in Settings.model_fields)

# pydantic-settings는 환경 변수 이름의 대소문자를 무시하므로 소문자 이름도 함께 지운다.
for _env_name in list(os.environ):
    if _env_name.upper() in SETTING_ENV_NAMES:
        del os.environ[_env_name]
os.environ.update(SETTING_ENV_DEFAULTS)


def disable_dotenv() -> None:
    """`Settings` 클래스에 저장된 dotenv 경로를 꺼서 `backend/.env`를 읽지 않게 한다."""
    Settings.model_config["env_file"] = None


disable_dotenv()


@pytest.fixture(autouse=True)
def isolated_var_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """모든 테스트의 `VAR_DIR`를 `tmp_path / "var"`로 돌리고 dotenv 읽기를 끈다."""
    var_dir = tmp_path / "var"
    monkeypatch.setenv("VAR_DIR", str(var_dir))
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    return var_dir


@pytest.fixture
def clean_settings_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """설정 환경 변수(구현 선택 7개, `SEED_PATH`·`VAR_DIR`·`DEMO_DATE`·`FRONTEND_DIST`)를 지운다."""
    for env_name in SETTING_ENV_NAMES:
        monkeypatch.delenv(env_name, raising=False)
    return monkeypatch


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """`tmp_path / "app.db"`에 스키마만 만든 빈 DB 경로."""
    path = tmp_path / "app.db"
    with connect(path) as conn:
        create_schema(conn)
    return path


@pytest.fixture(scope="session")
def seeded_db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """실제 시드를 D=2026-12-05(`DEMO`), `FakeNutritionEngine`으로 적재한 정상 DB(표시 없음).

    복사해서만 쓴다.
    """
    path = tmp_path_factory.mktemp("seeded") / "app.db"
    build_database(path, load_seed_file(DEFAULT_SEED_PATH), DEMO, FakeNutritionEngine())
    return path
