"""시드 파일 검증(`load_seed_file`)과 시연일 범위 검사(`check_demo_date_range`) 테스트.

잘못된 시드는 실제 시드 JSON을 깊은 복사해 고친 뒤 `tmp_path`에 써서 만든다.
"""

from __future__ import annotations

import copy
import json
import os
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from app.config import DEFAULT_SEED_PATH, ConfigError
from app.intake.types import SlotStatus
from app.nutrition.types import MealType, OrderStatus, RecordStatus, Sex
from app.storage.errors import (
    AppLockedError,
    DemoDateRangeError,
    ResetBusyError,
    ResetCleanupError,
    SeedError,
    StoragePrepareError,
    StorageReplaceError,
)
from app.storage.seed import check_demo_date_range, load_seed_file
from app.storage.seed_models import DemoSeed

SeedDict = dict[str, Any]


@pytest.fixture(scope="module")
def real_seed_dict() -> SeedDict:
    """실제 시드 JSON 원본. 테스트는 이것을 직접 고치지 않고 깊은 복사본을 고친다."""
    return json.loads(DEFAULT_SEED_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def seed_dict(real_seed_dict: SeedDict) -> SeedDict:
    """테스트마다 새로 만든 실제 시드의 깊은 복사본."""
    return copy.deepcopy(real_seed_dict)


@pytest.fixture(scope="module")
def real_seed() -> DemoSeed:
    return load_seed_file(DEFAULT_SEED_PATH)


def _write(tmp_path: Path, data: object) -> Path:
    path = tmp_path / "seed.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def _plan(data: SeedDict, meal_plan_id: str) -> dict[str, Any]:
    return next(p for p in data["meal_plans"] if p["meal_plan_id"] == meal_plan_id)


def _order(data: SeedDict, meal_order_id: str) -> dict[str, Any]:
    return next(o for o in data["meal_orders"] if o["meal_order_id"] == meal_order_id)


# --- 실제 시드 -----------------------------------------------------------------


def test_load_seed_file_real_seed_counts(real_seed: DemoSeed) -> None:
    assert len(real_seed.patients) == 10
    assert len(real_seed.patient_weights) == 20
    assert len(real_seed.patient_targets) == 10
    assert len(real_seed.patient_assessments) == 43
    assert len(real_seed.meal_plans) == 24
    assert all(len(plan.slots) == 6 for plan in real_seed.meal_plans)
    assert len(real_seed.meal_orders) == 240
    assert sum(len(order.slot_intakes) for order in real_seed.meal_orders) == 1226


def test_load_seed_file_unserved_slot_reads_as_null_menu(real_seed: DemoSeed) -> None:
    plan = next(p for p in real_seed.meal_plans if p.meal_plan_id == "D-2_lunch_general")
    slot_5 = next(s for s in plan.slots if s.slot_id == "slot_5")
    assert slot_5.menu_name is None
    assert slot_5.served_g == pytest.approx(0.0)
    orders = [o for o in real_seed.meal_orders if o.meal_plan_id == "D-2_lunch_general"]
    assert orders
    assert all(i.slot_id != "slot_5" for o in orders for i in o.slot_intakes)


def test_load_seed_file_uses_existing_enums(real_seed: DemoSeed) -> None:
    patient = real_seed.patients[0]
    assert isinstance(patient.sex, Sex)
    plan = real_seed.meal_plans[0]
    assert isinstance(plan.meal, MealType)
    order = real_seed.meal_orders[0]
    assert isinstance(order.order_status, OrderStatus)
    assert isinstance(order.record_status, RecordStatus)
    assert isinstance(order.slot_intakes[0].status, SlotStatus)


def test_load_seed_file_npo_order_keeps_null_record_status(real_seed: DemoSeed) -> None:
    npo = [o for o in real_seed.meal_orders if o.order_status is OrderStatus.NPO]
    assert len(npo) == 2
    assert all(o.record_status is None for o in npo)


def test_load_seed_file_order_from_meal_defaults_to_none(real_seed: DemoSeed) -> None:
    assert all(o.order_from_meal is None for o in real_seed.meal_orders)


def test_load_seed_file_accepts_order_from_meal(tmp_path: Path, seed_dict: SeedDict) -> None:
    seed_dict["meal_orders"][0]["order_from_meal"] = "lunch"
    seed = load_seed_file(_write(tmp_path, seed_dict))
    assert seed.meal_orders[0].order_from_meal is MealType.LUNCH


def test_load_seed_file_ignores_source_note_and_meta(tmp_path: Path, seed_dict: SeedDict) -> None:
    seed_dict["meta"] = {"anything": [1, 2, {"x": None}]}
    seed_dict["meal_orders"][0]["source_note"] = "아무 메모"
    seed = load_seed_file(_write(tmp_path, seed_dict))
    assert len(seed.meal_orders) == 240


def test_load_seed_file_accepts_cancelled_order_without_record(
    tmp_path: Path, seed_dict: SeedDict
) -> None:
    order = seed_dict["meal_orders"][0]
    order.update(order_status="cancelled", record_status=None, slot_intakes=[])
    seed = load_seed_file(_write(tmp_path, seed_dict))
    assert seed.meal_orders[0].order_status is OrderStatus.CANCELLED
    assert seed.meal_orders[0].record_status is None


# --- 변형 도우미 ---------------------------------------------------------------

Mutation = Callable[[SeedDict], None]


def _parent(d: SeedDict, path: tuple[Any, ...]) -> Any:
    target: Any = d
    for key in path[:-1]:
        target = target[key]
    return target


def _set(path: tuple[Any, ...], value: Any) -> Mutation:
    """`path`가 가리키는 값을 `value`로 바꾸는 변형."""

    def mutate(d: SeedDict) -> None:
        _parent(d, path)[path[-1]] = value

    return mutate


def _delete(path: tuple[Any, ...]) -> Mutation:
    """`path`가 가리키는 키를 지우는 변형."""

    def mutate(d: SeedDict) -> None:
        del _parent(d, path)[path[-1]]

    return mutate


def _dup_first(table: str, **changes: Any) -> Mutation:
    """`table`의 첫 행을 복사해 `changes`를 적용한 뒤 끝에 붙이는 변형."""

    def mutate(d: SeedDict) -> None:
        d[table].append({**copy.deepcopy(d[table][0]), **changes})

    return mutate


def _drop_slot_intakes(d: SeedDict, meal_plan_id: str, slot_id: str) -> None:
    """`meal_plan_id` 계획을 발주한 모든 발주에서 `slot_id` 칸의 칸별 섭취를 뺀다."""
    for order in d["meal_orders"]:
        if order["meal_plan_id"] == meal_plan_id:
            order["slot_intakes"] = [i for i in order["slot_intakes"] if i["slot_id"] != slot_id]


# --- 형태 오류 -----------------------------------------------------------------


def _unserved_with_menu(d: SeedDict) -> None:
    _plan(d, "D-2_lunch_general")["slots"][4]["menu_name"] = "새 메뉴"


def _unserved_with_energy(d: SeedDict) -> None:
    _plan(d, "D-2_lunch_general")["slots"][4]["energy_kcal"] = 10


def _five_slots(d: SeedDict) -> None:
    plan = d["meal_plans"][0]
    plan["slots"] = plan["slots"][:5]
    _drop_slot_intakes(d, plan["meal_plan_id"], "slot_6")


def _npo_with_intake(d: SeedDict) -> None:
    npo = _order(d, "NS01_D-3_lunch")
    npo["slot_intakes"] = copy.deepcopy(_order(d, "NS02_D-3_lunch")["slot_intakes"][:1])


def _cancelled_with_intakes(d: SeedDict) -> None:
    d["meal_orders"][0]["order_status"] = "cancelled"


ORDER_0 = ("meal_orders", 0)
INTAKE_0 = ("meal_orders", 0, "slot_intakes", 0)
SLOT_0 = ("meal_plans", 0, "slots", 0)


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(_delete(("patients", 0, "sex")), id="missing-patient-sex"),
        pytest.param(_delete((*ORDER_0, "order_status")), id="missing-order-status"),
        pytest.param(_delete((*SLOT_0, "served_g")), id="missing-slot-served-g"),
        pytest.param(_delete((*INTAKE_0, "status")), id="missing-intake-status"),
        pytest.param(_delete(("patients",)), id="missing-patients-table"),
        pytest.param(_set((*ORDER_0, "order_status"), "fasting"), id="bad-order-status"),
        pytest.param(_set(("patients", 0, "sex"), "unknown"), id="bad-sex"),
        pytest.param(_set((*SLOT_0, "dish_type"), "dessert"), id="bad-dish"),
        pytest.param(_set(("patients", 0, "ckd_dialysis"), "yes"), id="bad-ckd-dialysis"),
        pytest.param(_set(("patients", 0, "data_source"), "real"), id="bad-data-source"),
        pytest.param(_set(("patient_assessments", 0, "kind"), "mood"), id="bad-assessment-kind"),
        pytest.param(_set(("patient_targets", 0, "source"), "guess"), id="bad-target-source"),
        pytest.param(_set(("meal_plans", 0, "meal"), "snack"), id="bad-meal"),
        pytest.param(_set((*ORDER_0, "record_status"), "done"), id="bad-record-status"),
        pytest.param(_set((*ORDER_0, "staff_zero_reason"), "x"), id="bad-zero-reason"),
        pytest.param(_set((*ORDER_0, "order_from_meal"), "brunch"), id="bad-from-meal"),
        pytest.param(_set((*INTAKE_0, "status"), "guessed"), id="bad-intake-status"),
        pytest.param(_set((*INTAKE_0, "quality_issues"), ["dark"]), id="bad-quality-issue"),
        pytest.param(_set((*INTAKE_0, "estimate_basis"), "vlm:"), id="bad-estimate-basis"),
        pytest.param(_set((*INTAKE_0, "intake_fraction_est"), 1.5), id="fraction-above-one"),
        pytest.param(_set((*INTAKE_0, "intake_fraction_est"), -0.1), id="fraction-below-zero"),
        pytest.param(_set((*SLOT_0, "served_g"), -1), id="negative-served"),
        pytest.param(_set(("patients", 0, "age_at_d0"), -1), id="negative-age"),
        pytest.param(_set(("patients", 0, "unknown_field"), 1), id="unknown-field"),
        pytest.param(_set(("patient_weights", 0, "weight_kg"), float("nan")), id="nan-weight"),
        pytest.param(_set((*SLOT_0, "energy_kcal"), float("inf")), id="inf-slot-energy"),
        pytest.param(_set((*ORDER_0, "record_status"), None), id="ordered-null-record"),
        pytest.param(_npo_with_intake, id="npo-with-intake"),
        pytest.param(_cancelled_with_intakes, id="cancelled-with-intakes"),
        pytest.param(_unserved_with_menu, id="unserved-with-menu"),
        pytest.param(_set((*SLOT_0, "menu_name"), None), id="served-without-menu"),
        pytest.param(_unserved_with_energy, id="unserved-with-energy"),
        pytest.param(_five_slots, id="plan-with-five-slots"),
    ],
)
def test_load_seed_file_shape_error_raises_seed_error(
    tmp_path: Path, seed_dict: SeedDict, mutate: Mutation
) -> None:
    mutate(seed_dict)
    with pytest.raises(SeedError):
        load_seed_file(_write(tmp_path, seed_dict))


def test_load_seed_file_top_level_array_raises_seed_error(tmp_path: Path) -> None:
    with pytest.raises(SeedError):
        load_seed_file(_write(tmp_path, []))


# --- 관계 오류 -----------------------------------------------------------------


def _dup_order_patient_day_meal(d: SeedDict) -> None:
    _dup_first("meal_plans", meal_plan_id="D-7_breakfast_soft", diet_type="soft")(d)
    _dup_first(
        "meal_orders", meal_order_id="NS01_D-7_breakfast_soft", meal_plan_id="D-7_breakfast_soft"
    )(d)


def _intake_on_unserved_slot(d: SeedDict) -> None:
    order = _order(d, "NS02_D-2_lunch")
    order["slot_intakes"].append({**copy.deepcopy(order["slot_intakes"][0]), "slot_id": "slot_5"})


def _dup_intake_slot(d: SeedDict) -> None:
    intakes = d["meal_orders"][0]["slot_intakes"]
    intakes.append(copy.deepcopy(intakes[0]))


def _dup_plan_slot(d: SeedDict) -> None:
    d["meal_plans"][0]["slots"][5]["slot_id"] = "slot_1"
    _drop_slot_intakes(d, d["meal_plans"][0]["meal_plan_id"], "slot_6")


@pytest.mark.parametrize(
    ("mutate", "table", "record_id"),
    [
        pytest.param(_dup_first("patients"), "patients", "NS01", id="dup-patient-id"),
        pytest.param(
            _dup_first("meal_plans", day_offset=-10),
            "meal_plans",
            "D-7_breakfast_general",
            id="dup-plan-id",
        ),
        pytest.param(
            _dup_first("meal_plans", meal_plan_id="D-7_breakfast_copy"),
            "meal_plans",
            "D-7_breakfast_copy",
            id="dup-plan-key",
        ),
        pytest.param(
            _dup_first("meal_orders", meal_plan_id="D-6_breakfast_general"),
            "meal_orders",
            "NS01_D-7_breakfast",
            id="dup-order-id",
        ),
        pytest.param(
            _dup_first("meal_orders", meal_order_id="NS01_D-7_breakfast_copy"),
            "meal_orders",
            "NS01_D-7_breakfast_copy",
            id="dup-pt-plan",
        ),
        pytest.param(
            _dup_order_patient_day_meal,
            "meal_orders",
            "NS01_D-7_breakfast_soft",
            id="dup-pt-day-meal",
        ),
        pytest.param(
            _set((*ORDER_0, "patient_id"), "NS99"), "meal_orders", "NS99", id="order-no-patient"
        ),
        pytest.param(
            _set((*ORDER_0, "meal_plan_id"), "D-9_breakfast_general"),
            "meal_orders",
            "D-9_breakfast_general",
            id="order-missing-plan",
        ),
        pytest.param(
            _set((*INTAKE_0, "slot_id"), "slot_9"), "slot_intakes", "slot_9", id="slot-not-in-plan"
        ),
        pytest.param(_intake_on_unserved_slot, "slot_intakes", "NS02_D-2_lunch", id="unserved"),
        pytest.param(_dup_intake_slot, "slot_intakes", "NS01_D-7_breakfast", id="dup-intake"),
        pytest.param(_dup_plan_slot, "meal_plan_slots", "D-7_breakfast_general", id="dup-slot"),
        pytest.param(
            _set(("patient_weights", 0, "patient_id"), "NS99"),
            "patient_weights",
            "NS99",
            id="weight-no-patient",
        ),
        pytest.param(
            _set(("patient_targets", 0, "patient_id"), "NS99"),
            "patient_targets",
            "NS99",
            id="target-no-patient",
        ),
        pytest.param(
            _set(("patient_assessments", 0, "patient_id"), "NS99"),
            "patient_assessments",
            "NS99",
            id="assess-no-patient",
        ),
        pytest.param(_dup_first("patient_weights"), "patient_weights", "NS01", id="dup-weight"),
        pytest.param(_dup_first("patient_targets"), "patient_targets", "NS01", id="dup-target"),
        pytest.param(
            _dup_first("patient_assessments"), "patient_assessments", "NS01", id="dup-assessment"
        ),
        pytest.param(
            _set(("meal_plans", 0, "baseline_photo_id"), "ph_" + "0" * 32),
            "meal_plans",
            "D-7_breakfast_general",
            id="plan-baseline-photo",
        ),
        pytest.param(
            _set((*ORDER_0, "post_photo_id"), "ph_" + "0" * 32),
            "meal_orders",
            "NS01_D-7_breakfast",
            id="order-post-photo",
        ),
    ],
)
def test_load_seed_file_relation_error_names_table_and_id(
    tmp_path: Path, seed_dict: SeedDict, mutate: Mutation, table: str, record_id: str
) -> None:
    mutate(seed_dict)
    with pytest.raises(SeedError) as exc_info:
        load_seed_file(_write(tmp_path, seed_dict))
    message = str(exc_info.value)
    assert table in message
    assert record_id in message


# --- 파일 오류 -----------------------------------------------------------------


def test_load_seed_file_missing_file_raises_prepare_error(tmp_path: Path) -> None:
    path = tmp_path / "none.json"
    with pytest.raises(StoragePrepareError, match="시드 파일을 읽지 못했다") as exc_info:
        load_seed_file(path)
    assert str(path) in str(exc_info.value)
    assert isinstance(exc_info.value.__cause__, OSError)


@pytest.mark.skipif(os.geteuid() == 0, reason="root는 읽기 권한 검사를 우회한다")
def test_load_seed_file_unreadable_file_raises_prepare_error(
    tmp_path: Path, real_seed_dict: SeedDict
) -> None:
    path = _write(tmp_path, real_seed_dict)
    path.chmod(0o000)
    try:
        with pytest.raises(StoragePrepareError) as exc_info:
            load_seed_file(path)
    finally:
        path.chmod(0o644)
    assert str(path) in str(exc_info.value)


def test_load_seed_file_directory_raises_prepare_error(tmp_path: Path) -> None:
    with pytest.raises(StoragePrepareError):
        load_seed_file(tmp_path)


def test_load_seed_file_json_syntax_error_raises_seed_error(tmp_path: Path) -> None:
    path = tmp_path / "seed.json"
    path.write_text('{"patients": [', encoding="utf-8")
    with pytest.raises(SeedError):
        load_seed_file(path)


def test_load_seed_file_deeply_nested_json_raises_seed_error(tmp_path: Path) -> None:
    path = tmp_path / "seed.json"
    path.write_text("[" * 200_000 + "]" * 200_000, encoding="utf-8")
    with pytest.raises(SeedError):
        load_seed_file(path)


def test_load_seed_file_non_utf8_raises_seed_error(tmp_path: Path) -> None:
    path = tmp_path / "seed.json"
    path.write_bytes(b'{"patients": "\xff\xfe"}')
    with pytest.raises(SeedError):
        load_seed_file(path)


# --- 시연일 범위 ---------------------------------------------------------------


def test_check_demo_date_range_first_year_raises(real_seed: DemoSeed) -> None:
    with pytest.raises(DemoDateRangeError) as exc_info:
        check_demo_date_range(real_seed, date(1, 1, 1))
    assert isinstance(exc_info.value, ConfigError)
    assert str(exc_info.value) == (
        "시연일 0001-01-01에 시드 날짜 오프셋(-38~0일)을 더하면 날짜 범위를 벗어난다"
    )


def test_check_demo_date_range_last_day_passes_when_offsets_not_positive(
    real_seed: DemoSeed,
) -> None:
    check_demo_date_range(real_seed, date(9999, 12, 31))


def test_check_demo_date_range_last_day_raises_when_offset_positive(
    tmp_path: Path, seed_dict: SeedDict
) -> None:
    seed_dict["patient_weights"][0]["day_offset"] = 3
    seed = load_seed_file(_write(tmp_path, seed_dict))
    with pytest.raises(DemoDateRangeError, match=r"\(-38~3일\)"):
        check_demo_date_range(seed, date(9999, 12, 31))


@pytest.mark.parametrize("offset", [3 * 10**6, -(10**6), 10**12, -(10**12)])
def test_check_demo_date_range_huge_offset_never_overflows(
    tmp_path: Path, seed_dict: SeedDict, offset: int
) -> None:
    seed_dict["patient_assessments"][0]["day_offset"] = offset
    seed = load_seed_file(_write(tmp_path, seed_dict))
    with pytest.raises(DemoDateRangeError):
        check_demo_date_range(seed, date(2026, 12, 5))


def test_check_demo_date_range_demo_day_passes(real_seed: DemoSeed) -> None:
    check_demo_date_range(real_seed, date(2026, 12, 5))


def test_check_demo_date_range_birth_year_below_one_raises(real_seed: DemoSeed) -> None:
    max_age = max(p.age_at_d0 for p in real_seed.patients)
    with pytest.raises(DemoDateRangeError):
        check_demo_date_range(real_seed, date(max_age, 6, 1))
    check_demo_date_range(real_seed, date(max_age + 1, 6, 1))


# --- 오류 클래스 ---------------------------------------------------------------


def test_reset_cleanup_error_keeps_failures() -> None:
    err = ResetCleanupError(("checkpoints.db", "photos"))
    assert err.failures == ("checkpoints.db", "photos")
    assert "checkpoints.db" in str(err)


@pytest.mark.parametrize(
    "error_class",
    [SeedError, StoragePrepareError, StorageReplaceError, ResetBusyError, AppLockedError],
)
def test_storage_errors_are_plain_exceptions(error_class: type[Exception]) -> None:
    assert issubclass(error_class, Exception)
    assert not issubclass(error_class, ConfigError)
