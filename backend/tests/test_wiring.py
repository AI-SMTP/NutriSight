"""설정 이름으로 구현을 고르고 `create_app()`이 `app.state`에 연결하는지 검증한다."""

from __future__ import annotations

import pytest

from app import wiring
from app.config import ConfigError, Settings
from app.intake.fake import FakeEstimator
from app.main import create_app
from app.nutrition.fake import FakeNutritionEngine
from app.recommender.fake_guideline import FakeGuidelineSearch
from app.services.fake_patient_data import FakePatientData

# (설정 필드, app.state 속성, 등록부 이름)
CONTRACTS: tuple[tuple[str, str, str], ...] = (
    ("intake_adapter", "intake_estimator", "INTAKE_ESTIMATORS"),
    ("nutrition_engine", "nutrition_engine", "NUTRITION_ENGINES"),
    ("guideline_search", "guideline_search", "GUIDELINE_SEARCHES"),
    ("patient_data", "patient_data", "PATIENT_DATA_PORTS"),
)
CONTRACT_IDS = [setting for setting, *_ in CONTRACTS]


def test_default_settings_put_fake_implementations_on_app_state(
    clean_settings_env: pytest.MonkeyPatch,
) -> None:
    app = create_app(Settings(_env_file=None))

    assert isinstance(app.state.intake_estimator, FakeEstimator)
    assert isinstance(app.state.nutrition_engine, FakeNutritionEngine)
    assert isinstance(app.state.guideline_search, FakeGuidelineSearch)
    assert isinstance(app.state.patient_data, FakePatientData)
    assert app.state.intake_estimator.delay_s == pytest.approx(2.0)


def test_fake_intake_delay_follows_settings() -> None:
    app = create_app(Settings(_env_file=None, fake_intake_delay_s=0.25))

    assert app.state.intake_estimator.delay_s == pytest.approx(0.25)


def test_create_app_without_settings_reads_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_INTAKE_DELAY_S", "0.75")

    app = create_app()

    assert app.state.intake_estimator.delay_s == pytest.approx(0.75)


@pytest.mark.parametrize(("setting", "state_attr", "registry_name"), CONTRACTS, ids=CONTRACT_IDS)
def test_registered_alternative_is_selected_by_name(
    monkeypatch: pytest.MonkeyPatch,
    setting: str,
    state_attr: str,
    registry_name: str,
) -> None:
    alternative = object()
    received: list[Settings] = []

    def factory(settings: Settings) -> object:
        received.append(settings)
        return alternative

    monkeypatch.setitem(getattr(wiring, registry_name), "alt", factory)
    settings = Settings(_env_file=None, **{setting: "alt"})

    app = create_app(settings)

    assert getattr(app.state, state_attr) is alternative
    assert received == [settings]


@pytest.mark.parametrize("setting", CONTRACT_IDS)
def test_unregistered_name_raises_config_error(setting: str) -> None:
    settings = Settings(_env_file=None, **{setting: "missing"})

    with pytest.raises(ConfigError) as excinfo:
        create_app(settings)

    message = str(excinfo.value)
    assert setting in message
    assert "missing" in message
