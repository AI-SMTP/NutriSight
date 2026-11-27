"""저장소 테스트 공통 fixture."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.storage.db import connect, create_schema


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """`tmp_path / "app.db"`에 스키마만 만든 빈 DB 경로."""
    path = tmp_path / "app.db"
    with connect(path) as conn:
        create_schema(conn)
    return path
