"""경고 상승 훅 `on_alert_evaluated` 테스트 (스펙 3.6, 3.5 "판정이 이어서 바뀔 때").

생성기는 `asyncio.Event`, 쓰기 실행기 저장은 `threading.Event`(`WriteGate`)로 멈추고 풀어 순서를
정한다. 기다림은 모두 `TIMEOUT` 상한을 둔다.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from app.nutrition.types import AlertLevel
from app.recommender.generator_types import GenerationError
from app.services.generation import on_alert_evaluated
from app.services.ports import RecommendationCard, RecommendationStatus
from app.storage.db import connect
from tests.services.generation import (
    LATEST_ALERT,
    PATIENT,
    TIMEOUT,
    GenerationEnv,
    GenerationEnvs,
    RecordingLocks,
    ScriptedGenerator,
    WriteGate,
    add_alert,
    add_card,
    statuses,
    wait_set,
)
from tests.storage.rows import insert_alert

FIRST_ALERT = "alert_NS07_hook_1"
SECOND_ALERT = "alert_NS07_hook_2"
FIRST_AT = "2026-12-05T08:00:00"
SECOND_AT = "2026-12-05T09:00:00"


@pytest.fixture
async def make(service_db: Path) -> AsyncIterator[GenerationEnvs]:
    async with GenerationEnvs(service_db) as factory:
        yield factory


async def _run(
    env: GenerationEnv, previous: AlertLevel | None, alert_id: str
) -> RecommendationCard | None:
    """`TIMEOUT` 상한 안에서 훅을 기다린다."""
    return await asyncio.wait_for(
        on_alert_evaluated(PATIENT, previous, alert_id, deps=env.deps), TIMEOUT
    )


def _hook(
    env: GenerationEnv, previous: AlertLevel | None, alert_id: str
) -> asyncio.Task[RecommendationCard | None]:
    return asyncio.create_task(_run(env, previous, alert_id))


# ── 상승 판정 ──


@pytest.mark.parametrize(
    ("previous", "level"),
    [
        (AlertLevel.NONE, "caution"),
        (AlertLevel.CAUTION, "warning"),
        (AlertLevel.NONE, "warning"),
        (None, "caution"),
    ],
)
async def test_rise_creates_card_for_latest_alert(make, service_db, previous, level):
    add_alert(service_db, FIRST_ALERT, level=level, evaluated_at=FIRST_AT)
    env = make()

    card = await _run(env, previous, FIRST_ALERT)

    assert card is not None
    assert card.status == RecommendationStatus.ACTIVE
    assert card.alert_id == FIRST_ALERT
    assert len(env.deps.generator.calls) == 1
    assert statuses(service_db) == {card.recommendation_id: "active"}


@pytest.mark.parametrize(
    ("previous", "level"),
    [
        (AlertLevel.CAUTION, "caution"),
        (AlertLevel.WARNING, "caution"),
        (None, "none"),
    ],
)
async def test_same_or_lower_level_does_nothing(make, service_db, previous, level):
    add_alert(service_db, FIRST_ALERT, level=level, evaluated_at=FIRST_AT)
    env = make()

    result = await _run(env, previous, FIRST_ALERT)

    assert result is None
    assert env.deps.generator.calls == []
    assert statuses(service_db) == {}
    assert env.created() == []


async def test_rise_judged_by_argument_alert_not_latest(make, service_db):
    """상승은 인자 판정(A, caution)으로 판단하고, 카드는 더 늦은 최신 판정(B, none)에 연결된다."""
    add_alert(service_db, FIRST_ALERT, level="caution", evaluated_at=FIRST_AT)
    add_alert(service_db, SECOND_ALERT, level="none", evaluated_at=SECOND_AT)
    env = make()

    card = await _run(env, AlertLevel.NONE, FIRST_ALERT)

    assert card is not None
    assert card.alert_id == SECOND_ALERT
    assert len(env.deps.generator.calls) == 1


async def test_generation_failure_returns_failed_card(make, service_db):
    add_alert(service_db, FIRST_ALERT, level="warning", evaluated_at=FIRST_AT)
    env = make(generator=ScriptedGenerator(error=GenerationError("모델 오류")))

    card = await _run(env, AlertLevel.CAUTION, FIRST_ALERT)

    assert card is not None
    assert card.status == RecommendationStatus.FAILED
    assert card.items == ()
    assert statuses(service_db) == {card.recommendation_id: "failed"}


async def test_rise_skipped_when_current_card_is_for_latest_alert(make, service_db):
    # 시드의 최신 판정(LATEST_ALERT, none)에 연결된 카드가 이미 있으면 `auto`는 건너뛴다.
    add_card(service_db, "R_old", alert_id=LATEST_ALERT)
    with connect(service_db) as conn:
        conn.execute("UPDATE alerts SET level = 'caution' WHERE alert_id = ?", (LATEST_ALERT,))
    env = make()

    result = await _run(env, AlertLevel.NONE, LATEST_ALERT)

    assert result is None
    assert env.deps.generator.calls == []
    assert statuses(service_db) == {"R_old": "active"}


async def test_unknown_alert_raises_value_error(make, service_db):
    env = make()

    with pytest.raises(ValueError, match="alert_missing"):
        await on_alert_evaluated(PATIENT, AlertLevel.NONE, "alert_missing", deps=env.deps)

    assert env.deps.generator.calls == []


async def test_alert_of_other_patient_raises_value_error(make, service_db):
    with connect(service_db) as conn:
        insert_alert(
            conn,
            alert_id="alert_NS01_hook",
            patient_id="NS01",
            evaluated_at=FIRST_AT,
            level="warning",
        )
    env = make()

    with pytest.raises(ValueError, match="alert_NS01_hook"):
        await on_alert_evaluated(PATIENT, AlertLevel.NONE, "alert_NS01_hook", deps=env.deps)

    assert env.deps.generator.calls == []
    assert statuses(service_db) == {}


# ── 연속 판정 정책 ──


async def test_rise_during_generation_creates_second_card_for_new_alert(make, service_db):
    """(가) 생성기를 멈춘 동안 새 상승 판정 → 카드 두 장, 둘째가 새 판정에 연결된다."""
    add_alert(service_db, FIRST_ALERT, level="caution", evaluated_at=FIRST_AT)
    gate = asyncio.Event()
    locks = RecordingLocks()
    env = make(generator=ScriptedGenerator(gate=gate, gate_calls=frozenset({1})), locks=locks)
    first = _hook(env, None, FIRST_ALERT)
    await wait_set(env.deps.generator.entered)

    add_alert(service_db, SECOND_ALERT, level="warning", evaluated_at=SECOND_AT)
    second = _hook(env, AlertLevel.CAUTION, SECOND_ALERT)
    await wait_set(locks.second_request)
    gate.set()
    first_card, second_card = await asyncio.wait_for(asyncio.gather(first, second), TIMEOUT)

    assert first_card is not None and second_card is not None
    assert first_card.alert_id == FIRST_ALERT
    assert second_card.alert_id == SECOND_ALERT
    assert statuses(service_db) == {
        first_card.recommendation_id: "superseded",
        second_card.recommendation_id: "active",
    }


async def test_two_rises_called_together_create_one_card_for_latest(make, service_db):
    """(나) 상승 판정 두 개 저장 뒤 훅 두 번을 동시에 → 카드 한 장, 최신 판정에 연결된다."""
    add_alert(service_db, FIRST_ALERT, level="caution", evaluated_at=FIRST_AT)
    add_alert(service_db, SECOND_ALERT, level="warning", evaluated_at=SECOND_AT)
    env = make()

    results = await asyncio.wait_for(
        asyncio.gather(_hook(env, None, FIRST_ALERT), _hook(env, AlertLevel.CAUTION, SECOND_ALERT)),
        TIMEOUT,
    )

    cards = [r for r in results if r is not None]
    assert len(cards) == 1
    assert cards[0].alert_id == SECOND_ALERT
    assert len(env.deps.generator.calls) == 1
    assert statuses(service_db) == {cards[0].recommendation_id: "active"}


async def test_same_level_during_generation_keeps_card_on_previous_alert(make, service_db):
    """(다) 멈춘 동안 같은 수준 판정 → 카드 한 장, 이전 판정에 연결된 채 남는다."""
    add_alert(service_db, FIRST_ALERT, level="caution", evaluated_at=FIRST_AT)
    gate = asyncio.Event()
    env = make(generator=ScriptedGenerator(gate=gate))
    first = _hook(env, None, FIRST_ALERT)
    await wait_set(env.deps.generator.entered)

    add_alert(service_db, SECOND_ALERT, level="caution", evaluated_at=SECOND_AT)
    second_result = await _run(env, AlertLevel.CAUTION, SECOND_ALERT)
    gate.set()
    first_card = await asyncio.wait_for(first, TIMEOUT)

    assert second_result is None
    assert first_card is not None
    assert first_card.alert_id == FIRST_ALERT
    assert len(env.deps.generator.calls) == 1
    assert statuses(service_db) == {first_card.recommendation_id: "active"}


# ── 취소 보호 ──


async def test_caller_cancel_during_save_then_second_hook(make, service_db, monkeypatch):
    add_alert(service_db, FIRST_ALERT, level="caution", evaluated_at=FIRST_AT)
    write_gate = WriteGate(monkeypatch)
    locks = RecordingLocks()

    def save_second_alert() -> None:
        # 첫 생성의 맥락 읽기 뒤·저장 전에 둘째 판정을 커밋한다. 저장이 멈춘 동안에는 쓰기
        # 잠금이 잡혀 있어 다른 연결로 쓸 수 없으므로 이 시점에 넣는다.
        if len(env.deps.generator.calls) == 1:
            add_alert(service_db, SECOND_ALERT, level="warning", evaluated_at=SECOND_AT)

    env = make(generator=ScriptedGenerator(on_enter=save_second_alert), locks=locks)
    first = _hook(env, None, FIRST_ALERT)
    await write_gate.wait_entered()

    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    second = _hook(env, AlertLevel.CAUTION, SECOND_ALERT)
    await wait_set(locks.second_request)  # 둘째가 첫째의 저장이 끝나기 전에 잠금을 요청했다
    write_gate.release.set()
    second_card = await asyncio.wait_for(second, TIMEOUT)
    await env.drain()

    assert second_card is not None
    assert second_card.alert_id == SECOND_ALERT
    assert len(env.deps.generator.calls) == 2
    created = env.created()
    assert len(created) == 2
    first_id = created[0]["recommendation_id"]
    assert created[1]["recommendation_id"] == second_card.recommendation_id
    assert statuses(service_db) == {
        first_id: "superseded",
        second_card.recommendation_id: "active",
    }
