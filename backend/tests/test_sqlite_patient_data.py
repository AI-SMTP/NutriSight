"""`SqlitePatientData`의 계약 테스트와 SQLite 전용 동작 테스트 (스펙 3.8).

계약 배치는 `tests/contracts/sqlite_patient_batch.py`가 `FakePatientData` 공개 상수와 같은 값으로
넣는다. 런타임은 `GenerationEnvs`로 만든다(가짜 시계 고정, 발행 순간 기록).
"""

from __future__ import annotations

import asyncio
import sqlite3
import threading
from collections.abc import AsyncIterator
from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import ANY, Mock

import pytest

from app.events.bus import Event
from app.nutrition.fake import FakeNutritionEngine
from app.nutrition.types import AlertLevel
from app.services import fake_patient_data as fake
from app.services import recommendations as rec_service
from app.services.fake_patient_data import default_cards, late_failed_cards
from app.services.ports import ModifiedBy, RecommendationItem
from app.services.runtime import AppRuntime
from app.services.sqlite_patient_data import SqlitePatientData
from app.services.unit_of_work import WriteResult
from app.storage import recommendations as rec_store
from app.storage.db import connect, create_schema
from tests.contracts.patient_data import (
    LateFailedFixture,
    PatientDataPortContract,
    PortFixture,
    build_duplicate_items,
    build_items,
)
from tests.contracts.sqlite_patient_batch import CHAT_THREAD_ID, load_patient_batch
from tests.services.cards import read_card
from tests.services.generation import APP_NOW, TIMEOUT, GenerationEnv, GenerationEnvs

# 기대 날짜는 Fake 계약 테스트와 같은 값을 따로 고정한다(구현 상수와 비교하지 않기 위해).
EXPECTED_SUMMARY_DATES = (
    date(2026, 11, 20),
    date(2026, 11, 21),
    date(2026, 11, 23),
    date(2026, 11, 24),
    date(2026, 11, 25),
    date(2026, 11, 26),
)
EXPECTED_ALT_DAYS_DATES = (date(2026, 11, 24), date(2026, 11, 25), date(2026, 11, 26))
EXPECTED_ALT_ON_DATES = (
    date(2026, 11, 21),
    date(2026, 11, 23),
    date(2026, 11, 24),
    date(2026, 11, 25),
    date(2026, 11, 26),
    date(2026, 11, 27),
)
UPDATED_EVENT = "recommendation.updated"


async def _open_port(db: Path, envs: GenerationEnvs) -> tuple[SqlitePatientData, GenerationEnv]:
    env = envs()
    return SqlitePatientData(db, env.runtime, FakeNutritionEngine()), env


@pytest.fixture
async def batch_envs(db_path: Path) -> AsyncIterator[GenerationEnvs]:
    """기본 카드 7장 배치를 넣은 `db_path`의 런타임 공장. 블록을 나가면 런타임을 정리한다."""
    load_patient_batch(db_path, default_cards())
    async with GenerationEnvs(db_path) as envs:
        yield envs


@pytest.fixture
async def port_env(
    db_path: Path, batch_envs: GenerationEnvs
) -> tuple[SqlitePatientData, GenerationEnv]:
    return await _open_port(db_path, batch_envs)


@pytest.fixture
def late_db(tmp_path: Path) -> Path:
    path = tmp_path / "late.db"
    with connect(path) as conn:
        create_schema(conn)
    load_patient_batch(path, late_failed_cards())
    return path


class TestSqlitePatientData(PatientDataPortContract):
    @pytest.fixture
    def port(self, port_env: tuple[SqlitePatientData, GenerationEnv]) -> SqlitePatientData:
        return port_env[0]

    @pytest.fixture
    def port_fixture(self) -> PortFixture:
        return PortFixture(
            patient_with_active=fake.PATIENT_WITH_ACTIVE,
            expected_active_id=fake.ACTIVE_ID,
            patient_with_failed_only=fake.PATIENT_WITH_FAILED_ONLY,
            expected_failed_id=fake.FAILED_ONLY_ID,
            patient_with_tie=fake.PATIENT_WITH_TIE,
            expected_tie_id=fake.TIE_FAILED_ID,
            patient_without_card=fake.PATIENT_WITHOUT_CARD,
            confirmed_id=fake.CONFIRMED_ID,
            superseded_id=fake.SUPERSEDED_ID,
            failed_id=fake.FAILED_ID,
            unknown_patient_id="NS99",
            unknown_recommendation_id="rec-unknown",
            summary_on=fake.SUMMARY_ON,
            summary_days=fake.SUMMARY_DAYS,
            expected_summary_dates=EXPECTED_SUMMARY_DATES,
            alt_summary_days=fake.ALT_SUMMARY_DAYS,
            expected_alt_days_dates=EXPECTED_ALT_DAYS_DATES,
            alt_summary_on=fake.ALT_SUMMARY_ON,
            expected_alt_on_dates=EXPECTED_ALT_ON_DATES,
            expected_alt_on_alert_level=AlertLevel.WARNING,
            chat_thread_id=CHAT_THREAD_ID,
        )

    @pytest.fixture
    async def late_failed_port(self, late_db: Path) -> AsyncIterator[SqlitePatientData]:
        async with GenerationEnvs(late_db) as envs:
            port, _ = await _open_port(late_db, envs)
            yield port

    @pytest.fixture
    def late_failed(self) -> LateFailedFixture:
        return LateFailedFixture(patient_id=fake.PATIENT_WITH_ACTIVE, expected_id=fake.FAILED_ID)


# ---- 수정: save_items 경유와 커밋 뒤 발행 ----


async def test_update_goes_through_save_items_and_publishes_after_commit(
    db_path: Path,
    port_env: tuple[SqlitePatientData, GenerationEnv],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    port, env = port_env
    spy = Mock(wraps=rec_service.save_items)
    monkeypatch.setattr(rec_service, "save_items", spy)
    # 발행 순간에 다른 연결로 읽어, 커밋된 값을 보는지(커밋 뒤 발행인지) 기록한다.
    seen_at_publish: list[tuple[str, ModifiedBy]] = []
    recording_publish = env.runtime.bus.publish

    def checking_publish(event: Event) -> None:
        stored = read_card(db_path, fake.ACTIVE_ID)
        seen_at_publish.append((stored.items[0].item_id, stored.last_modified_by))
        recording_publish(event)

    monkeypatch.setattr(env.runtime.bus, "publish", checking_publish)
    items = build_items("doc")

    result = await port.update_recommendation(fake.ACTIVE_ID, items, ModifiedBy.DOCTOR, None)

    spy.assert_called_once_with(ANY, fake.ACTIVE_ID, items, ModifiedBy.DOCTOR, None, None, APP_NOW)
    assert result.items == items
    assert result.updated_at == APP_NOW
    assert [event.name for event in env.events] == [UPDATED_EVENT]
    assert env.events[0].data["recommendation_id"] == fake.ACTIVE_ID
    assert env.events[0].data["patient_id"] == fake.PATIENT_WITH_ACTIVE
    assert env.events[0].data["modified_by"] == "doctor"
    assert seen_at_publish == [("doc1", ModifiedBy.DOCTOR)]


async def test_update_runs_save_items_on_writer_thread(
    port_env: tuple[SqlitePatientData, GenerationEnv], monkeypatch: pytest.MonkeyPatch
) -> None:
    port, _ = port_env
    real = rec_service.save_items
    threads: list[str] = []

    def recording(*args: Any) -> Any:
        threads.append(threading.current_thread().name)
        return real(*args)

    monkeypatch.setattr(rec_service, "save_items", recording)

    await port.update_recommendation(fake.ACTIVE_ID, build_items("doc"), ModifiedBy.DOCTOR, None)

    assert len(threads) == 1
    assert threads[0].startswith("db-writer")


# ---- 수정 실패: 이벤트 없음, 카드 그대로 ----


class _StorageBoom(sqlite3.OperationalError):
    """저장 SQL이 던지는 저장소 예외 대역."""


async def _assert_rejected_without_effect(
    db_path: Path,
    port_env: tuple[SqlitePatientData, GenerationEnv],
    items: tuple[RecommendationItem, ...],
    expected: type[Exception],
) -> None:
    """수정이 `expected`로 실패하고, 이벤트가 없고, 카드가 그대로인지 확인한다."""
    port, env = port_env
    before = read_card(db_path, fake.ACTIVE_ID)

    with pytest.raises(expected):
        await port.update_recommendation(fake.ACTIVE_ID, items, ModifiedBy.DOCTOR, None)

    assert env.events == []
    assert read_card(db_path, fake.ACTIVE_ID) == before


async def test_storage_error_publishes_nothing_and_keeps_card(
    db_path: Path,
    port_env: tuple[SqlitePatientData, GenerationEnv],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(*args: Any, **kwargs: Any) -> int:
        raise _StorageBoom("저장 실패")

    monkeypatch.setattr(rec_store, "update_card_items", boom)

    await _assert_rejected_without_effect(db_path, port_env, build_items("doc"), _StorageBoom)


async def test_duplicate_item_id_publishes_nothing_and_keeps_card(
    db_path: Path, port_env: tuple[SqlitePatientData, GenerationEnv]
) -> None:
    await _assert_rejected_without_effect(db_path, port_env, build_duplicate_items(), ValueError)


# ---- 호출자 취소: 쓰기는 커밋·발행까지 끝난다 ----


class _Gate:
    """쓰기 실행기 스레드를 `release`가 켜질 때까지 멈추는 게이트."""

    def __init__(self) -> None:
        self.entered = threading.Event()
        self.release = threading.Event()

    def hold(self) -> None:
        """호출한 스레드에서 들어왔음을 알리고 풀릴 때까지 기다린다."""
        self.entered.set()
        if not self.release.wait(TIMEOUT):
            raise TimeoutError("게이트가 풀리지 않았다")

    async def wait_entered(self) -> None:
        assert await asyncio.to_thread(self.entered.wait, TIMEOUT)


async def test_cancelled_caller_still_commits_and_publishes(
    db_path: Path,
    port_env: tuple[SqlitePatientData, GenerationEnv],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    port, env = port_env
    gate = _Gate()
    real = rec_store.update_card_items

    def gated(*args: Any, **kwargs: Any) -> int:
        gate.hold()
        return real(*args, **kwargs)

    monkeypatch.setattr(rec_store, "update_card_items", gated)
    items = build_items("doc")
    caller = asyncio.create_task(
        port.update_recommendation(fake.ACTIVE_ID, items, ModifiedBy.DOCTOR, None)
    )
    await gate.wait_entered()

    caller.cancel()
    with pytest.raises(asyncio.CancelledError):
        await caller
    assert env.events == []  # 아직 커밋 전이다
    assert read_card(db_path, fake.ACTIVE_ID).items != items

    gate.release.set()
    await env.drain()

    stored = read_card(db_path, fake.ACTIVE_ID)
    assert stored.items == items
    assert stored.last_modified_by is ModifiedBy.DOCTOR
    assert [event.name for event in env.events] == [UPDATED_EVENT]


async def test_cancelled_caller_still_runs_write_queued_behind_another(
    db_path: Path, port_env: tuple[SqlitePatientData, GenerationEnv]
) -> None:
    """앞선 쓰기에 막혀 아직 시작하지 않은 수정도 호출자가 취소된 뒤 실행된다.

    쓰기 실행기만으로는 대기 중인 작업이 호출자 취소와 함께 취소되므로, 앱 소유 태스크로
    기다리는지(`run_shielded`)를 이 경우가 가른다.
    """
    port, env = port_env
    writer = env.runtime.writer
    gate = _Gate()

    def blocker(conn: sqlite3.Connection) -> WriteResult[None]:
        gate.hold()
        return WriteResult(None)

    blocking = asyncio.create_task(writer.run_write(blocker))
    await gate.wait_entered()
    items = build_items("doc")
    caller = asyncio.create_task(
        port.update_recommendation(fake.ACTIVE_ID, items, ModifiedBy.DOCTOR, None)
    )
    await asyncio.sleep(0)  # caller가 한 번 돌아 앱 소유 쓰기 태스크를 만들게 한다

    caller.cancel()
    with pytest.raises(asyncio.CancelledError):
        await caller
    gate.release.set()
    await asyncio.wait_for(blocking, TIMEOUT)
    await env.drain()
    # 실행기는 작업을 순서대로 돌리므로, 뒤에 넣은 빈 쓰기가 끝나면 앞선 작업도 끝났다.
    await asyncio.wait_for(writer.run_write(lambda conn: WriteResult(None)), TIMEOUT)

    assert read_card(db_path, fake.ACTIVE_ID).items == items
    assert [event.name for event in env.events] == [UPDATED_EVENT]


# ---- 생성자 ----


def test_constructor_does_not_create_db_file(tmp_path: Path) -> None:
    path = tmp_path / "missing.db"
    runtime = AppRuntime.create(path)

    SqlitePatientData(path, runtime, FakeNutritionEngine())

    assert not path.exists()


def test_constructor_rejects_path_different_from_writer(tmp_path: Path) -> None:
    runtime = AppRuntime.create(tmp_path / "app.db")

    with pytest.raises(ValueError):
        SqlitePatientData(tmp_path / "other.db", runtime, FakeNutritionEngine())


def test_constructor_accepts_same_path_spelled_differently(tmp_path: Path) -> None:
    (tmp_path / "sub").mkdir()
    runtime = AppRuntime.create(tmp_path / "app.db")

    SqlitePatientData(tmp_path / "sub" / ".." / "app.db", runtime, FakeNutritionEngine())
