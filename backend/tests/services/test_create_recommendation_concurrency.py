"""추천 생성 서비스 테스트: 취소 보호·환자별 잠금·생성 중 다른 쓰기 (스펙 3.2 취소 보호, 3.5 표).

생성기는 `asyncio.Event`, 쓰기 실행기 저장은 `threading.Event`로 멈추고 풀어 순서를 정한다.
기다림은 모두 `TIMEOUT` 상한을 둔다.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import sqlite3
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from app.services.clock import format_app_timestamp
from app.services.generation import create_recommendation
from app.services.item_rules import ItemEdit
from app.services.ports import (
    PrescriptionType,
    RecommendationNotEditableError,
    RecommendationStatus,
)
from app.services.recommendations import confirm_recommendation, edit_by_doctor
from app.storage import recommendations as rec_store
from app.storage.db import connect
from tests.services.cards import read_card
from tests.services.generation import (
    EARLIER_ALERT,
    GEN_STORED_AT,
    LATEST_ALERT,
    PATIENT,
    TIMEOUT,
    GenerationEnvs,
    RecordingLocks,
    ScriptedGenerator,
    WriteGate,
    add_card,
    statuses,
    wait_set,
)

RUNTIME_LOGGER = "app.services.runtime"  # 호출자 취소 뒤 본문 실패 로그는 런타임이 남긴다
SETTLE_S = 0.2  # 결함이 드러날 시간(올바른 구현의 결과와 무관)

EDIT = ItemEdit(
    item_id="rx1",
    type=PrescriptionType.FOOD_FORTIFICATION,
    title="식사 강화 14일",
    detail="의사가 고침",
    duration_days=14,
    review_date=None,
)


@pytest.fixture
async def make(service_db: Path) -> AsyncIterator[GenerationEnvs]:
    async with GenerationEnvs(service_db) as factory:
        yield factory


def _start(env, mode: str = "manual") -> asyncio.Task:
    return asyncio.create_task(create_recommendation(PATIENT, mode=mode, deps=env.deps))


async def _cancel(task: asyncio.Task) -> None:
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


# ── 취소 보호 ──


async def test_caller_cancel_during_generation_still_saves_card(make, service_db):
    add_card(service_db, "R_old")
    gate = asyncio.Event()
    env = make(generator=ScriptedGenerator(gate=gate))
    caller = _start(env)
    await wait_set(env.deps.generator.entered)

    await _cancel(caller)
    gate.set()
    await env.drain()

    created = env.created()
    assert [e["status"] for e in created] == ["active"]
    new_id = created[0]["recommendation_id"]
    assert statuses(service_db) == {"R_old": "superseded", new_id: "active"}


async def test_cancelled_save_commits_before_next_generation(make, service_db, monkeypatch):
    add_card(service_db, "R_old")
    gate = WriteGate(monkeypatch)
    locks = RecordingLocks()
    published_at_enter: list[int] = []
    second_entered = asyncio.Event()

    def on_enter() -> None:
        published_at_enter.append(len(env.created()))
        if len(published_at_enter) == 2:
            second_entered.set()

    env = make(generator=ScriptedGenerator(on_enter=on_enter), locks=locks)
    first = _start(env)
    await gate.wait_entered()

    await _cancel(first)
    second = _start(env)
    await wait_set(locks.second_request)  # 둘째가 첫째의 저장이 끝나기 전에 잠금을 요청했다
    # 잠금이 첫 본문에 묶여 있으면 둘째 생성기는 저장이 풀릴 때까지 들어오지 못한다. 잠금이
    # 호출자 쪽에 있으면(취소와 함께 풀리면) 여기서 들어온다. 이 기다림은 그런 결함이 드러날
    # 시간을 줄 뿐이고, 올바른 구현의 결과는 기다림 길이와 무관하다.
    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(second_entered.wait(), SETTLE_S)
    gate.release.set()
    second_card = await asyncio.wait_for(second, TIMEOUT)
    await env.drain()

    # 둘째 생성기는 첫 카드가 커밋·발행된 뒤에야 들어왔다(잠금을 첫 본문이 끝까지 쥐었다).
    assert published_at_enter == [0, 1]
    created = env.created()
    assert len(created) == 2
    first_id = created[0]["recommendation_id"]
    assert created[1]["recommendation_id"] == second_card.recommendation_id
    assert statuses(service_db) == {
        "R_old": "superseded",
        first_id: "superseded",
        second_card.recommendation_id: "active",
    }


async def test_body_failure_after_caller_cancel_is_logged_once(
    make, service_db, monkeypatch, caplog
):
    add_card(service_db, "R_old")
    gate = WriteGate(monkeypatch)

    def boom(conn, **kwargs):
        raise sqlite3.OperationalError("저장 실패")

    monkeypatch.setattr(rec_store, "insert_card", boom)
    env = make()
    caller = _start(env)
    await gate.wait_entered()

    with caplog.at_level(logging.ERROR, logger=RUNTIME_LOGGER):
        await _cancel(caller)
        gate.release.set()
        await env.drain()
        await asyncio.sleep(0)  # 완료 콜백은 태스크가 끝난 다음 차례에 실행된다

    errors = [r for r in caplog.records if r.name == RUNTIME_LOGGER and r.levelno == logging.ERROR]
    assert len(errors) == 1
    assert PATIENT in errors[0].getMessage()
    assert isinstance(errors[0].exc_info[1], sqlite3.OperationalError)
    assert env.events == []
    assert statuses(service_db) == {"R_old": "active"}


# ── 환자별 잠금 ──


async def test_auto_waiting_on_lock_reads_card_saved_by_previous_generation(make, service_db):
    add_card(service_db, "R_old", alert_id=EARLIER_ALERT)
    locks = RecordingLocks()
    gate = asyncio.Event()
    env = make(generator=ScriptedGenerator(gate=gate), locks=locks)
    first = _start(env, "auto")
    await wait_set(env.deps.generator.entered)

    second = _start(env, "auto")
    await wait_set(locks.second_request)
    assert locks.get(PATIENT).locked()  # 첫 생성이 생성기 대기 중에도 잠금을 쥐고 있다
    gate.set()
    first_card, second_result = await asyncio.wait_for(asyncio.gather(first, second), TIMEOUT)

    assert first_card is not None
    assert first_card.alert_id == LATEST_ALERT
    assert second_result is None
    assert len(env.deps.generator.calls) == 1
    assert statuses(service_db) == {"R_old": "superseded", first_card.recommendation_id: "active"}


async def test_concurrent_manual_creates_two_cards_in_lock_order(make, service_db):
    add_card(service_db, "R_old")
    env = make()

    first, second = await asyncio.wait_for(asyncio.gather(_start(env), _start(env)), TIMEOUT)

    assert env.deps.generator.max_active == 1
    assert [e["recommendation_id"] for e in env.created()] == [
        first.recommendation_id,
        second.recommendation_id,
    ]
    assert statuses(service_db) == {
        "R_old": "superseded",
        first.recommendation_id: "superseded",
        second.recommendation_id: "active",
    }


async def test_locks_are_per_patient(make, service_db):
    gate = asyncio.Event()
    env = make(generator=ScriptedGenerator(gate=gate, gate_calls=frozenset({1})))
    blocked = _start(env)
    await wait_set(env.deps.generator.entered)

    other = await asyncio.wait_for(
        create_recommendation("NS01", mode="manual", deps=env.deps), TIMEOUT
    )
    gate.set()
    mine = await asyncio.wait_for(blocked, TIMEOUT)

    assert other.patient_id == "NS01"
    assert mine.patient_id == PATIENT


# ── 생성 중 다른 쓰기 (스펙 3.5 표) ──


async def test_patch_during_generation_keeps_edit_on_superseded_card(make, service_db):
    add_card(service_db, "R_old")
    gate = asyncio.Event()
    env = make(generator=ScriptedGenerator(gate=gate))
    task = _start(env)
    await wait_set(env.deps.generator.entered)

    edited = await env.runtime.writer.run_write(
        lambda conn: edit_by_doctor(conn, "R_old", (EDIT,), GEN_STORED_AT, env.runtime.clock.now())
    )
    gate.set()
    new = await asyncio.wait_for(task, TIMEOUT)

    old = read_card(service_db, "R_old")
    assert old.status is RecommendationStatus.SUPERSEDED
    assert old.items == edited.items
    assert old.items[0].title == "식사 강화 14일"
    assert new.status is RecommendationStatus.ACTIVE
    with pytest.raises(RecommendationNotEditableError):
        await env.runtime.writer.run_write(
            lambda conn: edit_by_doctor(
                conn,
                "R_old",
                (EDIT,),
                format_app_timestamp(edited.updated_at),
                env.runtime.clock.now(),
            )
        )


async def test_confirm_during_generation_keeps_confirmed_card(make, service_db):
    add_card(service_db, "R_old")
    gate = asyncio.Event()
    env = make(generator=ScriptedGenerator(gate=gate))
    task = _start(env)
    await wait_set(env.deps.generator.entered)

    await env.runtime.writer.run_write(
        lambda conn: confirm_recommendation(
            conn, "R_old", ("rx1",), GEN_STORED_AT, env.runtime.clock.now()
        )
    )
    gate.set()
    new = await asyncio.wait_for(task, TIMEOUT)

    with connect(service_db) as conn:
        prescriptions = conn.execute(
            "SELECT recommendation_id FROM prescriptions WHERE patient_id = ?", (PATIENT,)
        ).fetchall()
    assert [row["recommendation_id"] for row in prescriptions] == ["R_old"]
    assert statuses(service_db) == {"R_old": "confirmed", new.recommendation_id: "active"}


async def test_task_cancelled_after_caller_cancel_logs_no_error(make, service_db, caplog):
    gate = asyncio.Event()
    env = make(generator=ScriptedGenerator(gate=gate))
    caller = _start(env)
    await wait_set(env.deps.generator.entered)

    with caplog.at_level(logging.ERROR, logger=RUNTIME_LOGGER):
        await _cancel(caller)
        await env.runtime.tasks.cancel_all()  # 종료 정책: 남은 생성 태스크를 취소한다
        await asyncio.sleep(0)

    assert [r for r in caplog.records if r.name == RUNTIME_LOGGER] == []
    assert statuses(service_db) == {}
    assert env.events == []
