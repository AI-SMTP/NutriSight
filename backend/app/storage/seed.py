"""시드 파일 읽기·검증과 시연일 범위 검사 (스펙 3.7, 3.8 1단계).

오류 경계:
- 파일 읽기의 `OSError`(없음·권한·I/O) → `StoragePrepareError`
- JSON 문법·인코딩 오류, Pydantic 형태 오류, 적재 전 관계 검증 실패 → `SeedError`
- 시연일과 시드 오프셋 조합이 날짜 범위를 벗어남 → `DemoDateRangeError`(`ConfigError` 계열)

관계 검증은 검증을 통과한 시드를 적재할 때 PRIMARY KEY·UNIQUE·외래 키·칸 트리거에
걸리지 않도록, 적재 뒤 키(날짜로 바꾼 ID 포함) 기준으로 확인한다.
"""

from __future__ import annotations

import json
from collections.abc import Hashable, Iterable
from datetime import MINYEAR, date, timedelta
from pathlib import Path

from pydantic import ValidationError

from app.storage.errors import DemoDateRangeError, SeedError, StoragePrepareError
from app.storage.seed_load import (
    CLEANUP_PENDING_KEY,
    SeedCounts,
    build_database,
    build_engine,
)
from app.storage.seed_models import DemoSeed, SeedMealOrder, SeedMealPlan
from app.storage.seed_reset import finish_cleanup

# 적재(`build_database`)는 `seed_load.py`에 두고, 시드 관련 진입점은 이 모듈에서 함께 내보낸다.
__all__ = [
    "CLEANUP_PENDING_KEY",
    "SeedCounts",
    "build_database",
    "build_engine",
    "check_demo_date_range",
    "finish_cleanup",
    "load_seed_file",
]

# 시연일 기준 출생 연도(`demo_date.year - age_at_d0`)의 최솟값.
MIN_BIRTH_YEAR = MINYEAR


def load_seed_file(path: Path) -> DemoSeed:
    """시드 파일을 읽어 형태와 관계를 검증한 `DemoSeed`를 돌려준다.

    파일을 읽지 못하면 `StoragePrepareError`, 내용이 잘못됐으면 `SeedError`를 던진다.
    """
    try:
        raw = path.read_bytes()
    except OSError as err:
        raise StoragePrepareError(f"시드 파일을 읽지 못했다: {path}") from err
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as err:
        raise SeedError(f"시드 파일이 올바른 UTF-8 JSON이 아니다: {path}: {err}") from err
    try:
        seed = DemoSeed.model_validate(data)
    except ValidationError as err:
        raise SeedError(f"시드 파일 형식이 잘못됐다: {path}\n{err}") from err
    _check_relations(seed)
    return seed


def check_demo_date_range(seed: DemoSeed, demo_date: date) -> None:
    """시연일에 시드의 모든 날짜 오프셋을 더해도 날짜 범위 안인지 확인한다.

    `demo_date + min(offset)`과 `demo_date + max(offset)`이 1~9999년 안이어야 하고,
    출생 연도 `demo_date.year - max(age_at_d0)`가 1 이상이어야 한다. 벗어나면
    `DemoDateRangeError`를 던지고 `OverflowError`는 밖으로 내보내지 않는다.
    """
    offsets = list(_all_offsets(seed))
    if offsets:
        low, high = min(offsets), max(offsets)
        if not (_shift_fits(demo_date, low) and _shift_fits(demo_date, high)):
            raise DemoDateRangeError(
                f"시연일 {demo_date.isoformat()}에 시드 날짜 오프셋({low}~{high}일)을 더하면 "
                "날짜 범위를 벗어난다"
            )
    if seed.patients:
        max_age = max(patient.age_at_d0 for patient in seed.patients)
        if demo_date.year - max_age < MIN_BIRTH_YEAR:
            raise DemoDateRangeError(
                f"시연일 {demo_date.isoformat()}에서 시드 나이(최대 {max_age}세)를 빼면 "
                f"출생 연도가 {MIN_BIRTH_YEAR}보다 작다"
            )


def _shift_fits(base: date, offset_days: int) -> bool:
    """`base + offset_days일`이 `date`가 표현하는 범위(1~9999년) 안이면 True.

    범위를 벗어나면 `timedelta` 생성이나 덧셈이 `OverflowError`를 낸다.
    """
    try:
        base + timedelta(days=offset_days)
    except OverflowError:
        return False
    return True


def _all_offsets(seed: DemoSeed) -> Iterable[int]:
    """시드의 모든 `*_offset` 값. 적재 때 날짜로 바뀌는 값 전부다."""
    yield from (p.observation_start_offset for p in seed.patients)
    yield from (w.day_offset for w in seed.patient_weights)
    yield from (t.effective_from_offset for t in seed.patient_targets)
    yield from (a.day_offset for a in seed.patient_assessments)
    yield from (plan.day_offset for plan in seed.meal_plans)
    yield from (o.order_from_offset for o in seed.meal_orders if o.order_from_offset is not None)


# --- 관계 검증 -----------------------------------------------------------------


def _check_relations(seed: DemoSeed) -> None:
    """ID 중복, 참조 대상 존재, 칸별 섭취의 칸을 검증한다. 실패하면 `SeedError`."""
    patient_ids = _unique_keys("patients", ((p.patient_id, p.patient_id) for p in seed.patients))
    _check_history(seed, patient_ids)
    plans = _check_plans(seed.meal_plans)
    _check_orders(seed.meal_orders, patient_ids, plans)
    _check_no_photos(seed)


def _check_no_photos(seed: DemoSeed) -> None:
    """시드에는 사진이 없으므로 사진 ID는 모두 null이어야 한다(사진 외래 키가 COMMIT에서 실패)."""
    for plan in seed.meal_plans:
        if plan.baseline_photo_id is not None:
            raise SeedError(
                f"meal_plans: {plan.meal_plan_id}의 baseline_photo_id는 시드에서 null이어야 한다"
            )
    for order in seed.meal_orders:
        if order.post_photo_id is not None:
            raise SeedError(
                f"meal_orders: {order.meal_order_id}의 post_photo_id는 시드에서 null이어야 한다"
            )


def _unique_keys[K: Hashable](table: str, items: Iterable[tuple[K, str]]) -> set[K]:
    """(키, 메시지에 쓸 ID) 목록에서 키가 겹치면 `SeedError`를 던지고 키 집합을 돌려준다."""
    seen: set[K] = set()
    for key, label in items:
        if key in seen:
            raise SeedError(f"{table}: 키가 중복된다: {label} ({_format_key(key)})")
        seen.add(key)
    return seen


def _format_key(key: Hashable) -> str:
    """메시지용 키 표기. 튜플은 값만 쉼표로 잇고, 열거값은 원래 문자열로 쓴다."""
    parts = key if isinstance(key, tuple) else (key,)
    return ", ".join(str(part) for part in parts)


def _require_patient(table: str, patient_id: str, patient_ids: set[str]) -> None:
    if patient_id not in patient_ids:
        raise SeedError(f"{table}: 없는 환자 {patient_id}를 가리킨다")


def _check_history(seed: DemoSeed, patient_ids: set[str]) -> None:
    """체중·목표·평가 이력의 환자 참조와 키 중복을 검증한다."""
    for w in seed.patient_weights:
        _require_patient("patient_weights", w.patient_id, patient_ids)
    for t in seed.patient_targets:
        _require_patient("patient_targets", t.patient_id, patient_ids)
    for a in seed.patient_assessments:
        _require_patient("patient_assessments", a.patient_id, patient_ids)
    _unique_keys(
        "patient_weights",
        (((w.patient_id, w.day_offset), w.patient_id) for w in seed.patient_weights),
    )
    _unique_keys(
        "patient_targets",
        (((t.patient_id, t.effective_from_offset), t.patient_id) for t in seed.patient_targets),
    )
    _unique_keys(
        "patient_assessments",
        (((a.patient_id, a.day_offset, a.kind), a.patient_id) for a in seed.patient_assessments),
    )


def _check_plans(plans: tuple[SeedMealPlan, ...]) -> dict[str, SeedMealPlan]:
    """배식 계획 ID·(날짜, 끼니, 식종) 중복과 계획 안 칸 중복을 검증한다."""
    _unique_keys("meal_plans", ((p.meal_plan_id, p.meal_plan_id) for p in plans))
    _unique_keys(
        "meal_plans", (((p.day_offset, p.meal, p.diet_type), p.meal_plan_id) for p in plans)
    )
    for plan in plans:
        _unique_keys("meal_plan_slots", ((s.slot_id, plan.meal_plan_id) for s in plan.slots))
    return {plan.meal_plan_id: plan for plan in plans}


def _check_orders(
    orders: tuple[SeedMealOrder, ...],
    patient_ids: set[str],
    plans: dict[str, SeedMealPlan],
) -> None:
    """발주 ID·참조·(환자, 계획)·(환자, 날짜, 끼니) 중복과 칸별 섭취를 검증한다."""
    _unique_keys("meal_orders", ((o.meal_order_id, o.meal_order_id) for o in orders))
    for order in orders:
        _require_patient(f"meal_orders: {order.meal_order_id}", order.patient_id, patient_ids)
        if order.meal_plan_id not in plans:
            raise SeedError(
                f"meal_orders: {order.meal_order_id}가 없는 배식 계획 "
                f"{order.meal_plan_id}를 가리킨다"
            )
        _check_slot_intakes(order, plans[order.meal_plan_id])
    _unique_keys("meal_orders", (((o.patient_id, o.meal_plan_id), o.meal_order_id) for o in orders))
    # 적재 때 발주 ID는 `<patient_id>_<날짜>_<meal>`이 되므로 이 조합도 겹치면 안 된다.
    _unique_keys(
        "meal_orders",
        (
            (
                (o.patient_id, plans[o.meal_plan_id].day_offset, plans[o.meal_plan_id].meal),
                o.meal_order_id,
            )
            for o in orders
        ),
    )


def _check_slot_intakes(order: SeedMealOrder, plan: SeedMealPlan) -> None:
    """칸별 섭취가 발주한 계획의 배식 칸만, 칸마다 한 번씩 가리키는지 검증한다."""
    slots = {slot.slot_id: slot for slot in plan.slots}
    _unique_keys("slot_intakes", ((i.slot_id, order.meal_order_id) for i in order.slot_intakes))
    for intake in order.slot_intakes:
        slot = slots.get(intake.slot_id)
        if slot is None:
            raise SeedError(
                f"slot_intakes: {order.meal_order_id}의 칸 {intake.slot_id}가 "
                f"배식 계획 {plan.meal_plan_id}에 없다"
            )
        if not slot.is_served:
            raise SeedError(
                f"slot_intakes: {order.meal_order_id}의 칸 {intake.slot_id}는 "
                f"배식 계획 {plan.meal_plan_id}의 미배식 칸이다"
            )
