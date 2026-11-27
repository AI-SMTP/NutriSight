"""설정 이름으로 네 계약의 구현을 만드는 등록부.

계약마다 `이름 → 생성 함수(Settings)` 등록부가 있고, `Settings`의 해당 값으로 구현을 고른다.

병행 트랙이 실제 구현을 추가하는 방법:

1. 구현 모듈에 `def build_xxx(settings: Settings) -> <계약>` 생성 함수를 만든다.
2. 아래 해당 등록부에 이름으로 추가한다. 예: `INTAKE_ESTIMATORS["vlm"] = build_vlm_estimator`
3. 환경 변수(또는 `backend/.env`)로 고른다. 예: `INTAKE_ADAPTER=vlm`

| 등록부 | 설정(환경 변수) | `app.state` 속성 |
| --- | --- | --- |
| `INTAKE_ESTIMATORS` | `INTAKE_ADAPTER` | `intake_estimator` |
| `NUTRITION_ENGINES` | `NUTRITION_ENGINE` | `nutrition_engine` |
| `GUIDELINE_SEARCHES` | `GUIDELINE_SEARCH` | `guideline_search` |
| `PATIENT_DATA_PORTS` | `PATIENT_DATA` | `patient_data` |

테스트는 `monkeypatch.setitem(wiring.<등록부>, "alt", factory)`로 등록해 자동 복원한다.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from app.config import ConfigError, Settings
from app.intake.fake import FakeEstimator
from app.intake.types import IntakeEstimator
from app.nutrition.fake import FakeNutritionEngine
from app.nutrition.types import NutritionEngine
from app.recommender.fake_guideline import FakeGuidelineSearch
from app.recommender.guideline_types import GuidelineSearch
from app.services.fake_patient_data import FakePatientData
from app.services.ports import PatientDataPort

INTAKE_ESTIMATORS: dict[str, Callable[[Settings], IntakeEstimator]] = {
    "fake": lambda settings: FakeEstimator(delay_s=settings.fake_intake_delay_s),
}
NUTRITION_ENGINES: dict[str, Callable[[Settings], NutritionEngine]] = {
    "fake": lambda settings: FakeNutritionEngine(),
}
GUIDELINE_SEARCHES: dict[str, Callable[[Settings], GuidelineSearch]] = {
    "fake": lambda settings: FakeGuidelineSearch(),
}
PATIENT_DATA_PORTS: dict[str, Callable[[Settings], PatientDataPort]] = {
    "fake": lambda settings: FakePatientData(),
}


@dataclass(frozen=True)
class Components:
    """앱 시작 시 만든 네 계약의 구현."""

    intake_estimator: IntakeEstimator
    nutrition_engine: NutritionEngine
    guideline_search: GuidelineSearch
    patient_data: PatientDataPort


def _build[T](
    registry: Mapping[str, Callable[[Settings], T]], setting_name: str, settings: Settings
) -> T:
    """등록부에서 설정값 이름의 생성 함수를 찾아 구현을 만든다."""
    name = getattr(settings, setting_name)
    factory = registry.get(name)
    if factory is None:
        registered = ", ".join(sorted(registry))
        raise ConfigError(
            f"{setting_name}={name!r}은 등록되지 않은 구현 이름이다 (등록된 이름: {registered})"
        )
    return factory(settings)


def build_components(settings: Settings) -> Components:
    """설정값으로 네 구현을 만든다. 등록되지 않은 이름이면 `ConfigError`를 던진다."""
    return Components(
        intake_estimator=_build(INTAKE_ESTIMATORS, "intake_adapter", settings),
        nutrition_engine=_build(NUTRITION_ENGINES, "nutrition_engine", settings),
        guideline_search=_build(GUIDELINE_SEARCHES, "guideline_search", settings),
        patient_data=_build(PATIENT_DATA_PORTS, "patient_data", settings),
    )
