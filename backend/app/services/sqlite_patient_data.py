"""`PatientDataPort`의 SQLite 구현(스펙 3.8). 읽기는 `to_thread`, 쓰기는 `run_shielded` + 실행기.

Fake와 다른 점: 없는 `thread_id`는 `sqlite3.IntegrityError`, 없는 카드에 잘못된 항목은 항목 검사가
먼저라 `ValueError`(Fake는 `RecommendationNotFoundError`)다. 계약은 두 경우를 검사하지 않는다.
"""

from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import Callable
from datetime import date
from pathlib import Path

from app.nutrition.types import NutritionEngine
from app.services import patients
from app.services import recommendations as rec_service
from app.services.ports import (
    IntakeSummary,
    ModifiedBy,
    RecommendationCard,
    RecommendationItem,
)
from app.services.runtime import AppRuntime
from app.services.unit_of_work import WriteResult, run_in_db


class SqlitePatientData:
    """업무 DB(`app.db`)를 읽고 추천 카드를 고치는 환자 데이터 포트."""

    def __init__(self, db_path: Path, runtime: AppRuntime, engine: NutritionEngine) -> None:
        """`db_path`가 런타임 쓰기 실행기의 DB 경로와 다르면 `ValueError`. DB 파일은 열지 않는다."""
        if db_path.resolve() != runtime.writer.db_path.resolve():
            raise ValueError(
                f"포트 DB 경로가 쓰기 실행기 경로와 다르다: {db_path} != {runtime.writer.db_path}"
            )
        self._db_path = db_path
        self._runtime = runtime
        self._engine = engine

    async def _read[T](self, fn: Callable[[sqlite3.Connection], T]) -> T:
        return await asyncio.to_thread(run_in_db, self._db_path, fn, mode="read")

    async def get_intake_summary(self, patient_id: str, days: int, on: date) -> IntakeSummary:
        return await self._read(
            lambda conn: patients.intake_summary(conn, self._engine, patient_id, days, on)
        )

    async def get_recommendation(self, patient_id: str) -> RecommendationCard | None:
        return await self._read(lambda conn: rec_service.current_card(conn, patient_id))

    async def update_recommendation(
        self,
        recommendation_id: str,
        items: tuple[RecommendationItem, ...],
        modified_by: ModifiedBy,
        thread_id: str | None,
    ) -> RecommendationCard:
        """받은 항목을 그대로 저장한다(3.3절 병합 없음, 잠금 비교 없음)."""
        now = self._runtime.clock.now()

        def write(conn: sqlite3.Connection) -> WriteResult[RecommendationCard]:
            # 호출 시점에 모듈 속성으로 찾아, 모든 수정이 `save_items` 한 곳을 거치게 한다.
            return rec_service.save_items(
                conn, recommendation_id, items, modified_by, thread_id, None, now
            )

        return await self._runtime.tasks.run_shielded(
            self._runtime.writer.run_write(write),
            label=f"포트 추천 카드 수정 {recommendation_id}",
        )
