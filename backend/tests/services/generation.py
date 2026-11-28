"""추천 생성 서비스 테스트가 함께 쓰는 런타임·생성기·DB 준비 도우미.

`GenerationEnvs`는 테스트마다 `AppRuntime.create(db, now_fn=가짜)`로 런타임을 만들고, 시계를
고정하고, 버스를 실행 중인 루프에 묶는다. 발행된 이벤트는 버스 `publish`를 감싸 발행 순간
(쓰기 실행기 스레드)에 기록하므로, "이벤트가 없다"를 기다림 없이 확인할 수 있다.
기다림은 모두 `TIMEOUT` 상한을 둔다. 결과가 실제 시간 경과(sleep)에 기대지 않는다.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from types import TracebackType
from typing import Any

import pytest

from app.events.bus import Event
from app.nutrition.fake import FakeNutritionEngine
from app.recommender.fake_generator import FakeRecommendationGenerator
from app.services.generation import CREATED_EVENT, PatientLocks, RecommendationDeps
from app.services.ports import IntakeSummary
from app.services.runtime import AppRuntime
from app.storage import recommendations as rec_store
from app.storage.codec import items_to_json
from app.storage.db import connect
from tests.storage.demo import DEMO
from tests.storage.items import AGENT_ITEM, DOCTOR_ITEM
from tests.storage.rows import insert_alert, insert_recommendation

TIMEOUT = 5.0
PATIENT = "NS07"
# 시드에서 NS07의 시연일(2026-12-05) 이하 최신 판정(수준 none)과 그 전날 판정.
LATEST_ALERT = "alert_NS07_2026-12-04"
EARLIER_ALERT = "alert_NS07_2026-12-03"
NEW_ALERT = "alert_NS07_2026-12-05"
GEN_STORED_AT = "2026-12-04T09:00:00.000000"
APP_NOW = datetime(2026, 12, 5, 9, 0, 0)


class FakeNow:
    """바꿀 수 있는 가짜 실제 시각."""

    def __init__(self, value: datetime) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value


_DEFAULT = object()


class ScriptedGenerator:
    """호출을 기록하고, `gate`가 있으면 풀릴 때까지 기다린 뒤 정해진 결과를 내는 생성기.

    `result`를 주지 않으면 `FakeRecommendationGenerator`의 카드, `error`를 주면 그 예외.
    `gate_calls`는 `gate`를 기다릴 호출 번호(1부터)다. `None`이면 모든 호출이 기다린다.
    """

    def __init__(
        self,
        result: object = _DEFAULT,
        *,
        error: BaseException | None = None,
        gate: asyncio.Event | None = None,
        gate_calls: frozenset[int] | None = None,
        on_enter: Callable[[], None] | None = None,
    ) -> None:
        self._result = result
        self._error = error
        self._gate = gate
        self._gate_calls = gate_calls
        self._on_enter = on_enter
        self.calls: list[tuple[str, IntakeSummary]] = []
        self.entered = asyncio.Event()
        self.active = 0
        self.max_active = 0

    async def generate(self, patient_id: str, summary: IntakeSummary) -> Any:
        self.calls.append((patient_id, summary))
        call_no = len(self.calls)
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        if self._on_enter is not None:
            self._on_enter()
        self.entered.set()
        try:
            if self._gate is not None and (self._gate_calls is None or call_no in self._gate_calls):
                await self._gate.wait()
            # 한 번 양보해 다른 생성이 겹칠 기회를 준다(겹치면 max_active가 2가 된다).
            await asyncio.sleep(0)
            if self._error is not None:
                raise self._error
            if self._result is _DEFAULT:
                return await FakeRecommendationGenerator().generate(patient_id, summary)
            return self._result
        finally:
            self.active -= 1


class RecordingLocks(PatientLocks):
    """`get` 호출 수를 세고, 두 번째 호출 때 `second_request`를 켠다."""

    def __init__(self) -> None:
        super().__init__()
        self.requests = 0
        self.second_request = asyncio.Event()

    def get(self, patient_id: str) -> asyncio.Lock:
        self.requests += 1
        if self.requests >= 2:
            self.second_request.set()
        return super().get(patient_id)


class WriteGate:
    """`supersede_open_cards` 첫 호출을 쓰기 실행기 스레드에서 멈춘다."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._real = rec_store.supersede_open_cards
        self.entered = threading.Event()
        self.release = threading.Event()
        self._calls = 0
        monkeypatch.setattr(rec_store, "supersede_open_cards", self)

    def __call__(self, conn: Any, patient_id: str) -> int:
        self._calls += 1
        if self._calls == 1:
            self.entered.set()
            if not self.release.wait(TIMEOUT):
                raise TimeoutError("WriteGate가 풀리지 않았다")
        return self._real(conn, patient_id)

    async def wait_entered(self) -> None:
        assert await asyncio.to_thread(self.entered.wait, TIMEOUT)


@dataclass
class GenerationEnv:
    """테스트 하나의 런타임·의존성·발행 기록."""

    now: FakeNow
    runtime: AppRuntime
    deps: RecommendationDeps
    events: list[Event] = field(default_factory=list)

    def created(self) -> list[dict[str, object]]:
        """발행된 `recommendation.created` 이벤트 데이터(발행 순서)."""
        return [dict(e.data) for e in self.events if e.name == CREATED_EVENT]

    async def drain(self) -> None:
        """남은 앱 소유 태스크가 끝나기를 기다린다."""
        pending = tuple(self.runtime.tasks.tasks)
        await asyncio.wait_for(asyncio.gather(*pending, return_exceptions=True), TIMEOUT)

    async def close(self) -> None:
        await self.runtime.tasks.cancel_all()
        await asyncio.to_thread(self.runtime.writer.shutdown)


class GenerationEnvs:
    """`async with`로 쓰는 `GenerationEnv` 공장. 블록을 나가면 모든 런타임을 정리한다."""

    def __init__(self, db: Path) -> None:
        self._db = db
        self._envs: list[GenerationEnv] = []

    async def __aenter__(self) -> GenerationEnvs:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        for env in self._envs:
            await env.close()

    def __call__(
        self,
        *,
        generator: object | None = None,
        timeout_s: float = TIMEOUT,
        locks: PatientLocks | None = None,
        now: datetime = APP_NOW,
        today: date = DEMO,
    ) -> GenerationEnv:
        """`today`(실제 날짜)와 시연일 `DEMO`의 차이로 시계를 고정한다. `now`는 실제 시각이다."""
        fake_now = FakeNow(now)
        runtime = AppRuntime.create(self._db, now_fn=fake_now)
        runtime.clock.anchor(DEMO, today)
        runtime.bus.bind_loop(asyncio.get_running_loop())
        deps = RecommendationDeps(
            generator=generator if generator is not None else ScriptedGenerator(),  # type: ignore[arg-type]
            runtime=runtime,
            db_path=self._db,
            engine=FakeNutritionEngine(),
            locks=locks if locks is not None else PatientLocks(),
            timeout_s=timeout_s,
        )
        env = GenerationEnv(now=fake_now, runtime=runtime, deps=deps)
        real_publish = runtime.bus.publish

        def recording_publish(event: Event) -> None:
            env.events.append(event)
            real_publish(event)

        runtime.bus.publish = recording_publish  # type: ignore[method-assign]
        self._envs.append(env)
        return env


async def wait_set(event: asyncio.Event) -> None:
    await asyncio.wait_for(event.wait(), TIMEOUT)


def add_card(
    db: Path,
    recommendation_id: str,
    *,
    status: str = "active",
    alert_id: str | None = LATEST_ALERT,
    created_at: str = GEN_STORED_AT,
    patient_id: str = PATIENT,
) -> None:
    """항목 2개(`rx1` 에이전트, `rx2` 의사)인 카드를 직접 넣는다."""
    with connect(db) as conn:
        insert_recommendation(
            conn,
            recommendation_id=recommendation_id,
            patient_id=patient_id,
            alert_id=alert_id,
            items=items_to_json((AGENT_ITEM, DOCTOR_ITEM)),
            created_at=created_at,
            updated_at=created_at,
            status=status,
        )


def add_alert(
    db: Path,
    alert_id: str = NEW_ALERT,
    *,
    level: str = "warning",
    evaluated_at: str = "2026-12-05T08:00:00",
) -> None:
    """NS07 판정을 직접 넣는다."""
    with connect(db) as conn:
        insert_alert(
            conn,
            alert_id=alert_id,
            patient_id=PATIENT,
            evaluated_at=evaluated_at,
            level=level,
            nutrients="[]" if level == "none" else '["protein"]',
        )


def statuses(db: Path, patient_id: str = PATIENT) -> dict[str, str]:
    """그 환자 카드의 ID → 상태."""
    with connect(db) as conn:
        rows = conn.execute(
            "SELECT recommendation_id, status FROM recommendations WHERE patient_id = ?",
            (patient_id,),
        ).fetchall()
    return {row["recommendation_id"]: row["status"] for row in rows}
