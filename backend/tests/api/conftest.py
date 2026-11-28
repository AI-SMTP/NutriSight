"""API 테스트 공통 fixture.

모듈마다 시드 DB(D=2026-12-05)를 새 `VAR_DIR/app.db`로 복사하고 `DEMO_DATE`를 시연일로 고정한
앱을 한 번만 시작한다(같은 앱 인스턴스는 두 번 시작할 수 없다). 테스트가 넣는 행은
`scratch`로 넣어 테스트가 끝나면 지운다.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, storage_paths
from app.main import create_app
from tests.api.scratch import ScratchRows
from tests.conftest import install_app_db
from tests.storage.demo import DEMO


def make_api_settings(root: Path, seeded_db: Path, **overrides: object) -> Settings:
    """`root/var/app.db`에 시드 DB를 복사하고 그 `VAR_DIR`·시연일을 쓰는 설정을 만든다."""
    var_dir = root / "var"
    install_app_db(var_dir, seeded_db)
    return Settings(_env_file=None, var_dir=var_dir, demo_date=DEMO.isoformat(), **overrides)


@pytest.fixture(scope="module")
def api_settings(tmp_path_factory: pytest.TempPathFactory, seeded_db: Path) -> Settings:
    """모듈 하나가 함께 쓰는 앱 설정."""
    return make_api_settings(tmp_path_factory.mktemp("api"), seeded_db)


@pytest.fixture(scope="module")
def api_db(api_settings: Settings) -> Path:
    """모듈 앱이 쓰는 `app.db` 경로."""
    return storage_paths(api_settings).app_db


@pytest.fixture(scope="module")
def client(api_settings: Settings) -> Iterator[TestClient]:
    """lifespan을 실행한(시작된) 모듈 앱 클라이언트."""
    with TestClient(create_app(api_settings)) as test_client:
        yield test_client


@pytest.fixture
def scratch(api_db: Path) -> Iterator[ScratchRows]:
    """테스트 동안만 남는 행 넣기 도우미."""
    rows = ScratchRows(api_db)
    yield rows
    rows.cleanup()


@pytest.fixture
def write_settings(tmp_path: Path, seeded_db: Path) -> Settings:
    """테스트 하나만 쓰는 앱 설정. DB를 바꾸는 테스트(쓰기 API)가 쓴다."""
    return make_api_settings(tmp_path / "write", seeded_db)


@pytest.fixture
def write_client(write_settings: Settings) -> Iterator[TestClient]:
    """테스트마다 새로 시작하는 앱 클라이언트. 테스트끼리·모듈 앱과 DB를 나누지 않는다.

    서버 예외를 500 응답으로 받아야 하면 `write_settings`로 직접
    `TestClient(create_app(write_settings), raise_server_exceptions=False)`를 연다.
    """
    with TestClient(create_app(write_settings)) as test_client:
        yield test_client
