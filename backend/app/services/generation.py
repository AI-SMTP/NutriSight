"""추천 카드 생성 서비스 (스펙 3.5 "생성 서비스", 3.2 취소 보호).

`create_recommendation`은 비동기다. 본문 전체(환자별 잠금 → 같은 스냅샷의 맥락 읽기 → 연결 없이
생성기 대기 → 한 트랜잭션 저장 → 쓰기 실행기 안 발행 → 잠금 해제)를 앱 소유 태스크 하나에서
돌리고 호출자는 `TaskRegistry.run_shielded`로 기다린다(호출자가 취소된 뒤 본문이 실패하면
ERROR 로그로 남는다). 카드 조회·수정·확정(`app.services.recommendations`)과는 서로 import하지
않고 저장소 SQL(`app.storage.recommendations`)만 함께 쓴다.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import Literal

from app.events.bus import Event
from app.nutrition.types import NutritionEngine
from app.recommender.generator_types import (
    GeneratedCard,
    GenerationError,
    RecommendationGenerator,
)
from app.services.clock import next_timestamp
from app.services.item_rules import validate_generated_card
from app.services.patients import intake_summary, latest_alert
from app.services.ports import (
    IntakeSummary,
    ModifiedBy,
    RecommendationCard,
    RecommendationStatus,
)
from app.services.runtime import AppRuntime
from app.services.unit_of_work import WriteResult, run_in_db
from app.storage import queries
from app.storage import recommendations as rec_store

logger = logging.getLogger(__name__)

CREATED_EVENT = "recommendation.created"
RECOMMENDATION_ID_PREFIX = "rec_"
SUMMARY_DAYS = 14  # 생성기 입력 요약 기간(포트 `get_intake_summary(patient_id, 14, 시연일)`과 같다)
GenerationMode = Literal["manual", "auto"]
_MODES: frozenset[str] = frozenset({"manual", "auto"})


class PatientLocks:
    """환자별 `asyncio.Lock` 사전. 같은 환자의 생성을 잠금 순서대로 하나씩 실행한다.

    이벤트 루프 스레드에서만 쓴다.
    """

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}

    def get(self, patient_id: str) -> asyncio.Lock:
        """그 환자의 잠금. 처음 부르면 만든다."""
        lock = self._locks.get(patient_id)
        if lock is None:
            lock = self._locks[patient_id] = asyncio.Lock()
        return lock


@dataclass(frozen=True)
class RecommendationDeps:
    """추천 생성·경고 훅이 쓰는 의존성 묶음 (`app.state.recommendation_deps`)."""

    generator: RecommendationGenerator
    runtime: AppRuntime
    db_path: Path
    engine: NutritionEngine
    locks: PatientLocks
    timeout_s: float  # 생성기 시간 제한(초), 설정 `recommendation_timeout_s`


@dataclass(frozen=True)
class GenerationContext:
    """한 스냅샷에서 읽은 생성 맥락."""

    summary: IntakeSummary
    alert_id: str | None  # 요약 `alert`에 해당하는 최신 판정 ID. 판정이 없으면 None
    current: RecommendationCard | None  # 현재 카드(`active`·`failed` 중 가장 늦은 것)


def read_generation_context(
    conn: sqlite3.Connection, engine: NutritionEngine, patient_id: str
) -> GenerationContext:
    """요약·최신 판정 ID·현재 카드를 읽는다. `mode="snapshot"` 연결에서 불러야 서로 일치한다.

    없는 환자 → `PatientNotFoundError`.
    """
    on = queries.get_demo_date(conn)
    summary = intake_summary(conn, engine, patient_id, SUMMARY_DAYS, on)
    alert = latest_alert(conn, patient_id, on)
    return GenerationContext(
        summary=summary,
        alert_id=None if alert is None else alert.alert_id,
        current=rec_store.select_current_card(conn, patient_id),
    )


def _already_current(context: GenerationContext) -> bool:
    """현재 카드가 이미 최신 판정에 대한 카드인가(`auto` 건너뛰기 조건)."""
    return context.current is not None and context.current.alert_id == context.alert_id


def save_generated_card(
    conn: sqlite3.Connection,
    patient_id: str,
    alert_id: str | None,
    generated: GeneratedCard | None,
    now: datetime,
) -> WriteResult[RecommendationCard]:
    """그 환자의 `active`·`failed` 카드를 `superseded`로 바꾸고 새 카드를 넣는다(같은 트랜잭션).

    `generated`가 있으면 `active`, `None`이면 항목·주의 문구가 빈 `failed` 카드다. 시각은 `now`와
    그 환자 카드의 최대 `created_at + 1µs` 중 큰 값이다. 이벤트는 `recommendation.created` 하나다.
    """
    rec_store.supersede_open_cards(conn, patient_id)
    _, created_at = next_timestamp(now, rec_store.max_card_created_at(conn, patient_id))
    succeeded = generated is not None
    status = RecommendationStatus.ACTIVE if succeeded else RecommendationStatus.FAILED
    recommendation_id = f"{RECOMMENDATION_ID_PREFIX}{uuid.uuid4().hex}"
    rec_store.insert_card(
        conn,
        recommendation_id=recommendation_id,
        patient_id=patient_id,
        alert_id=alert_id,
        items=generated.items if succeeded else (),
        cautions=generated.cautions if succeeded else (),
        last_modified_by=ModifiedBy.AGENT,
        thread_id=None,
        created_at=created_at,
        updated_at=created_at,
        status=status,
    )
    card = rec_store.select_card(conn, recommendation_id)
    if card is None:
        raise RuntimeError(f"방금 넣은 카드를 읽지 못했다: {recommendation_id}")
    event = Event(
        CREATED_EVENT,
        {
            "recommendation_id": recommendation_id,
            "patient_id": patient_id,
            "status": status.value,
            "at": created_at,
        },
    )
    return WriteResult(card, (event,))


async def _generate(
    deps: RecommendationDeps, patient_id: str, summary: IntakeSummary
) -> GeneratedCard | None:
    """생성기를 시간 제한 안에서 기다리고 결과를 검증한다. 실패면 WARNING 로그 후 `None`.

    실패로 보는 것은 `GenerationError`·시간 초과·검증 실패(`ValueError`)뿐이다. 그 밖의 생성기
    예외는 계약 위반이라 그대로 올린다(카드를 저장하지 않는다).
    """
    try:
        result = await asyncio.wait_for(
            deps.generator.generate(patient_id, summary), deps.timeout_s
        )
    except TimeoutError:
        logger.warning("추천 생성 시간 초과(%.1f초): %s", deps.timeout_s, patient_id)
        return None
    except GenerationError as err:
        logger.warning("추천 생성 실패: %s (%s)", patient_id, err)
        return None
    try:
        validate_generated_card(result)
    except ValueError as err:
        logger.warning("추천 생성 결과가 규칙을 어겼다: %s (%s)", patient_id, err)
        return None
    return result


async def _create_body(
    patient_id: str, mode: GenerationMode, deps: RecommendationDeps
) -> RecommendationCard | None:
    """생성 본문. 잠금 안에서 맥락 읽기 → 생성기 대기(연결 없음) → 저장·발행을 한다."""
    async with deps.locks.get(patient_id):
        context = await asyncio.to_thread(
            run_in_db,
            deps.db_path,
            partial(read_generation_context, engine=deps.engine, patient_id=patient_id),
            mode="snapshot",
        )
        if mode == "auto" and _already_current(context):
            return None
        generated = await _generate(deps, patient_id, context.summary)
        save = partial(
            save_generated_card,
            patient_id=patient_id,
            alert_id=context.alert_id,
            generated=generated,
            now=deps.runtime.clock.now(),
        )
        return await deps.runtime.writer.run_write(save)


async def create_recommendation(
    patient_id: str, *, mode: GenerationMode, deps: RecommendationDeps
) -> RecommendationCard | None:
    """추천 카드를 만든다. `manual`은 항상, `auto`는 현재 카드가 최신 판정의 것이 아닐 때만.

    본문은 앱 소유 태스크에서 돌아 호출자가 취소돼도 끝까지 실행된다(저장·발행 포함).
    생성 실패(`GenerationError`·시간 초과·검증 실패)는 `failed` 카드로 저장하고 예외를 올리지
    않는다. 그 밖의 생성기 예외는 그대로 올린다. 호출자가 취소된 뒤 본문이 실패하면 ERROR 로그로
    남긴다. 없는 환자 → `PatientNotFoundError`, 저장 실패 → 저장 예외(이벤트 없음),
    `auto`에서 건너뛰면 `None`, 알 수 없는 `mode` → `ValueError`.
    """
    if mode not in _MODES:
        raise ValueError(f"지원하지 않는 mode: {mode!r}")
    return await deps.runtime.tasks.run_shielded(
        _create_body(patient_id, mode, deps), label=patient_id
    )
