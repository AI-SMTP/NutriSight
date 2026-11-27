"""테스트 전역 설정.

모듈 수준 `app = create_app()`은 테스트 수집 중에 실행된다. 사용자 셸 값이나 로컬 `.env`가
수집 시점의 앱과 헬스체크 결과를 바꾸지 못하도록, 앱 모듈을 import하기 전에 구현 선택
환경 변수 5개를 기본값으로 고정한다. pydantic-settings는 환경 변수를 dotenv보다 우선한다.
다른 값이 필요한 테스트는 `monkeypatch.setenv`로 덮어쓴다.
"""

from __future__ import annotations

import os

import pytest

SETTING_ENV_DEFAULTS: dict[str, str] = {
    "INTAKE_ADAPTER": "fake",
    "NUTRITION_ENGINE": "fake",
    "GUIDELINE_SEARCH": "fake",
    "PATIENT_DATA": "fake",
    "FAKE_INTAKE_DELAY_S": "2.0",
}

os.environ.update(SETTING_ENV_DEFAULTS)


@pytest.fixture
def clean_settings_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """구현 선택 환경 변수 5개를 지워 `Settings` 기본값을 드러낸다."""
    for env_name in SETTING_ENV_DEFAULTS:
        monkeypatch.delenv(env_name, raising=False)
    return monkeypatch
