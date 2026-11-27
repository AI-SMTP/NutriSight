"""`Settings` 기본값·환경 변수 덮어쓰기·검증 테스트."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings


def test_settings_defaults_select_fake_implementations(
    clean_settings_env: pytest.MonkeyPatch,
) -> None:
    settings = Settings(_env_file=None)

    assert settings.intake_adapter == "fake"
    assert settings.nutrition_engine == "fake"
    assert settings.guideline_search == "fake"
    assert settings.patient_data == "fake"
    assert settings.fake_intake_delay_s == pytest.approx(2.0)


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
