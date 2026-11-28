"""저장소 테스트 공통 fixture."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from app.config import DEFAULT_SEED_PATH
from app.nutrition.fake import FakeNutritionEngine
from app.storage.seed import build_database, load_seed_file
from tests.storage.demo import DEMO
from tests.storage.dump import TableDump, table_dump


@pytest.fixture(scope="session")
def pending_db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """실제 시드를 D=2026-12-05, `cleanup_pending=True`로 적재한 DB. 복사해서만 쓴다."""
    path = tmp_path_factory.mktemp("pending") / "app.db"
    seed = load_seed_file(DEFAULT_SEED_PATH)
    build_database(path, seed, DEMO, FakeNutritionEngine(), cleanup_pending=True)
    return path


@pytest.fixture(scope="session")
def fresh_dump(tmp_path_factory: pytest.TempPathFactory, seeded_db: Path) -> TableDump:
    """같은 D로 새로 적재한 DB의 전체 내용(`seeded_at` 제외)."""
    copy = tmp_path_factory.mktemp("fresh") / "app.db"
    shutil.copyfile(seeded_db, copy)
    return table_dump(copy)
