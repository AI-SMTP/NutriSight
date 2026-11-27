"""시드·리셋 진입점 모음 (스펙 3.7, 3.8).

구현은 역할별 모듈에 둔다.
- `seed_file.py`: 시드 파일 읽기·검증, 시연일 범위 검사
- `seed_load.py`: 시드 적재(`build_database`)와 엔진 선택(`build_engine`)
- `seed_reset.py`: 리셋 절차와 교체 뒤 정리, 앱 시작 때 저장소 준비(`ensure_storage`)

테스트의 장애 주입은 함수가 정의된 모듈(`seed_reset` 등)의 속성을 덮어쓴다.
"""

from __future__ import annotations

from app.storage.seed_file import check_demo_date_range, load_seed_file
from app.storage.seed_load import (
    CLEANUP_PENDING_KEY,
    SeedCounts,
    build_database,
    build_engine,
)
from app.storage.seed_reset import (
    ResetResult,
    ensure_storage,
    finish_cleanup,
    rebuild_storage,
    reset_storage,
)

__all__ = [
    "CLEANUP_PENDING_KEY",
    "ResetResult",
    "SeedCounts",
    "build_database",
    "build_engine",
    "check_demo_date_range",
    "ensure_storage",
    "finish_cleanup",
    "load_seed_file",
    "rebuild_storage",
    "reset_storage",
]
