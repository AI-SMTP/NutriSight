"""서비스 테스트 공통 fixture.

빈 스키마 `db_path`와 시드 `seeded_db`는 `tests/conftest.py`에 있다.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from app.nutrition.fake import FakeNutritionEngine
from app.nutrition.types import DailyTarget, PatientProfile, Sex
from tests.storage.demo import DEMO


@pytest.fixture
def service_db(tmp_path: Path, seeded_db: Path) -> Path:
    """테스트마다 새로 복사한 시드 DB 경로. 테스트끼리 상태를 나누지 않는다."""
    path = tmp_path / "seeded.db"
    shutil.copyfile(seeded_db, path)
    return path


@pytest.fixture
def engine() -> FakeNutritionEngine:
    """서비스 테스트가 쓰는 판단 엔진(고정 목표 1500 kcal·55 g, `kdri`)."""
    return FakeNutritionEngine()


@pytest.fixture
def fake_target(engine: FakeNutritionEngine) -> DailyTarget:
    """`engine`이 입력과 무관하게 돌려주는 고정 목표."""
    return engine.daily_target(PatientProfile(Sex.FEMALE, 1940), (), (), DEMO)
