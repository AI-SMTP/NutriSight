"""추천 생성 서비스 테스트: 성공·실패·잘못된 생성 결과·`auto` 건너뛰기·스냅샷·연결 (스펙 3.5).

취소·동시성은 `test_create_recommendation_concurrency.py`, 시계는
`test_create_recommendation_clock.py`에 있다.
"""

from __future__ import annotations

import asyncio
import logging
import re
import sqlite3
import threading
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from app.nutrition.types import AlertLevel
from app.recommender.fake_generator import FakeRecommendationGenerator
from app.recommender.generator_types import GeneratedCard, GenerationError
from app.services import generation, unit_of_work
from app.services import runtime as runtime_module
from app.services.generation import create_recommendation
from app.services.ports import (
    AddedBy,
    EvidenceRef,
    ModifiedBy,
    PatientNotFoundError,
    RecommendationStatus,
)
from app.storage import recommendations as rec_store
from app.storage.db import connect
from tests.services.cards import read_card
from tests.services.generation import (
    APP_NOW,
    EARLIER_ALERT,
    LATEST_ALERT,
    NEW_ALERT,
    PATIENT,
    GenerationEnvs,
    ScriptedGenerator,
    add_alert,
    add_card,
    statuses,
)
from tests.storage.items import AGENT_ITEM
from tests.storage.rows import insert_alert, insert_recommendation

LOGGER = "app.services.generation"


@pytest.fixture
async def make(service_db: Path) -> AsyncIterator[GenerationEnvs]:
    async with GenerationEnvs(service_db) as factory:
        yield factory


# ── 성공 ──


async def test_manual_creates_active_card_and_supersedes_open_cards(make, service_db):
    add_card(service_db, "R_active", status="active")
    add_card(service_db, "R_failed", status="failed", created_at="2026-12-03T09:00:00.000000")
    add_card(service_db, "R_confirmed", status="confirmed")
    env = make()

    card = await create_recommendation(PATIENT, mode="manual", deps=env.deps)

    assert card is not None
    assert re.fullmatch(r"rec_[0-9a-f]{32}", card.recommendation_id)
    assert card.status is RecommendationStatus.ACTIVE
    assert card.last_modified_by is ModifiedBy.AGENT
    assert card.thread_id is None
    assert card.alert_id == LATEST_ALERT
    assert card.created_at == APP_NOW
    assert card.updated_at == APP_NOW
    summary = env.deps.generator.calls[0][1]
    expected = await FakeRecommendationGenerator().generate(PATIENT, summary)
    assert (card.items, card.cautions) == (expected.items, expected.cautions)
    assert read_card(service_db, card.recommendation_id) == card
    assert statuses(service_db) == {
        "R_active": "superseded",
        "R_failed": "superseded",
        "R_confirmed": "confirmed",
        card.recommendation_id: "active",
    }
    assert env.created() == [
        {
            "recommendation_id": card.recommendation_id,
            "patient_id": PATIENT,
            "status": "active",
            "at": "2026-12-05T09:00:00.000000",
        }
    ]


async def test_generator_receives_14_day_summary_on_demo_date(make):
    env = make()

    await create_recommendation(PATIENT, mode="manual", deps=env.deps)

    patient_id, summary = env.deps.generator.calls[0]
    assert patient_id == PATIENT
    assert (summary.period_start, summary.period_end) == (date(2026, 11, 22), date(2026, 12, 5))
    assert summary.alert is not None
    assert summary.alert.level is AlertLevel.NONE


async def test_manual_for_patient_without_alert_links_no_alert(make, service_db):
    with connect(service_db) as conn:
        conn.execute("DELETE FROM alerts WHERE patient_id = ?", (PATIENT,))
    env = make()

    card = await create_recommendation(PATIENT, mode="manual", deps=env.deps)

    assert card is not None
    assert card.status is RecommendationStatus.ACTIVE
    assert card.alert_id is None
    assert env.deps.generator.calls[0][1].alert is None


async def test_created_event_reaches_bus_subscriber(make):
    env = make()

    async with env.runtime.bus.subscribe() as events:
        card = await create_recommendation(PATIENT, mode="manual", deps=env.deps)
        event = await asyncio.wait_for(anext(events), 5.0)

    assert event.name == "recommendation.created"
    assert event.data["recommendation_id"] == card.recommendation_id


# ── 실패 → failed 카드 ──


def _assert_failed(card, env, service_db) -> None:
    assert card is not None
    assert card.status is RecommendationStatus.FAILED
    assert (card.items, card.cautions) == ((), ())
    assert card.last_modified_by is ModifiedBy.AGENT
    assert card.alert_id == LATEST_ALERT
    assert read_card(service_db, card.recommendation_id) == card
    assert statuses(service_db)["R_old"] == "superseded"
    assert [e["status"] for e in env.created()] == ["failed"]
    assert env.created()[0]["recommendation_id"] == card.recommendation_id


async def test_generation_error_saves_failed_card_and_logs_warning(make, service_db, caplog):
    add_card(service_db, "R_old")
    env = make(generator=ScriptedGenerator(error=GenerationError("모델 오류")))

    with caplog.at_level(logging.WARNING, logger=LOGGER):
        card = await create_recommendation(PATIENT, mode="manual", deps=env.deps)

    _assert_failed(card, env, service_db)
    assert any(r.levelno == logging.WARNING and r.name == LOGGER for r in caplog.records)


async def test_generator_timeout_saves_failed_card(make, service_db, caplog):
    add_card(service_db, "R_old")
    env = make(generator=ScriptedGenerator(gate=asyncio.Event()), timeout_s=0.05)

    with caplog.at_level(logging.WARNING, logger=LOGGER):
        card = await create_recommendation(PATIENT, mode="manual", deps=env.deps)

    _assert_failed(card, env, service_db)
    assert env.deps.generator.active == 0  # 시간 초과로 생성기 대기가 취소됐다
    assert any(r.levelno == logging.WARNING and r.name == LOGGER for r in caplog.records)


def _card(*items, cautions=()) -> GeneratedCard:
    return GeneratedCard(items=tuple(items), cautions=tuple(cautions))


INVALID_RESULTS = {
    "empty_items": _card(),
    "duplicate_item_id": _card(AGENT_ITEM, AGENT_ITEM),
    "malformed_item_id": _card(replace(AGENT_ITEM, item_id="bad id!")),
    "type_enum_value_string": _card(replace(AGENT_ITEM, type="food_fortification")),
    "type_unknown_string": _card(replace(AGENT_ITEM, type="surgery")),
    "empty_title": _card(replace(AGENT_ITEM, title="")),
    "title_101_chars": _card(replace(AGENT_ITEM, title="가" * 101)),
    "duration_zero": _card(replace(AGENT_ITEM, duration_days=0)),
    "duration_bool": _card(replace(AGENT_ITEM, duration_days=True)),
    "review_date_string": _card(replace(AGENT_ITEM, review_date="2026-12-12")),
    "added_by_doctor": _card(replace(AGENT_ITEM, added_by=AddedBy.DOCTOR)),
    "empty_doc_id": _card(replace(AGENT_ITEM, evidence=(EvidenceRef("", "R20"),))),
    "non_string_caution": _card(AGENT_ITEM, cautions=(123,)),
    "not_generated_card": {"items": (AGENT_ITEM,), "cautions": ()},
}


@pytest.mark.parametrize("result", INVALID_RESULTS.values(), ids=INVALID_RESULTS.keys())
async def test_invalid_generated_result_saves_failed_card(make, service_db, caplog, result):
    add_card(service_db, "R_old")
    env = make(generator=ScriptedGenerator(result))

    with caplog.at_level(logging.WARNING, logger=LOGGER):
        card = await create_recommendation(PATIENT, mode="manual", deps=env.deps)

    _assert_failed(card, env, service_db)
    assert any(r.levelno == logging.WARNING and r.name == LOGGER for r in caplog.records)


async def test_unexpected_generator_exception_propagates_without_card(make, service_db):
    add_card(service_db, "R_old")
    env = make(generator=ScriptedGenerator(error=ValueError("계약 밖 예외")))

    with pytest.raises(ValueError, match="계약 밖 예외"):
        await create_recommendation(PATIENT, mode="manual", deps=env.deps)

    assert env.events == []
    assert statuses(service_db) == {"R_old": "active"}


# ── auto 건너뛰기와 manual ──


@pytest.mark.parametrize(
    ("status", "alert_id", "without_alerts"),
    [("active", LATEST_ALERT, False), ("failed", LATEST_ALERT, False), ("active", None, True)],
    ids=["active_latest_alert", "failed_latest_alert", "no_alert_patient_card_without_alert"],
)
async def test_auto_skips_when_current_card_links_latest_alert(
    make, service_db, status, alert_id, without_alerts
):
    if without_alerts:
        with connect(service_db) as conn:
            conn.execute("DELETE FROM alerts WHERE patient_id = ?", (PATIENT,))
    add_card(service_db, "R_old", status=status, alert_id=alert_id)
    env = make()

    result = await create_recommendation(PATIENT, mode="auto", deps=env.deps)

    assert result is None
    assert env.deps.generator.calls == []
    assert statuses(service_db) == {"R_old": status}
    assert env.events == []


@pytest.mark.parametrize(
    ("status", "alert_id"),
    [("active", EARLIER_ALERT), ("failed", EARLIER_ALERT), ("active", None)],
    ids=["active_older_alert", "failed_older_alert", "active_no_alert"],
)
async def test_auto_creates_when_current_card_links_other_alert(make, service_db, status, alert_id):
    add_card(service_db, "R_old", status=status, alert_id=alert_id)
    env = make()

    card = await create_recommendation(PATIENT, mode="auto", deps=env.deps)

    assert card is not None
    assert card.alert_id == LATEST_ALERT
    assert statuses(service_db) == {"R_old": "superseded", card.recommendation_id: "active"}


async def test_auto_creates_when_no_current_card(make, service_db):
    add_card(service_db, "R_confirmed", status="confirmed", alert_id=LATEST_ALERT)
    env = make()

    card = await create_recommendation(PATIENT, mode="auto", deps=env.deps)

    assert card is not None
    assert card.alert_id == LATEST_ALERT


async def test_manual_creates_even_when_current_card_links_latest_alert(make, service_db):
    add_card(service_db, "R_old", alert_id=LATEST_ALERT)
    env = make()

    card = await create_recommendation(PATIENT, mode="manual", deps=env.deps)

    assert card is not None
    assert statuses(service_db) == {"R_old": "superseded", card.recommendation_id: "active"}


async def test_unknown_mode_raises_value_error(make):
    env = make()

    with pytest.raises(ValueError):
        await create_recommendation(PATIENT, mode="later", deps=env.deps)  # type: ignore[arg-type]

    assert env.runtime.tasks.tasks == frozenset()


async def test_missing_patient_raises_not_found_without_card(make, service_db):
    env = make()

    with pytest.raises(PatientNotFoundError):
        await create_recommendation("NS99", mode="manual", deps=env.deps)

    assert env.deps.generator.calls == []
    assert statuses(service_db, "NS99") == {}
    assert env.events == []


# ── 같은 스냅샷의 생성 맥락 ──


def _interleave(monkeypatch, db, *, alert: bool, card: bool) -> None:
    """맥락 읽기의 둘째 조회 직전에 다른 연결로 새 판정·새 카드를 커밋하게 한다."""
    real = generation.latest_alert

    def interleaved(conn: sqlite3.Connection, patient_id: str, on: date):
        with connect(db) as other:
            if alert:
                insert_alert(
                    other,
                    alert_id=NEW_ALERT,
                    patient_id=PATIENT,
                    evaluated_at="2026-12-05T08:00:00",
                    level="warning",
                )
            if card:
                insert_recommendation(
                    other,
                    recommendation_id="R_late",
                    patient_id=PATIENT,
                    alert_id=LATEST_ALERT,
                    created_at="2026-12-05T08:00:00.000000",
                    updated_at="2026-12-05T08:00:00.000000",
                )
        return real(conn, patient_id, on)

    monkeypatch.setattr(generation, "latest_alert", interleaved)


async def test_manual_summary_and_alert_id_come_from_same_snapshot(make, service_db, monkeypatch):
    _interleave(monkeypatch, service_db, alert=True, card=False)
    env = make()

    card = await create_recommendation(PATIENT, mode="manual", deps=env.deps)

    summary = env.deps.generator.calls[0][1]
    assert summary.alert is not None
    assert summary.alert.level is AlertLevel.NONE
    assert card.alert_id == LATEST_ALERT


async def test_auto_compares_with_alert_from_same_snapshot(make, service_db, monkeypatch):
    add_card(service_db, "R_old", alert_id=LATEST_ALERT)
    _interleave(monkeypatch, service_db, alert=True, card=False)
    env = make()

    assert await create_recommendation(PATIENT, mode="auto", deps=env.deps) is None
    assert env.deps.generator.calls == []


async def test_auto_compares_with_current_card_from_same_snapshot(make, service_db, monkeypatch):
    add_card(service_db, "R_old", alert_id=EARLIER_ALERT)
    _interleave(monkeypatch, service_db, alert=False, card=True)
    env = make()

    card = await create_recommendation(PATIENT, mode="auto", deps=env.deps)

    assert card is not None
    assert card.alert_id == LATEST_ALERT
    assert len(env.deps.generator.calls) == 1


async def test_context_is_read_after_new_alert_committed(make, service_db):
    add_alert(service_db, NEW_ALERT, level="warning")
    env = make()

    card = await create_recommendation(PATIENT, mode="manual", deps=env.deps)

    assert card.alert_id == NEW_ALERT
    assert env.deps.generator.calls[0][1].alert.level is AlertLevel.WARNING


# ── 연결 없이 생성기를 기다린다 ──


async def test_generator_waits_without_open_connection(make, monkeypatch):
    log: list[tuple[str, object]] = []
    open_count = [0]
    guard = threading.Lock()

    def tracking(db, fn, *, mode):
        with guard:
            open_count[0] += 1
            log.append(("open", mode))
        try:
            return unit_of_work.run_in_db(db, fn, mode=mode)
        finally:
            with guard:
                open_count[0] -= 1
                log.append(("close", mode))

    monkeypatch.setattr(generation, "run_in_db", tracking)
    monkeypatch.setattr(runtime_module, "run_in_db", tracking)
    generator = ScriptedGenerator(on_enter=lambda: log.append(("generate", open_count[0])))
    env = make(generator=generator)

    await create_recommendation(PATIENT, mode="manual", deps=env.deps)

    assert log == [
        ("open", "snapshot"),
        ("close", "snapshot"),
        ("generate", 0),
        ("open", "write"),
        ("close", "write"),
    ]


# ── 저장 실패 ──


async def test_save_sql_error_propagates_without_event_or_change(make, service_db, monkeypatch):
    add_card(service_db, "R_old")
    before = read_card(service_db, "R_old")

    def boom(conn, **kwargs):
        raise sqlite3.OperationalError("저장 실패")

    monkeypatch.setattr(rec_store, "insert_card", boom)
    env = make()

    with pytest.raises(sqlite3.OperationalError):
        await create_recommendation(PATIENT, mode="manual", deps=env.deps)

    assert env.events == []
    assert statuses(service_db) == {"R_old": "active"}
    assert read_card(service_db, "R_old") == before
