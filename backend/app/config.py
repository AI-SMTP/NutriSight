"""구현 선택 설정과 설정 오류.

환경 변수(대소문자 무시)와 `backend/.env`에서 읽는다. 환경 변수가 dotenv보다 우선한다.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# 실행 위치와 무관하게 `backend/.env`를 읽는다.
BACKEND_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"
DEFAULT_IMPLEMENTATION = "fake"
DEFAULT_FAKE_INTAKE_DELAY_S = 2.0


class ConfigError(Exception):
    """설정값으로 구현을 만들 수 없을 때(등록되지 않은 이름 등) 던진다."""


class Settings(BaseSettings):
    """네 계약의 구현 이름과 Fake 섭취 추정 지연 시간."""

    model_config = SettingsConfigDict(env_file=BACKEND_ENV_FILE, extra="ignore")

    intake_adapter: str = DEFAULT_IMPLEMENTATION
    nutrition_engine: str = DEFAULT_IMPLEMENTATION
    guideline_search: str = DEFAULT_IMPLEMENTATION
    patient_data: str = DEFAULT_IMPLEMENTATION
    fake_intake_delay_s: float = Field(DEFAULT_FAKE_INTAKE_DELAY_S, ge=0)
