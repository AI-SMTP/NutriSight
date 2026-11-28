"""추천 생성 서비스 테스트: 앱 시계의 자정 넘김·역행 (스펙 3.2 "앱이 만드는 시각").

실제 날짜 2026-11-28에 앱을 시작해 시연일(2026-12-05)과 7일 차이로 시계를 고정한다.
가짜 실제 시각만 바꿔 시연일 23:59:50 → 다음 날 00:00:10, 10초 역행을 만든다.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from app.services import prescriptions as rx_service
from app.services.clock import format_app_timestamp
from app.services.generation import create_recommendation
from app.services.item_rules import ItemEdit
from app.services.ports import PrescriptionType
from app.services.recommendations import (
    StaleRecommendationError,
    current_card,
    edit_by_doctor,
)
from app.services.unit_of_work import run_in_db
from tests.services.generation import PATIENT, GenerationEnvs
from tests.storage.demo import DEMO

REAL_TODAY = date(2026, 11, 28)
OFFSET = DEMO - REAL_TODAY

EDIT = ItemEdit(
    item_id="fortify",
    type=PrescriptionType.FOOD_FORTIFICATION,
    title="식사 강화 10일",
    detail="",
    duration_days=10,
    review_date=None,
)


@pytest.fixture
async def make(service_db: Path) -> AsyncIterator[GenerationEnvs]:
    async with GenerationEnvs(service_db) as factory:
        yield factory


def _set_app_time(env, app_time: datetime) -> None:
    """앱 시각이 `app_time`이 되도록 가짜 실제 시각을 맞춘다."""
    env.now.value = app_time - OFFSET


async def _prescribe(env):
    return await env.runtime.writer.run_write(
        lambda conn: rx_service.create_prescription(conn, PATIENT, (EDIT,), env.runtime.clock.now())
    )


async def test_cards_and_prescriptions_cross_midnight_in_order(make, service_db):
    env = make(today=REAL_TODAY)
    _set_app_time(env, datetime(2026, 12, 5, 23, 59, 50))
    card_a = await create_recommendation(PATIENT, mode="manual", deps=env.deps)
    rx_a = await _prescribe(env)

    _set_app_time(env, datetime(2026, 12, 6, 0, 0, 10))
    card_b = await create_recommendation(PATIENT, mode="manual", deps=env.deps)
    rx_b = await _prescribe(env)

    assert card_a.created_at.date() == DEMO
    assert card_b.created_at == datetime(2026, 12, 6, 0, 0, 10)
    assert rx_b.confirmed_at.startswith("2026-12-06")
    current = run_in_db(service_db, lambda c: current_card(c, PATIENT), mode="read")
    assert current.recommendation_id == card_b.recommendation_id
    history = run_in_db(
        service_db, lambda c: rx_service.list_prescriptions(c, PATIENT), mode="read"
    )
    assert [r.prescription_id for r in history] == [rx_b.prescription_id, rx_a.prescription_id]


async def test_card_created_after_clock_rewind_is_still_latest(make, service_db):
    env = make(today=REAL_TODAY)
    _set_app_time(env, datetime(2026, 12, 5, 10, 0, 0))
    first = await create_recommendation(PATIENT, mode="manual", deps=env.deps)

    _set_app_time(env, datetime(2026, 12, 5, 9, 59, 50))
    second = await create_recommendation(PATIENT, mode="manual", deps=env.deps)

    assert second.created_at == first.created_at + timedelta(microseconds=1)
    assert second.updated_at == second.created_at
    current = run_in_db(service_db, lambda c: current_card(c, PATIENT), mode="read")
    assert current.recommendation_id == second.recommendation_id


async def test_edit_after_clock_rewind_keeps_optimistic_lock(make):
    env = make(today=REAL_TODAY)
    _set_app_time(env, datetime(2026, 12, 5, 10, 0, 0))
    card = await create_recommendation(PATIENT, mode="manual", deps=env.deps)
    old_text = format_app_timestamp(card.updated_at)

    _set_app_time(env, datetime(2026, 12, 5, 9, 59, 50))
    edited = await env.runtime.writer.run_write(
        lambda conn: edit_by_doctor(
            conn, card.recommendation_id, (EDIT,), old_text, env.runtime.clock.now()
        )
    )

    assert edited.updated_at > card.updated_at
    with pytest.raises(StaleRecommendationError):
        await env.runtime.writer.run_write(
            lambda conn: edit_by_doctor(
                conn, card.recommendation_id, (EDIT,), old_text, env.runtime.clock.now()
            )
        )
    new_text = format_app_timestamp(edited.updated_at)
    again = await env.runtime.writer.run_write(
        lambda conn: edit_by_doctor(
            conn, card.recommendation_id, (EDIT,), new_text, env.runtime.clock.now()
        )
    )
    assert again.updated_at > edited.updated_at
