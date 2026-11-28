"""설정 이름으로 구현을 고르고 `create_app()`이 `app.state`에 연결하는지 검증한다."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import pytest

from app import wiring
from app.config import ConfigError, Settings, storage_paths
from app.intake.fake import FakeEstimator
from app.main import create_app
from app.nutrition.fake import FakeNutritionEngine
from app.nutrition.types import NutritionEngine
from app.recommender.fake_generator import FakeRecommendationGenerator
from app.recommender.fake_guideline import FakeGuidelineSearch
from app.services import sqlite_patient_data
from app.services.fake_patient_data import FakePatientData
from app.services.generation import PatientLocks
from app.services.runtime import AppRuntime
from app.services.sqlite_patient_data import SqlitePatientData

# (설정 필드, app.state 속성, 등록부 이름)
CONTRACTS: tuple[tuple[str, str, str], ...] = (
    ("intake_adapter", "intake_estimator", "INTAKE_ESTIMATORS"),
    ("nutrition_engine", "nutrition_engine", "NUTRITION_ENGINES"),
    ("guideline_search", "guideline_search", "GUIDELINE_SEARCHES"),
    ("patient_data", "patient_data", "PATIENT_DATA_PORTS"),
    ("recommender", "recommendation_generator", "RECOMMENDATION_GENERATORS"),
)
CONTRACT_IDS = [setting for setting, *_ in CONTRACTS]
# 생성 함수가 `(settings)`만 받는 등록부. `PATIENT_DATA_PORTS`는 `(settings, runtime)`을 받는다.
SETTINGS_ONLY_CONTRACTS = tuple(c for c in CONTRACTS if c[2] != "PATIENT_DATA_PORTS")


def test_default_settings_put_default_implementations_on_app_state(
    clean_settings_env: pytest.MonkeyPatch,
) -> None:
    app = create_app(Settings(_env_file=None))

    assert isinstance(app.state.intake_estimator, FakeEstimator)
    assert isinstance(app.state.nutrition_engine, FakeNutritionEngine)
    assert isinstance(app.state.guideline_search, FakeGuidelineSearch)
    assert isinstance(app.state.patient_data, SqlitePatientData)
    assert isinstance(app.state.recommendation_generator, FakeRecommendationGenerator)
    assert app.state.intake_estimator.delay_s == pytest.approx(2.0)


def test_fake_patient_data_stays_registered() -> None:
    app = create_app(Settings(_env_file=None, patient_data="fake"))

    assert isinstance(app.state.patient_data, FakePatientData)


PortArgs = tuple[Path, AppRuntime, NutritionEngine]


class SpyPort(SqlitePatientData):
    """생성 인자를 `calls`에 기록하는 SQLite 포트. `spy_port`가 테스트마다 `calls`를 바꾼다."""

    calls: ClassVar[list[PortArgs]] = []

    def __init__(self, db_path: Path, runtime: AppRuntime, engine: NutritionEngine) -> None:
        type(self).calls.append((db_path, runtime, engine))
        super().__init__(db_path, runtime, engine)


@pytest.fixture
def spy_port(monkeypatch: pytest.MonkeyPatch) -> list[PortArgs]:
    """`sqlite` 포트 생성을 `SpyPort`로 바꾸고 생성 인자 기록을 돌려준다."""
    calls: list[PortArgs] = []
    monkeypatch.setattr(SpyPort, "calls", calls)
    monkeypatch.setattr(sqlite_patient_data, "SqlitePatientData", SpyPort)
    return calls


def test_sqlite_port_uses_app_runtime_and_app_db(
    spy_port: list[PortArgs], isolated_var_dir: Path
) -> None:
    settings = Settings(_env_file=None)

    app = create_app(settings)

    assert isinstance(app.state.patient_data, SpyPort)
    [(db_path, runtime, engine)] = spy_port
    assert db_path == storage_paths(settings).app_db
    assert runtime is app.state.runtime
    assert isinstance(engine, FakeNutritionEngine)
    assert not isolated_var_dir.exists()


def test_sqlite_port_receives_engine_selected_by_setting(
    monkeypatch: pytest.MonkeyPatch, spy_port: list[PortArgs]
) -> None:
    built: list[FakeNutritionEngine] = []

    def alt_engine(settings: Settings) -> FakeNutritionEngine:
        engine = FakeNutritionEngine()
        built.append(engine)
        return engine

    monkeypatch.setitem(wiring.NUTRITION_ENGINES, "alt", alt_engine)

    app = create_app(Settings(_env_file=None, nutrition_engine="alt"))

    # 포트용 1번, `app.state`용 1번. 두 인스턴스는 공유하지 않는다(엔진은 상태가 없다는 전제).
    assert len(built) == 2
    [(_, _, port_engine)] = spy_port
    assert any(port_engine is engine for engine in built)
    assert any(app.state.nutrition_engine is engine for engine in built)


def test_runtime_is_shared_by_bus_and_recommendation_deps() -> None:
    settings = Settings(_env_file=None, recommendation_timeout_s=7.5)

    app = create_app(settings)

    runtime = app.state.runtime
    deps = app.state.recommendation_deps
    assert isinstance(runtime, AppRuntime)
    assert app.state.event_bus is runtime.bus
    assert runtime.writer.db_path == storage_paths(settings).app_db
    assert deps.runtime is runtime
    assert deps.generator is app.state.recommendation_generator
    assert deps.engine is app.state.nutrition_engine
    assert deps.db_path == storage_paths(settings).app_db
    assert isinstance(deps.locks, PatientLocks)
    assert deps.timeout_s == pytest.approx(7.5)


def test_each_app_gets_its_own_runtime() -> None:
    settings = Settings(_env_file=None)

    first = create_app(settings)
    second = create_app(settings)

    assert first.state.runtime is not second.state.runtime


def test_fake_intake_delay_follows_settings() -> None:
    app = create_app(Settings(_env_file=None, fake_intake_delay_s=0.25))

    assert app.state.intake_estimator.delay_s == pytest.approx(0.25)


def test_create_app_without_settings_reads_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_INTAKE_DELAY_S", "0.75")

    app = create_app()

    assert app.state.intake_estimator.delay_s == pytest.approx(0.75)


@pytest.mark.parametrize(
    ("setting", "state_attr", "registry_name"),
    SETTINGS_ONLY_CONTRACTS,
    ids=[setting for setting, *_ in SETTINGS_ONLY_CONTRACTS],
)
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
    # `sqlite` 포트는 판단 알고리즘을 따로 만들므로(스펙 3.8) `fake` 포트로 호출 횟수를 분리한다.
    settings = Settings(_env_file=None, **{"patient_data": "fake", setting: "alt"})

    app = create_app(settings)

    assert getattr(app.state, state_attr) is alternative
    assert received == [settings]


def test_registered_patient_data_alternative_receives_app_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alternative = object()
    received: list[tuple[Settings, AppRuntime]] = []

    def factory(settings: Settings, runtime: AppRuntime) -> object:
        received.append((settings, runtime))
        return alternative

    monkeypatch.setitem(wiring.PATIENT_DATA_PORTS, "alt", factory)
    settings = Settings(_env_file=None, patient_data="alt")

    app = create_app(settings)

    assert app.state.patient_data is alternative
    [(got_settings, got_runtime)] = received
    assert got_settings == settings
    assert got_runtime is app.state.runtime


def test_generator_alternative_is_used_by_recommendation_deps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alternative = FakeRecommendationGenerator(fail=True)
    monkeypatch.setitem(wiring.RECOMMENDATION_GENERATORS, "alt", lambda settings: alternative)

    app = create_app(Settings(_env_file=None, recommender="alt"))

    assert app.state.recommendation_deps.generator is alternative


@pytest.mark.parametrize("setting", CONTRACT_IDS)
def test_unregistered_name_raises_config_error(setting: str) -> None:
    settings = Settings(_env_file=None, **{setting: "missing"})

    with pytest.raises(ConfigError) as excinfo:
        create_app(settings)

    message = str(excinfo.value)
    assert setting in message
    assert "missing" in message
