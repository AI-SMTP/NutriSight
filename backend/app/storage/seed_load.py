"""검증된 시드를 시연일 기준으로 바꿔 한 트랜잭션에 적재한다 (스펙 3.7).

- 날짜는 `demo_date + offset일`, ID는 필드(`day_offset`·`meal`·`diet_type`·`patient_id`)로
  새로 만든다. 시드 ID 문자열은 해석하지 않는다.
- 원본 테이블 → 파생 테이블(`daily_intakes`·`alerts`) → `seed_meta` 순으로 넣고 마지막에 한 번
  커밋한다. 어느 단계든 예외가 나면 `connect()`가 롤백해 DDL과 행이 함께 사라진다.
- 적재 중 `IntegrityError`는 테이블과 행 ID를 담은 `SeedError`로 바꾼다. 트리거 오류 메시지에는
  테이블·ID가 없으므로 테이블별 적재 루프에서 붙인다.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from pydantic import BaseModel

from app.config import Settings
from app.nutrition.types import (
    MealRecord,
    MealType,
    NutritionEngine,
    RecordStatus,
)
from app.storage.codec import (
    evidence_to_json,
    format_basis_period,
    nutrients_to_json,
    quality_issues_to_json,
    strings_to_json,
)
from app.storage.db import SCHEMA_VERSION, connect, create_schema
from app.storage.errors import SeedError
from app.storage.seed_derived import PatientDay, evaluate_patients
from app.storage.seed_models import DemoSeed, SeedMealOrder, SeedMealPlan, SeedPatient

Clock = Callable[[], datetime]
# (메시지에 쓸 행 ID, 열 이름 → 값)
Row = tuple[str, Mapping[str, object]]

LOCAL_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S"
# 시드 경고는 판정일 마감 시각으로 기록한다(스펙 4절 경고 판정 시각).
SEED_ALERT_TIME = "23:59:59"
# `order_from_meal`이 없는 발주의 시작 끼니.
DEFAULT_ORDER_FROM_MEAL = MealType.BREAKFAST
# 교체 뒤 정리를 마치기 전까지만 있는 `seed_meta` 키와 값 (스펙 3.8).
CLEANUP_PENDING_KEY = "cleanup_pending"
CLEANUP_PENDING_VALUE = "1"
_MEAL_INDEX = {meal: index for index, meal in enumerate(MealType)}


@dataclass(frozen=True)
class SeedCounts:
    """적재한 테이블별 행 수."""

    patients: int
    patient_weights: int
    patient_targets: int
    patient_assessments: int
    meal_plans: int
    meal_plan_slots: int
    meal_orders: int
    slot_intakes: int
    daily_intakes: int
    alerts: int


@dataclass(frozen=True)
class _PlanKey:
    """배식 계획 하나를 시연일 기준으로 바꾼 값."""

    meal_plan_id: str
    on: date
    meal: MealType


def build_engine(settings: Settings) -> NutritionEngine:
    """앱과 같은 규칙(`NUTRITION_ENGINES[settings.nutrition_engine]`)으로 엔진을 만든다.

    등록되지 않은 이름이면 `ConfigError`를 던진다. `wiring`은 네 계약의 구현을 모두 import하므로
    `import app.storage.seed`만으로 읽히지 않게 함수 안에서 import한다.
    """
    from app.wiring import build_nutrition_engine

    return build_nutrition_engine(settings)


def build_database(
    db_path: Path,
    seed: DemoSeed,
    demo_date: date,
    engine: NutritionEngine,
    *,
    cleanup_pending: bool = False,
    clock: Clock = datetime.now,
) -> SeedCounts:
    """`db_path`에 스키마를 만들고 시드·파생 테이블·`seed_meta`를 한 트랜잭션으로 넣는다.

    전제: `db_path`는 없거나 스키마가 없는 빈 DB다(기존 테이블이 있으면 `CREATE TABLE`이 실패).

    `cleanup_pending=True`이면 `seed_meta`에 정리 대기 표시를 함께 넣는다. `clock`은
    `seeded_at`(로컬 시각)을 정한다. 적재 중 제약 위반은 `SeedError`이고, 그 밖의 예외(엔진
    예외 포함)는 그대로 전달한다. 어느 경우든 DB에는 테이블이 남지 않는다.
    """
    plans = {p.meal_plan_id: _plan_key(p, demo_date) for p in seed.meal_plans}
    with connect(db_path, journal_mode="DELETE") as conn:
        create_schema(conn, begin=True)
        source = _insert_sources(conn, seed, demo_date, plans)
        daily_count, alert_count = _insert_derived(conn, seed, demo_date, engine, plans)
        _insert_rows(conn, "seed_meta", _meta_rows(demo_date, clock(), cleanup_pending))
        _commit(conn)
    return SeedCounts(**source, daily_intakes=daily_count, alerts=alert_count)


# 변환 ----------------------------------------------------------------------


def _shift(demo_date: date, offset: int) -> date:
    return demo_date + timedelta(days=offset)


def _iso(demo_date: date, offset: int) -> str:
    """`demo_date + offset일`의 `YYYY-MM-DD`."""
    return _shift(demo_date, offset).isoformat()


def _plan_key(plan: SeedMealPlan, demo_date: date) -> _PlanKey:
    on = _shift(demo_date, plan.day_offset)
    return _PlanKey(f"{on.isoformat()}_{plan.meal}_{plan.diet_type}", on, plan.meal)


def _order_id(order: SeedMealOrder, plan: _PlanKey) -> str:
    return f"{order.patient_id}_{plan.on.isoformat()}_{plan.meal}"


def _record_status(order: SeedMealOrder) -> RecordStatus:
    """금식·취소 발주의 `null`은 `MealRecord` 계약과 같은 `not_recorded`로 바꾼다."""
    return order.record_status if order.record_status is not None else RecordStatus.NOT_RECORDED


def _order_from(order: SeedMealOrder, demo_date: date) -> str | None:
    if order.order_from_offset is None:
        return None
    meal = order.order_from_meal or DEFAULT_ORDER_FROM_MEAL
    return f"{_iso(demo_date, order.order_from_offset)} {meal}"


def _birth_year(patient: SeedPatient, demo_date: date) -> int:
    return demo_date.year - patient.age_at_d0


def _columns(model: BaseModel, *, exclude: set[str]) -> dict[str, object]:
    """열 이름과 같은 시드 필드를 그대로 옮긴다. 열거값은 문자열이 된다."""
    return model.model_dump(mode="json", exclude=exclude)


# 적재 ----------------------------------------------------------------------


def _insert_rows(conn: sqlite3.Connection, table: str, rows: Iterable[Row]) -> int:
    """행을 하나씩 넣고 개수를 돌려준다. 제약 위반이면 테이블·행 ID를 담은 `SeedError`."""
    count = 0
    for label, row in rows:
        columns = ", ".join(row)
        placeholders = ", ".join("?" for _ in row)
        try:
            conn.execute(
                f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", tuple(row.values())
            )
        except sqlite3.IntegrityError as err:
            raise SeedError(f"{table}: {label} 적재 중 제약 위반: {err}") from err
        count += 1
    return count


def _commit(conn: sqlite3.Connection) -> None:
    """커밋한다. 지연 외래 키(사진 참조) 위반은 커밋에서 나므로 `SeedError`로 바꾼다."""
    try:
        conn.commit()
    except sqlite3.IntegrityError as err:
        raise SeedError(
            "시드 적재를 확정하는 중 지연 외래 키 위반: 사진 참조 "
            "(meal_plans.baseline_photo_id, meal_orders.post_photo_id) "
            f"중 없는 사진을 가리키는 값이 있다: {err}"
        ) from err


def _insert_sources(
    conn: sqlite3.Connection, seed: DemoSeed, demo_date: date, plans: Mapping[str, _PlanKey]
) -> dict[str, int]:
    """원본 테이블을 트리거가 요구하는 순서(계획 → 칸 → 발주 → 칸별 섭취)로 넣는다."""
    return {
        "patients": _insert_rows(conn, "patients", _patient_rows(seed, demo_date)),
        "patient_weights": _insert_rows(conn, "patient_weights", _weight_rows(seed, demo_date)),
        "patient_targets": _insert_rows(conn, "patient_targets", _target_rows(seed, demo_date)),
        "patient_assessments": _insert_rows(
            conn, "patient_assessments", _assessment_rows(seed, demo_date)
        ),
        "meal_plans": _insert_rows(conn, "meal_plans", _plan_rows(seed, plans)),
        "meal_plan_slots": _insert_rows(conn, "meal_plan_slots", _slot_rows(seed, plans)),
        "meal_orders": _insert_rows(conn, "meal_orders", _order_rows(seed, demo_date, plans)),
        "slot_intakes": _insert_rows(conn, "slot_intakes", _slot_intake_rows(seed, plans)),
    }


def _patient_rows(seed: DemoSeed, demo_date: date) -> Iterable[Row]:
    for p in seed.patients:
        row = _columns(p, exclude={"age_at_d0", "observation_start_offset", "conditions"})
        yield (
            p.patient_id,
            {
                **row,
                "birth_year": _birth_year(p, demo_date),
                "conditions": strings_to_json(p.conditions),
                "observation_start": _iso(demo_date, p.observation_start_offset),
            },
        )


def _weight_rows(seed: DemoSeed, demo_date: date) -> Iterable[Row]:
    """체중 기록 행."""
    for w in seed.patient_weights:
        on = _iso(demo_date, w.day_offset)
        row = _columns(w, exclude={"day_offset"})
        yield f"{w.patient_id} {on}", {**row, "measured_on": on}


def _target_rows(seed: DemoSeed, demo_date: date) -> Iterable[Row]:
    for t in seed.patient_targets:
        on = _iso(demo_date, t.effective_from_offset)
        row = _columns(t, exclude={"effective_from_offset"})
        yield f"{t.patient_id} {on}", {**row, "effective_from": on}


def _assessment_rows(seed: DemoSeed, demo_date: date) -> Iterable[Row]:
    for a in seed.patient_assessments:
        on = _iso(demo_date, a.day_offset)
        row = _columns(a, exclude={"day_offset"})
        yield f"{a.patient_id} {on} {a.kind}", {**row, "assessed_on": on}


def _plan_rows(seed: DemoSeed, plans: Mapping[str, _PlanKey]) -> Iterable[Row]:
    for plan in seed.meal_plans:
        key = plans[plan.meal_plan_id]
        row = _columns(plan, exclude={"meal_plan_id", "day_offset", "meal", "slots"})
        yield (
            key.meal_plan_id,
            {
                **row,
                "meal_plan_id": key.meal_plan_id,
                "date": key.on.isoformat(),
                "meal": str(key.meal),
            },
        )


def _slot_rows(seed: DemoSeed, plans: Mapping[str, _PlanKey]) -> Iterable[Row]:
    for plan in seed.meal_plans:
        plan_id = plans[plan.meal_plan_id].meal_plan_id
        for s in plan.slots:
            yield f"{plan_id} {s.slot_id}", {**_columns(s, exclude=set()), "meal_plan_id": plan_id}


# 발주에서 열로 옮기지 않거나(`source_note`, `slot_intakes`) 바꿔서 넣는 필드.
_ORDER_CONVERTED_FIELDS = {
    "meal_order_id",
    "meal_plan_id",
    "order_from_offset",
    "order_from_meal",
    "record_status",
    "incomplete",
    "slot_intakes",
    "source_note",
}


def _order_rows(seed: DemoSeed, demo_date: date, plans: Mapping[str, _PlanKey]) -> Iterable[Row]:
    for o in seed.meal_orders:
        plan = plans[o.meal_plan_id]
        order_id = _order_id(o, plan)
        yield (
            order_id,
            {
                **_columns(o, exclude=_ORDER_CONVERTED_FIELDS),
                "meal_order_id": order_id,
                "meal_plan_id": plan.meal_plan_id,
                "order_from": _order_from(o, demo_date),
                "record_status": str(_record_status(o)),
                "incomplete": int(o.incomplete),
            },
        )


def _slot_intake_rows(seed: DemoSeed, plans: Mapping[str, _PlanKey]) -> Iterable[Row]:
    for o in seed.meal_orders:
        order_id = _order_id(o, plans[o.meal_plan_id])
        for i in o.slot_intakes:
            row = _columns(i, exclude={"quality_issues"})
            yield (
                f"{order_id} {i.slot_id}",
                {
                    **row,
                    "meal_order_id": order_id,
                    "quality_issues": quality_issues_to_json(i.quality_issues),
                },
            )


def _meta_rows(demo_date: date, now: datetime, cleanup_pending: bool) -> Iterable[Row]:
    values = {
        "schema_version": str(SCHEMA_VERSION),
        "demo_date": demo_date.isoformat(),
        "seeded_at": now.strftime(LOCAL_TIMESTAMP_FORMAT),
    }
    if cleanup_pending:
        values = {**values, CLEANUP_PENDING_KEY: CLEANUP_PENDING_VALUE}
    return ((key, {"key": key, "value": value}) for key, value in values.items())


# 파생 테이블 ---------------------------------------------------------------


def _insert_derived(
    conn: sqlite3.Connection,
    seed: DemoSeed,
    demo_date: date,
    engine: NutritionEngine,
    plans: Mapping[str, _PlanKey],
) -> tuple[int, int]:
    """환자별 관찰 시작일부터 D-1까지 각 날짜의 일별 섭취와 경고를 계산해 넣는다(D0 제외).

    배식 계획이 없는 날도 끼니 0개로 계산해 행을 만든다.
    """
    results = evaluate_patients(seed, demo_date, engine, _meals_by_patient_day(seed, plans))
    daily_count = _insert_rows(conn, "daily_intakes", (_daily_row(r) for r in results))
    alert_count = _insert_rows(conn, "alerts", (_alert_row(r) for r in results))
    return daily_count, alert_count


def _meals_by_patient_day(
    seed: DemoSeed, plans: Mapping[str, _PlanKey]
) -> dict[tuple[str, date], tuple[MealRecord, ...]]:
    """(환자, 날짜)별 발주를 끼니 순(아침 → 점심 → 저녁) `MealRecord`로 묶는다."""
    grouped: dict[tuple[str, date], list[MealRecord]] = {}
    for o in seed.meal_orders:
        plan = plans[o.meal_plan_id]
        record = MealRecord(
            meal=plan.meal,
            order_status=o.order_status,
            record_status=_record_status(o),
            energy_kcal_est=o.energy_kcal_est,
            protein_g_est=o.protein_g_est,
        )
        grouped.setdefault((o.patient_id, plan.on), []).append(record)
    return {
        key: tuple(sorted(records, key=lambda r: _MEAL_INDEX[r.meal]))
        for key, records in grouped.items()
    }


def _daily_row(result: PatientDay) -> Row:
    on, intake = result.day.isoformat(), result.intake
    return (
        f"{result.patient_id} {on}",
        {
            "patient_id": result.patient_id,
            "date": on,
            "energy_kcal": intake.energy_kcal,
            "protein_g": intake.protein_g,
            "energy_pct": intake.energy_pct,
            "protein_pct": intake.protein_pct,
            "recorded_meals": intake.recorded_meals,
            "unrecorded_meals": intake.unrecorded_meals,
            "npo_meals": intake.npo_meals,
        },
    )


def _alert_row(result: PatientDay) -> Row:
    on, alert = result.day.isoformat(), result.alert
    alert_id = f"alert_{result.patient_id}_{on}"
    return (
        alert_id,
        {
            "alert_id": alert_id,
            "patient_id": result.patient_id,
            "evaluated_at": f"{on}T{SEED_ALERT_TIME}",
            "level": str(alert.level),
            "basis_period": format_basis_period(alert.period_start, alert.period_end),
            "basis_values": evidence_to_json(alert.evidence),
            "nutrients": nutrients_to_json(alert.nutrients),
            "unrecorded_meals": alert.unrecorded_meals,
        },
    )
