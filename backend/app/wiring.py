"""설정 이름으로 다섯 계약의 구현을 만드는 등록부.

계약마다 `이름 → 생성 함수(Settings)` 등록부가 있고, `Settings`의 해당 값으로 구현을 고른다.
`PATIENT_DATA_PORTS`만 생성 함수가 `(Settings, AppRuntime)`을 받는다. `create_app`이 만든 런타임
(버스·태스크·쓰기 실행기·시계)을 포트와 추천 의존성이 함께 쓰게 하기 위해서다(스펙 3.8 등록 경로).

병행 트랙이 실제 구현을 추가하는 방법:

1. 이 모듈에 `def _build_xxx(settings: Settings) -> <계약>` 생성 함수를 만들고, 구현 모듈은
   함수 안에서 import한다. 그 이름이 선택됐을 때만 SDK·색인을 읽게 해, 다른 구현으로 띄우거나
   테스트를 수집할 때 무거운 의존성이 로드되거나 미설치로 import가 깨지지 않게 한다.

       def _build_vlm_estimator(settings: Settings) -> IntakeEstimator:
           from app.intake.vlm import VlmEstimator  # 선택됐을 때만 로드

           return VlmEstimator(...)

2. 아래 해당 등록부에 이름으로 추가한다. 예: `"vlm": _build_vlm_estimator`
3. 환경 변수(또는 `backend/.env`)로 고른다. 예: `INTAKE_ADAPTER=vlm`

기본 Fake는 외부 의존성이 없어 모듈 상단에서 import한다. 기본 환자 데이터 포트 `sqlite`도
같은 규칙으로 함수 안에서 import한다.

| 등록부 | 설정(환경 변수) | `app.state` 속성 |
| --- | --- | --- |
| `INTAKE_ESTIMATORS` | `INTAKE_ADAPTER` | `intake_estimator` |
| `NUTRITION_ENGINES` | `NUTRITION_ENGINE` | `nutrition_engine` |
| `GUIDELINE_SEARCHES` | `GUIDELINE_SEARCH` | `guideline_search` |
| `PATIENT_DATA_PORTS` | `PATIENT_DATA` | `patient_data` |
| `RECOMMENDATION_GENERATORS` | `RECOMMENDER` | `recommendation_generator` |

테스트는 `monkeypatch.setitem(wiring.<등록부>, "alt", factory)`로 등록해 자동 복원한다.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from app.config import ConfigError, Settings, storage_paths
from app.intake.fake import FakeEstimator
from app.intake.types import IntakeEstimator
from app.nutrition.fake import FakeNutritionEngine
from app.nutrition.types import NutritionEngine
from app.recommender.fake_generator import FakeRecommendationGenerator
from app.recommender.fake_guideline import FakeGuidelineSearch
from app.recommender.generator_types import RecommendationGenerator
from app.recommender.guideline_types import GuidelineSearch
from app.services.fake_patient_data import FakePatientData
from app.services.ports import PatientDataPort
from app.services.runtime import AppRuntime


def _build_claude(settings: Settings) -> IntakeEstimator:
    key = settings.anthropic_api_key
    if key is None or not key.get_secret_value().strip():
        raise ConfigError("INTAKE_ADAPTER=claude requires ANTHROPIC_API_KEY")

    from anthropic import AsyncAnthropic

    from app.intake.claude_estimator import ClaudeIntakeEstimator

    image_root = storage_paths(settings).photos_dir.resolve()
    client = AsyncAnthropic(
        api_key=key.get_secret_value().strip(),
        base_url="https://api.anthropic.com",
        timeout=60.0,
        max_retries=0,
    )
    return ClaudeIntakeEstimator(client=client, allowed_image_root=image_root)


INTAKE_ESTIMATORS: dict[str, Callable[[Settings], IntakeEstimator]] = {
    "fake": lambda settings: FakeEstimator(delay_s=settings.fake_intake_delay_s),
    "claude": _build_claude,
}
NUTRITION_ENGINES: dict[str, Callable[[Settings], NutritionEngine]] = {
    "fake": lambda settings: FakeNutritionEngine(),
}
GUIDELINE_SEARCHES: dict[str, Callable[[Settings], GuidelineSearch]] = {
    "fake": lambda settings: FakeGuidelineSearch(),
}


def _build_sqlite_patient_data(settings: Settings, runtime: AppRuntime) -> PatientDataPort:
    """업무 DB(`app.db`)를 쓰는 포트. 런타임의 쓰기 실행기·시계를 함께 쓴다.

    판단 알고리즘은 `NUTRITION_ENGINE` 설정으로 따로 만든다. 포트와 `app.state.nutrition_engine`은
    인스턴스를 공유하지 않으므로 판단 알고리즘 구현은 상태가 없어야 한다.
    """
    from app.services.sqlite_patient_data import SqlitePatientData

    return SqlitePatientData(
        storage_paths(settings).app_db, runtime, build_nutrition_engine(settings)
    )


PATIENT_DATA_PORTS: dict[str, Callable[[Settings, AppRuntime], PatientDataPort]] = {
    "sqlite": _build_sqlite_patient_data,
    "fake": lambda settings, runtime: FakePatientData(),
}
RECOMMENDATION_GENERATORS: dict[str, Callable[[Settings], RecommendationGenerator]] = {
    "fake": lambda settings: FakeRecommendationGenerator(),
}


@dataclass(frozen=True)
class Components:
    """앱 시작 시 만든 다섯 계약의 구현."""

    intake_estimator: IntakeEstimator
    nutrition_engine: NutritionEngine
    guideline_search: GuidelineSearch
    patient_data: PatientDataPort
    recommendation_generator: RecommendationGenerator


def _lookup[F](registry: Mapping[str, F], setting_name: str, settings: Settings) -> F:
    """등록부에서 설정값 이름의 생성 함수를 찾는다. 없으면 `ConfigError`."""
    name = getattr(settings, setting_name)
    factory = registry.get(name)
    if factory is None:
        registered = ", ".join(sorted(registry))
        raise ConfigError(
            f"{setting_name}={name!r}은 등록되지 않은 구현 이름이다 (등록된 이름: {registered})"
        )
    return factory


def _build[T](
    registry: Mapping[str, Callable[[Settings], T]], setting_name: str, settings: Settings
) -> T:
    """등록부에서 설정값 이름의 생성 함수를 찾아 구현을 만든다."""
    return _lookup(registry, setting_name, settings)(settings)


def build_nutrition_engine(settings: Settings) -> NutritionEngine:
    """`NUTRITION_ENGINE` 설정의 판단 알고리즘을 만든다. 시드 적재도 같은 규칙을 쓴다."""
    return _build(NUTRITION_ENGINES, "nutrition_engine", settings)


def build_components(settings: Settings, runtime: AppRuntime) -> Components:
    """설정값으로 다섯 구현을 만든다. 등록되지 않은 이름이면 `ConfigError`를 던진다.

    환자 데이터 포트에는 `runtime`을 넘긴다. 구현을 만들 때 DB 파일을 열지 않는다.
    """
    port_factory = _lookup(PATIENT_DATA_PORTS, "patient_data", settings)
    return Components(
        intake_estimator=_build(INTAKE_ESTIMATORS, "intake_adapter", settings),
        nutrition_engine=build_nutrition_engine(settings),
        guideline_search=_build(GUIDELINE_SEARCHES, "guideline_search", settings),
        patient_data=port_factory(settings, runtime),
        recommendation_generator=_build(RECOMMENDATION_GENERATORS, "recommender", settings),
    )
