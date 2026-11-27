"""시드 적재(`build_database`)와 엔진 선택(`build_engine`) 테스트 (스펙 3.7).

실제 시드를 시연일 2026-12-05(D0)로 적재한다. D-7은 2026-11-28, D-1은 2026-12-04다.
읽기 전용 테스트는 모듈 범위로 한 번 적재한 DB를 함께 쓴다.
"""

from __future__ import annotations

import json
import re
import sqlite3
import subprocess
import sys
from dataclasses import replace
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from app import wiring
from app.config import DEFAULT_SEED_PATH, ConfigError, Settings
from app.nutrition.fake import FakeNutritionEngine
from app.nutrition.types import (
    AlertLevel,
    AlertResult,
    DailyIntake,
    DailyTarget,
    MealRecord,
    MealType,
    Nutrient,
    NutrientEvidence,
    OrderStatus,
    PatientProfile,
    RecordStatus,
    Sex,
    TargetRecord,
    TargetSource,
    WeightRecord,
)
from app.storage.db import SCHEMA_VERSION, connect
from app.storage.errors import SeedError
from app.storage.queries import (
    demo_timestamp,
    get_meal_plan,
    list_alerts,
    list_daily_intakes,
    list_meal_orders,
    list_patients,
)
from app.storage.seed import (
    CLEANUP_PENDING_KEY,
    SeedCounts,
    build_database,
    build_engine,
    load_seed_file,
)
from app.storage.seed_models import DemoSeed
from tests.storage.demo import DEMO
from tests.storage.dump import table_dump
from tests.storage.rows import insert_alert

D_MINUS_7 = DEMO - timedelta(days=7)
D_MINUS_1 = DEMO - timedelta(days=1)
D_MINUS_2 = DEMO - timedelta(days=2)
PAST_DAYS = tuple(D_MINUS_7 + timedelta(days=i) for i in range(7))
TABLE_COUNT = 15
BACKEND_DIR = Path(__file__).resolve().parents[2]
SEEDED_AT_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")


@pytest.fixture(scope="module")
def seed() -> DemoSeed:
    return load_seed_file(DEFAULT_SEED_PATH)


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory, seed: DemoSeed) -> tuple[Path, SeedCounts]:
    """실제 시드를 D=2026-12-05로 한 번 적재한 DB. 읽기 전용 테스트만 쓴다."""
    path = tmp_path_factory.mktemp("seed") / "app.db"
    counts = build_database(path, seed, DEMO, FakeNutritionEngine())
    return path, counts


@pytest.fixture
def conn(built: tuple[Path, SeedCounts]):
    path, _ = built
    with connect(path) as connection:
        yield connection
        connection.rollback()


def _raw(conn: sqlite3.Connection, sql: str, params: tuple[object, ...] = ()) -> list[sqlite3.Row]:
    return conn.execute(sql, params).fetchall()


def _seed_meta(conn: sqlite3.Connection) -> dict[str, str]:
    return {r["key"]: r["value"] for r in _raw(conn, "SELECT key, value FROM seed_meta")}


# 행 수 ---------------------------------------------------------------------


def test_build_database_returns_row_counts(built: tuple[Path, SeedCounts]) -> None:
    _, counts = built

    assert counts == SeedCounts(
        patients=10,
        patient_weights=20,
        patient_targets=10,
        patient_assessments=43,
        meal_plans=24,
        meal_plan_slots=144,
        meal_orders=240,
        slot_intakes=counts.slot_intakes,
        daily_intakes=70,
        alerts=70,
    )
    assert counts.slot_intakes > 0


def test_build_database_slot_intake_count_matches_seed(
    built: tuple[Path, SeedCounts], seed: DemoSeed, conn: sqlite3.Connection
) -> None:
    _, counts = built
    expected = sum(len(o.slot_intakes) for o in seed.meal_orders)

    assert counts.slot_intakes == expected
    assert _raw(conn, "SELECT count(*) AS n FROM slot_intakes")[0]["n"] == expected


def test_build_database_each_patient_has_past_week(
    conn: sqlite3.Connection, seed: DemoSeed
) -> None:
    patients = list_patients(conn)
    seed_intakes = {
        (o.patient_id, o.meal_plan_id.split("_")[0], o.meal_plan_id.split("_")[1]): len(
            o.slot_intakes
        )
        for o in seed.meal_orders
    }

    assert [p.patient_id for p in patients] == [p.patient_id for p in seed.patients]
    for patient in patients:
        orders = list_meal_orders(conn, patient.patient_id, D_MINUS_7, D_MINUS_1)
        assert len(orders) == 21
        for order in orders:
            offset = f"D{(order.on - DEMO).days}"
            key = (patient.patient_id, offset, str(order.meal))
            assert len(order.slot_intakes) == seed_intakes[key]
        assert len(list_daily_intakes(conn, patient.patient_id, D_MINUS_7, D_MINUS_1)) == 7
        assert len(list_alerts(conn, patient.patient_id, D_MINUS_7, D_MINUS_1)) == 7


# D0 ------------------------------------------------------------------------


def test_build_database_demo_day_has_plans_and_orders_only(conn: sqlite3.Connection) -> None:
    plans = [get_meal_plan(conn, DEMO, meal) for meal in MealType]
    orders = [
        order
        for patient in list_patients(conn)
        for order in list_meal_orders(conn, patient.patient_id, DEMO, DEMO)
    ]

    assert all(plan is not None for plan in plans)
    assert len(orders) == 30
    ordered = [o for o in orders if o.order_status is OrderStatus.ORDERED]
    npo = [o for o in orders if o.order_status is OrderStatus.NPO]
    assert len(ordered) == 29
    assert all(o.record_status is RecordStatus.NOT_RECORDED for o in ordered)
    assert len(npo) == 1
    assert all(o.slot_intakes == () for o in orders)
    for patient in list_patients(conn):
        assert list_daily_intakes(conn, patient.patient_id, DEMO, DEMO) == ()


# 변환 ----------------------------------------------------------------------


def test_build_database_converts_ids_from_fields(conn: sqlite3.Connection) -> None:
    plan_ids = {r["meal_plan_id"] for r in _raw(conn, "SELECT meal_plan_id FROM meal_plans")}
    order = _raw(
        conn,
        "SELECT meal_plan_id FROM meal_orders WHERE meal_order_id = ?",
        ("NS01_2026-11-28_breakfast",),
    )

    assert "2026-11-28_breakfast_general" in plan_ids
    assert not any(pid.startswith("D") for pid in plan_ids)
    assert [r["meal_plan_id"] for r in order] == ["2026-11-28_breakfast_general"]


def test_build_database_converts_patient_fields(conn: sqlite3.Connection, seed: DemoSeed) -> None:
    rows = {r["patient_id"]: r for r in _raw(conn, "SELECT * FROM patients")}

    for patient in seed.patients:
        row = rows[patient.patient_id]
        assert row["birth_year"] == DEMO.year - patient.age_at_d0
        assert (
            row["observation_start"]
            == (DEMO + timedelta(days=patient.observation_start_offset)).isoformat()
        )
        assert json.loads(row["conditions"]) == list(patient.conditions)
    assert rows["NS01"]["birth_year"] == 1953
    assert rows["NS01"]["conditions"] == '["고혈압"]'


def test_build_database_converts_order_from_and_npo_status(conn: sqlite3.Connection) -> None:
    order_from = {r["order_from"] for r in _raw(conn, "SELECT order_from FROM meal_orders")}
    npo = _raw(
        conn,
        "SELECT record_status FROM meal_orders WHERE meal_order_id = ?",
        ("NS01_2026-12-02_lunch",),
    )

    assert order_from == {"2026-11-28 breakfast"}
    assert [r["record_status"] for r in npo] == ["not_recorded"]


def test_build_database_keeps_seed_meal_values(conn: sqlite3.Connection, seed: DemoSeed) -> None:
    rows = _raw(
        conn,
        "SELECT o.patient_id, p.date, p.meal, o.energy_kcal_est, o.protein_g_est, o.incomplete "
        "FROM meal_orders AS o JOIN meal_plans AS p ON p.meal_plan_id = o.meal_plan_id",
    )
    stored = {
        (r["patient_id"], r["date"], r["meal"]): (
            r["energy_kcal_est"],
            r["protein_g_est"],
            r["incomplete"],
        )
        for r in rows
    }
    plans = {p.meal_plan_id: p for p in seed.meal_plans}

    for order in seed.meal_orders:
        plan = plans[order.meal_plan_id]
        on = (DEMO + timedelta(days=plan.day_offset)).isoformat()
        assert stored[(order.patient_id, on, str(plan.meal))] == (
            order.energy_kcal_est,
            order.protein_g_est,
            int(order.incomplete),
        )


def test_build_database_writes_json_arrays(conn: sqlite3.Connection) -> None:
    issues = _raw(conn, "SELECT DISTINCT quality_issues FROM slot_intakes")

    assert all(isinstance(json.loads(r["quality_issues"]), list) for r in issues)


def test_build_database_uses_order_from_meal_and_null_offset(
    tmp_path: Path, seed: DemoSeed
) -> None:
    first, second, *rest = seed.meal_orders
    changed = seed.model_copy(
        update={
            "meal_orders": (
                first.model_copy(update={"order_from_meal": MealType.DINNER}),
                second.model_copy(update={"order_from_offset": None}),
                *rest,
            )
        }
    )
    path = tmp_path / "app.db"

    build_database(path, changed, DEMO, FakeNutritionEngine())

    with connect(path) as c:
        rows = dict(
            (r["meal_order_id"], r["order_from"])
            for r in _raw(c, "SELECT meal_order_id, order_from FROM meal_orders")
        )
    assert rows["NS01_2026-11-28_breakfast"] == "2026-11-28 dinner"
    assert rows["NS01_2026-11-28_lunch"] is None


def test_build_database_unserved_slot_has_no_intakes(conn: sqlite3.Connection) -> None:
    plan = get_meal_plan(conn, D_MINUS_2, MealType.LUNCH)
    assert plan is not None
    slot_5 = next(s for s in plan.slots if s.slot_id == "slot_5")
    orders = _raw(
        conn, "SELECT meal_order_id FROM meal_orders WHERE meal_plan_id = ?", (plan.meal_plan_id,)
    )
    slot_5_intakes = _raw(
        conn,
        "SELECT count(*) AS n FROM slot_intakes AS i "
        "JOIN meal_orders AS o ON o.meal_order_id = i.meal_order_id "
        "WHERE o.meal_plan_id = ? AND i.slot_id = 'slot_5'",
        (plan.meal_plan_id,),
    )

    assert slot_5.menu_name is None
    assert slot_5.served_g == pytest.approx(0.0)
    assert len(orders) == 10
    assert slot_5_intakes[0]["n"] == 0


# 파생 테이블 ---------------------------------------------------------------


def test_build_database_alert_rows_follow_seed_rules(conn: sqlite3.Connection) -> None:
    for patient in list_patients(conn):
        alerts = list_alerts(conn, patient.patient_id, D_MINUS_7, D_MINUS_1)
        daily = list_daily_intakes(conn, patient.patient_id, D_MINUS_7, D_MINUS_1)
        running = 0
        for alert, day, intake in zip(alerts, PAST_DAYS, daily, strict=True):
            running += intake.unrecorded_meals
            assert alert.alert_id == f"alert_{patient.patient_id}_{day.isoformat()}"
            assert alert.evaluated_at == f"{day.isoformat()}T23:59:59"
            assert alert.level is AlertLevel.NONE
            assert alert.basis_period is None
            assert alert.nutrients == ()
            # Fake 엔진은 누적 이력의 미기록 끼니 합을 돌려준다(이력이 그날까지인지 확인).
            assert alert.unrecorded_meals == running
    raw = _raw(conn, "SELECT DISTINCT basis_values, nutrients FROM alerts")
    assert [(r["basis_values"], r["nutrients"]) for r in raw] == [("[]", "[]")]


def test_build_database_daily_intakes_follow_fake_engine(conn: sqlite3.Connection) -> None:
    orders = list_meal_orders(conn, "NS01", D_MINUS_7, D_MINUS_7)
    recorded = [o for o in orders if o.record_status is RecordStatus.RECORDED]
    energy = sum(o.energy_kcal_est or 0.0 for o in recorded)

    (row,) = list_daily_intakes(conn, "NS01", D_MINUS_7, D_MINUS_7)

    assert row.recorded_meals == len(recorded)
    assert row.energy_kcal == pytest.approx(energy)
    assert row.energy_pct == pytest.approx(energy * 3 / len(recorded) / 1500.0 * 100)


class _SpyEngine(FakeNutritionEngine):
    """Fake 계산을 그대로 하면서 엔진 입력을 기록한다."""

    def __init__(self) -> None:
        self.targets: list[tuple[PatientProfile, tuple, tuple, date]] = []
        self.intakes: list[tuple[date, tuple[MealRecord, ...]]] = []
        self.alerts: list[tuple[tuple[DailyIntake, ...], date]] = []

    def daily_target(self, profile, targets, weights, on):  # type: ignore[override]
        self.targets.append((profile, targets, weights, on))
        return super().daily_target(profile, targets, weights, on)

    def daily_intake(self, on, meals, target):  # type: ignore[override]
        self.intakes.append((on, meals))
        return super().daily_intake(on, meals, target)

    def evaluate_alert(self, history, rules, on):  # type: ignore[override]
        self.alerts.append((history, on))
        return super().evaluate_alert(history, rules, on)


def test_build_database_passes_patient_inputs_to_engine(tmp_path: Path, seed: DemoSeed) -> None:
    spy = _SpyEngine()

    build_database(tmp_path / "app.db", seed, DEMO, spy)

    profile, targets, weights, on = spy.targets[0]
    assert profile == PatientProfile(sex=Sex.MALE, birth_year=1953)
    assert targets == (TargetRecord(D_MINUS_7, 1800.0, 65.0, TargetSource.TEAM_SET),)
    assert weights == (
        WeightRecord(DEMO - timedelta(days=38), 63.0),
        WeightRecord(D_MINUS_7, 63.0),
    )
    assert on == D_MINUS_7
    assert [day for _, _, _, day in spy.targets[:7]] == list(PAST_DAYS)
    assert len(spy.targets) == 70


def test_build_database_passes_day_meals_and_history(tmp_path: Path, seed: DemoSeed) -> None:
    spy = _SpyEngine()

    build_database(tmp_path / "app.db", seed, DEMO, spy)

    on, meals = spy.intakes[4]  # NS01 D-3: 점심 금식
    assert on == DEMO - timedelta(days=3)
    assert [m.meal for m in meals] == [MealType.BREAKFAST, MealType.LUNCH, MealType.DINNER]
    assert meals[1] == MealRecord(
        meal=MealType.LUNCH,
        order_status=OrderStatus.NPO,
        record_status=RecordStatus.NOT_RECORDED,
        energy_kcal_est=None,
        protein_g_est=None,
    )
    assert all(day < DEMO for day, _ in spy.intakes)
    for index, (history, day) in enumerate(spy.alerts[:7]):
        assert day == PAST_DAYS[index]
        assert [h.on for h in history] == list(PAST_DAYS[: index + 1])


# seed_meta -----------------------------------------------------------------


def test_build_database_writes_seed_meta(conn: sqlite3.Connection) -> None:
    meta = _seed_meta(conn)

    assert set(meta) == {"schema_version", "demo_date", "seeded_at"}
    assert meta["schema_version"] == str(SCHEMA_VERSION)
    assert meta["demo_date"] == "2026-12-05"
    assert SEEDED_AT_PATTERN.fullmatch(meta["seeded_at"])


def test_build_database_seeded_at_uses_clock(tmp_path: Path, seed: DemoSeed) -> None:
    path = tmp_path / "app.db"

    build_database(
        path,
        seed,
        DEMO,
        FakeNutritionEngine(),
        clock=lambda: datetime(2026, 11, 27, 9, 8, 7, 654321),
    )

    with connect(path) as c:
        assert _seed_meta(c)["seeded_at"] == "2026-11-27T09:08:07"


def test_build_database_cleanup_pending_flag(tmp_path: Path, seed: DemoSeed) -> None:
    path = tmp_path / "app.db"

    build_database(path, seed, DEMO, FakeNutritionEngine(), cleanup_pending=True)

    with connect(path) as c:
        assert "cleanup_pending" in _seed_meta(c)


# 결정성·조회 순서 ----------------------------------------------------------


def test_build_database_is_deterministic(tmp_path: Path, seed: DemoSeed) -> None:
    first, second = tmp_path / "a.db", tmp_path / "b.db"
    build_database(first, seed, DEMO, FakeNutritionEngine(), clock=lambda: datetime(2026, 1, 1))
    build_database(second, seed, DEMO, FakeNutritionEngine(), clock=lambda: datetime(2026, 2, 2))

    a, b = table_dump(first), table_dump(second)

    assert len(a) == TABLE_COUNT
    assert a == b


def test_demo_timestamp_alert_sorts_after_seed_alerts(tmp_path: Path, seed: DemoSeed) -> None:
    path = tmp_path / "app.db"
    build_database(path, seed, DEMO, FakeNutritionEngine())
    evaluated_at = demo_timestamp(DEMO, datetime(2026, 11, 27, 10, 0, 0))

    with connect(path) as c:
        insert_alert(c, alert_id="A_live", patient_id="NS01", evaluated_at=evaluated_at)
        alerts = list_alerts(c, "NS01", D_MINUS_7, DEMO)

    assert alerts[-1].alert_id == "A_live"
    assert alerts[-1].evaluated_at == "2026-12-05T10:00:00"


# 엔진 선택 -----------------------------------------------------------------


class _LowTargetEngine(FakeNutritionEngine):
    """목표 1,000 kcal를 주는 대체 엔진."""

    def daily_target(self, profile, targets, weights, on):  # type: ignore[override]
        return DailyTarget(energy_kcal=1000.0, protein_g=40.0, source=TargetSource.TEAM_SET)


def test_build_engine_default_is_fake() -> None:
    assert isinstance(build_engine(Settings(_env_file=None)), FakeNutritionEngine)


def test_build_engine_unknown_name_raises_config_error() -> None:
    with pytest.raises(ConfigError, match="nutrition_engine"):
        build_engine(Settings(nutrition_engine="missing", _env_file=None))


def test_build_engine_selected_engine_sets_daily_targets(
    tmp_path: Path, seed: DemoSeed, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(wiring.NUTRITION_ENGINES, "alt", lambda settings: _LowTargetEngine())
    engine = build_engine(Settings(nutrition_engine="alt", _env_file=None))
    path = tmp_path / "app.db"

    build_database(path, seed, DEMO, engine)

    with connect(path) as c:
        (row,) = list_daily_intakes(c, "NS01", D_MINUS_7, D_MINUS_7)
    assert isinstance(engine, _LowTargetEngine)
    assert row.energy_pct == pytest.approx(row.energy_kcal * 3 / row.recorded_meals / 1000 * 100)
    assert row.protein_pct == pytest.approx(row.protein_g * 3 / row.recorded_meals / 40 * 100)


# 실패 ----------------------------------------------------------------------


def _table_names(path: Path) -> list[str]:
    with sqlite3.connect(path) as c:
        rows = c.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return [name for (name,) in rows]


def test_build_database_integrity_error_names_table_and_id(tmp_path: Path, seed: DemoSeed) -> None:
    duplicated = seed.model_copy(update={"patients": (*seed.patients, seed.patients[0])})
    path = tmp_path / "app.db"

    with pytest.raises(SeedError, match=r"patients.*NS01") as info:
        build_database(path, duplicated, DEMO, FakeNutritionEngine())

    assert isinstance(info.value.__cause__, sqlite3.IntegrityError)
    assert _table_names(path) == []


def test_build_database_trigger_error_names_table_and_id(tmp_path: Path, seed: DemoSeed) -> None:
    index, order = next(
        (i, o)
        for i, o in enumerate(seed.meal_orders)
        if o.meal_plan_id == "D-2_lunch_general" and o.slot_intakes
    )
    bad_intake = order.slot_intakes[0].model_copy(update={"slot_id": "slot_5"})
    bad_order = order.model_copy(update={"slot_intakes": (*order.slot_intakes, bad_intake)})
    orders = (*seed.meal_orders[:index], bad_order, *seed.meal_orders[index + 1 :])
    broken = seed.model_copy(update={"meal_orders": orders})
    expected_id = f"{order.patient_id}_{D_MINUS_2.isoformat()}_lunch"

    with pytest.raises(SeedError, match=rf"slot_intakes.*{expected_id}"):
        build_database(tmp_path / "app.db", broken, DEMO, FakeNutritionEngine())


def test_build_database_commit_integrity_error_raises_seed_error(
    tmp_path: Path, seed: DemoSeed
) -> None:
    first, *rest = seed.meal_plans
    broken = seed.model_copy(
        update={"meal_plans": (first.model_copy(update={"baseline_photo_id": "P9999"}), *rest)}
    )
    path = tmp_path / "app.db"

    with pytest.raises(SeedError) as info:
        build_database(path, broken, DEMO, FakeNutritionEngine())

    assert isinstance(info.value.__cause__, sqlite3.IntegrityError)
    assert _table_names(path) == []


class _ExplodingEngine(FakeNutritionEngine):
    def daily_intake(self, on, meals, target):  # type: ignore[override]
        raise RuntimeError("엔진 실패 주입")


def test_build_database_engine_error_rolls_back_schema(tmp_path: Path, seed: DemoSeed) -> None:
    path = tmp_path / "app.db"

    with pytest.raises(RuntimeError, match="엔진 실패 주입"):
        build_database(path, seed, DEMO, _ExplodingEngine())

    assert _table_names(path) == []


def test_seed_counts_is_frozen(built: tuple[Path, SeedCounts]) -> None:
    _, counts = built

    with pytest.raises(AttributeError):
        counts.patients = 0  # type: ignore[misc]
    assert replace(counts, patients=1).patients == 1


# 리뷰 보강: 엔진 판정 값·환자별 관찰 기간·판정일 ------------------------------


class _CautionEngine(FakeNutritionEngine):
    """에너지 `caution` 판정과 근거를 돌려주는 대체 엔진."""

    def evaluate_alert(self, history, rules, on):  # type: ignore[override]
        return AlertResult(
            level=AlertLevel.CAUTION,
            nutrients=(Nutrient.ENERGY,),
            period_start=on - timedelta(days=6),
            period_end=on,
            evidence=(NutrientEvidence(Nutrient.ENERGY, avg_pct=62.5, low_days_streak=2),),
            unrecorded_meals=1,
        )


def test_build_database_stores_engine_alert_values(tmp_path: Path, seed: DemoSeed) -> None:
    path = tmp_path / "app.db"

    build_database(path, seed, DEMO, _CautionEngine())

    with connect(path) as c:
        alert = list_alerts(c, "NS01", D_MINUS_1, D_MINUS_1)[0]
    assert alert.level is AlertLevel.CAUTION
    assert alert.basis_period == f"{(D_MINUS_1 - timedelta(days=6)).isoformat()}~2026-12-04"
    assert alert.basis_values == (
        NutrientEvidence(Nutrient.ENERGY, avg_pct=62.5, low_days_streak=2),
    )
    assert alert.nutrients == (Nutrient.ENERGY,)
    assert alert.unrecorded_meals == 1


def _with_observation_start(seed: DemoSeed, patient_id: str, offset: int) -> DemoSeed:
    patients = tuple(
        p.model_copy(update={"observation_start_offset": offset})
        if p.patient_id == patient_id
        else p
        for p in seed.patients
    )
    return seed.model_copy(update={"patients": patients})


def test_build_database_later_observation_start_limits_rows(tmp_path: Path, seed: DemoSeed) -> None:
    path = tmp_path / "app.db"

    counts = build_database(path, _with_observation_start(seed, "NS02", -3), DEMO, _SpyEngine())

    with connect(path) as c:
        daily = list_daily_intakes(c, "NS02", D_MINUS_7, DEMO)
        alerts = list_alerts(c, "NS02", D_MINUS_7, DEMO)
    expected = [DEMO - timedelta(days=n) for n in (3, 2, 1)]
    assert [row.on for row in daily] == expected
    assert [a.alert_id for a in alerts] == [f"alert_NS02_{d.isoformat()}" for d in expected]
    assert counts.daily_intakes == 70 - 7 + 3
    assert counts.alerts == 70 - 7 + 3


def test_build_database_day_without_plan_gets_empty_row(tmp_path: Path, seed: DemoSeed) -> None:
    path = tmp_path / "app.db"
    d_minus_9 = DEMO - timedelta(days=9)

    build_database(path, _with_observation_start(seed, "NS03", -9), DEMO, FakeNutritionEngine())

    with connect(path) as c:
        daily = list_daily_intakes(c, "NS03", d_minus_9, D_MINUS_1)
    assert [row.on for row in daily] == [d_minus_9 + timedelta(days=i) for i in range(9)]
    first = daily[0]
    assert (first.recorded_meals, first.unrecorded_meals, first.npo_meals) == (0, 0, 0)
    assert first.energy_kcal is None
    assert first.energy_pct is None


class _WrongDayEngine(FakeNutritionEngine):
    """`daily_intake`가 입력과 다른 날짜를 돌려주는 엔진."""

    def daily_intake(self, on, meals, target):  # type: ignore[override]
        return replace(super().daily_intake(on, meals, target), on=date(2000, 1, 1))


def test_build_database_uses_loop_day_not_engine_day(tmp_path: Path, seed: DemoSeed) -> None:
    path = tmp_path / "app.db"

    build_database(path, seed, DEMO, _WrongDayEngine())

    with connect(path) as c:
        daily = list_daily_intakes(c, "NS01", D_MINUS_7, D_MINUS_1)
        alerts = list_alerts(c, "NS01", D_MINUS_7, D_MINUS_1)
    assert [row.on for row in daily] == list(PAST_DAYS)
    assert [a.alert_id for a in alerts] == [f"alert_NS01_{d.isoformat()}" for d in PAST_DAYS]
    assert [a.evaluated_at for a in alerts] == [f"{d.isoformat()}T23:59:59" for d in PAST_DAYS]


def test_cleanup_pending_key_names_seed_meta_row(tmp_path: Path, seed: DemoSeed) -> None:
    path = tmp_path / "app.db"

    build_database(path, seed, DEMO, FakeNutritionEngine(), cleanup_pending=True)

    with connect(path) as c:
        assert CLEANUP_PENDING_KEY in _seed_meta(c)
    assert CLEANUP_PENDING_KEY == "cleanup_pending"


def test_import_seed_does_not_load_wiring() -> None:
    code = "import sys; import app.storage.seed; sys.exit(1 if 'app.wiring' in sys.modules else 0)"
    result = subprocess.run([sys.executable, "-c", code], cwd=BACKEND_DIR, check=False)

    assert result.returncode == 0
