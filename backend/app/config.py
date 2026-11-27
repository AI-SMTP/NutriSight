"""구현 선택·저장소 경로·시연일 설정과 설정 오류.

환경 변수(대소문자 무시)와 `backend/.env`에서 읽는다. 환경 변수가 dotenv보다 우선한다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 실행 위치와 무관하게 `config.py` 위치에서 저장소 루트와 `backend/.env`를 계산한다.
REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"
DEFAULT_VAR_DIR = REPO_ROOT / "var"
DEFAULT_SEED_PATH = REPO_ROOT / "data" / "seed" / "demo_seed.json"
DEFAULT_IMPLEMENTATION = "fake"
DEFAULT_FAKE_INTAKE_DELAY_S = 2.0

_DEMO_DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}", re.ASCII)
DEMO_DATE_FORMAT_ERROR = "시연일 형식이 잘못됐다(YYYY-MM-DD)"


class ConfigError(Exception):
    """설정값으로 구현을 만들 수 없거나(등록되지 않은 이름 등) 형식이 잘못됐을 때 던진다."""


class Settings(BaseSettings):
    """네 계약의 구현 이름, Fake 섭취 추정 지연 시간, 저장소 경로와 시연일."""

    model_config = SettingsConfigDict(env_file=BACKEND_ENV_FILE, extra="ignore")

    intake_adapter: str = DEFAULT_IMPLEMENTATION
    nutrition_engine: str = DEFAULT_IMPLEMENTATION
    guideline_search: str = DEFAULT_IMPLEMENTATION
    patient_data: str = DEFAULT_IMPLEMENTATION
    fake_intake_delay_s: float = Field(DEFAULT_FAKE_INTAKE_DELAY_S, ge=0)
    var_dir: Path = DEFAULT_VAR_DIR
    seed_path: Path = DEFAULT_SEED_PATH
    # 원문 그대로 둔다. 형식 검사는 `resolve_demo_date`가 한다(모듈 수준 앱 생성이 실패하지 않게).
    demo_date: str | None = None

    @field_validator("var_dir", "seed_path")
    @classmethod
    def _anchor_to_repo_root(cls, value: Path) -> Path:
        """`~`를 펼치고, 상대 경로는 실행 위치가 아니라 저장소 루트 기준으로 해석한다."""
        expanded = value.expanduser()
        return expanded if expanded.is_absolute() else REPO_ROOT / expanded


@dataclass(frozen=True)
class StoragePaths:
    """`var_dir`에서 계산한 실행 중 파일 경로 묶음."""

    app_db: Path
    checkpoints_db: Path
    photos_dir: Path
    app_lock: Path


def storage_paths(settings: Settings) -> StoragePaths:
    """`settings.var_dir` 아래 업무 DB·대화 DB·사진 디렉토리·앱 잠금 파일 경로를 계산한다.

    경로만 계산하고 파일이나 디렉토리를 만들지 않는다.
    """
    var_dir = settings.var_dir
    return StoragePaths(
        app_db=var_dir / "app.db",
        checkpoints_db=var_dir / "checkpoints.db",
        photos_dir=var_dir / "photos",
        app_lock=var_dir / "app.lock",
    )


def _parse_demo_date(raw: str) -> date:
    """`YYYY-MM-DD` 형식의 실제 날짜만 받는다. 아니면 `ConfigError`를 던진다."""
    if not _DEMO_DATE_PATTERN.fullmatch(raw):
        raise ConfigError(DEMO_DATE_FORMAT_ERROR)
    try:
        return date.fromisoformat(raw)
    except ValueError as err:
        raise ConfigError(DEMO_DATE_FORMAT_ERROR) from err


def resolve_demo_date(cli_value: str | None, settings: Settings, today: date) -> date:
    """시연일을 CLI 값 → 설정 `DEMO_DATE` → `today` 순서로 정한다.

    `None`만 미입력으로 본다. 입력한 값은 우선순위와 상관없이 모두 검사한다(스펙 3.2). 명시한
    빈 문자열을 포함해 `YYYY-MM-DD` 실제 날짜가 아니면
    `ConfigError("시연일 형식이 잘못됐다(YYYY-MM-DD)")`를 던진다.
    """
    setting_date = None if settings.demo_date is None else _parse_demo_date(settings.demo_date)
    cli_date = None if cli_value is None else _parse_demo_date(cli_value)
    return cli_date or setting_date or today
