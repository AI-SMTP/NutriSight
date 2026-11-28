"""환자 목록·요약·섭취 기간 조회 서비스 (스펙 3.3 응답 모델, 3.8 일별 섭취·자주 남긴 메뉴 규칙).

모든 함수는 동기 함수이고 첫 인자로 `connect()`가 연 연결을 받는다. 읽기만 한다(`daily_intakes`에
계산 행을 쓰지 않는다). 화면 기준일은 매 호출 `seed_meta.demo_date`에서 읽고 서버 시각을 쓰지
않는다. `bmi`·`weight_change_30d.pct`는 반올림하지 않는다(표시 자리수는 화면 몫).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta

from app.nutrition.types import (
    AlertLevel,
    AlertResult,
    DailyIntake,
    DailyTarget,
    MealRecord,
    Nutrient,
    NutritionEngine,
    PatientProfile,
    Sex,
    TargetRecord,
    TargetSource,
    WeightRecord,
)
from app.services.ports import IntakeSummary, LeftMenu, PatientNotFoundError
from app.storage import queries
from app.storage.recommendations import list_prescriptions
from app.storage.records import (
    AlertRow,
    AssessmentRow,
    DailyIntakeRow,
    MealOrder,
    Patient,
    PatientHistory,
    WeightRow,
)

WEIGHT_CHANGE_WINDOW_DAYS = 30
LEFT_MENU_MAX_COUNT = 5
LEFT_MENU_MIN_MEALS = 2
LEFT_MENU_MAX_AVG_FRACTION = 0.5
_CM_PER_M = 100.0
_PCT_SCALE = 100.0
_BASIS_PERIOD_SEPARATOR = "~"


@dataclass(frozen=True)
class PatientListEntry:
    """환자 목록 한 줄. 판정이 없으면 `alert_level`은 None이다."""

    patient_id: str
    display_name: str
    room: str | None
    alert_level: AlertLevel | None
    alert_nutrients: tuple[Nutrient, ...]


@dataclass(frozen=True)
class WeightChange:
    """30일 체중 변화. `pct`는 기준 측정값 대비 백분율(반올림 없음)."""

    kg: float
    pct: float


@dataclass(frozen=True)
class TargetView:
    """시연일 목표. `effective_from`은 `team_set`일 때 적용 시작일, 아니면 None."""

    energy_kcal: float
    protein_g: float
    source: TargetSource
    effective_from: date | None


@dataclass(frozen=True)
class PatientDetailView:
    """환자 요약 (`PatientDetail`)."""

    patient_id: str
    display_name: str
    room: str | None
    sex: Sex
    age: int
    height_cm: float | None
    conditions: tuple[str, ...]
    diet_restrictions: str
    ckd_dialysis: str
    latest_weight: WeightRow | None
    weight_change_30d: WeightChange | None
    bmi: float | None
    target: TargetView
    assessments: tuple[AssessmentRow, ...]  # kind별 최신 한 건, kind 순


@dataclass(frozen=True)
class PrescriptionMark:
    """섭취 추이에 표시할 처방 확정 시점. `confirmed_at`은 저장 문자열 그대로다."""

    prescription_id: str
    confirmed_at: str


@dataclass(frozen=True)
class IntakeTrendView:
    """시연일을 끝으로 하는 섭취 추이 (`IntakeTrend`)."""

    patient_id: str
    period_start: date
    period_end: date
    days: tuple[DailyIntake, ...]
    prescriptions: tuple[PrescriptionMark, ...]  # confirmed_at 오름차순


# 공통 ----------------------------------------------------------------------


def _require_patient(conn: sqlite3.Connection, patient_id: str) -> Patient:
    patient = queries.get_patient(conn, patient_id)
    if patient is None:
        raise PatientNotFoundError(f"환자가 없다: {patient_id}")
    return patient


def _period_start(days: int, end: date) -> date:
    if days < 1:
        raise ValueError("days는 1 이상이어야 한다")
    return end - timedelta(days=days - 1)


def _engine_inputs(
    patient: Patient, history: PatientHistory
) -> tuple[PatientProfile, tuple[TargetRecord, ...], tuple[WeightRecord, ...]]:
    """`engine.daily_target`에 넘길 프로필과 날짜 오름차순 목표·체중 이력."""
    profile = PatientProfile(sex=patient.sex, birth_year=patient.birth_year)
    targets = tuple(
        TargetRecord(
            effective_from=t.effective_from,
            energy_kcal=t.energy_kcal,
            protein_g=t.protein_g,
            source=t.source,
        )
        for t in history.targets
    )
    weights = tuple(
        WeightRecord(measured_on=w.measured_on, weight_kg=w.weight_kg) for w in history.weights
    )
    return profile, targets, weights


def _meal_record(order: MealOrder) -> MealRecord:
    return MealRecord(
        meal=order.meal,
        order_status=order.order_status,
        record_status=order.record_status,
        energy_kcal_est=order.energy_kcal_est,
        protein_g_est=order.protein_g_est,
    )


def _stored_intake(row: DailyIntakeRow, target: DailyTarget) -> DailyIntake:
    return DailyIntake(
        on=row.on,
        energy_kcal=row.energy_kcal,
        protein_g=row.protein_g,
        energy_pct=row.energy_pct,
        protein_pct=row.protein_pct,
        recorded_meals=row.recorded_meals,
        unrecorded_meals=row.unrecorded_meals,
        npo_meals=row.npo_meals,
        target=target,
    )


# 일별 섭취·자주 남긴 메뉴·요약 -------------------------------------------------


def daily_rows(
    conn: sqlite3.Connection, engine: NutritionEngine, patient_id: str, start: date, end: date
) -> tuple[DailyIntake, ...]:
    """기간 안 발주가 있는 날의 일별 섭취, 오래된 날부터 (스펙 3.8 일별 섭취 규칙).

    저장된 `daily_intakes` 행이 있으면 그 값, 없으면 그날 발주로 엔진이 계산한 값(저장하지
    않음)이다. 발주가 없는 날은 저장 행이 있어도 뺀다. 목표는 그날 `engine.daily_target`이다.
    환자 없음 → `PatientNotFoundError`.
    """
    return _daily_rows(conn, engine, _require_patient(conn, patient_id), start, end)


def _daily_rows(
    conn: sqlite3.Connection, engine: NutritionEngine, patient: Patient, start: date, end: date
) -> tuple[DailyIntake, ...]:
    patient_id = patient.patient_id
    profile, targets, weights = _engine_inputs(
        patient, queries.get_patient_history(conn, patient_id)
    )
    stored = {row.on: row for row in queries.list_daily_intakes(conn, patient_id, start, end)}
    orders_by_day: dict[date, list[MealOrder]] = {}
    for order in queries.list_meal_orders(conn, patient_id, start, end):
        orders_by_day.setdefault(order.on, []).append(order)

    result: list[DailyIntake] = []
    # 발주가 있는 날만 돈다. 발주 없는 날의 저장 행(`stored`)은 쓰지 않는다.
    for day in sorted(orders_by_day):
        target = engine.daily_target(profile, targets, weights, day)
        row = stored.get(day)
        if row is not None:
            result.append(_stored_intake(row, target))
        else:
            meals = tuple(_meal_record(order) for order in orders_by_day[day])
            result.append(engine.daily_intake(day, meals, target))
    return tuple(result)


def left_menus(
    conn: sqlite3.Connection, patient_id: str, start: date, end: date
) -> tuple[LeftMenu, ...]:
    """기간 안 자주 남긴 메뉴 최대 5개 (스펙 3.8 자주 남긴 메뉴 규칙)."""
    return queries.list_left_menu_candidates(
        conn,
        patient_id,
        start,
        end,
        min_meals=LEFT_MENU_MIN_MEALS,
        max_avg_fraction=LEFT_MENU_MAX_AVG_FRACTION,
        limit=LEFT_MENU_MAX_COUNT,
    )


def latest_alert(conn: sqlite3.Connection, patient_id: str, on: date) -> AlertRow | None:
    """판정일이 `on` 이하인 판정 중 가장 최근 것(`evaluated_at`, 같으면 `alert_id` 큰 것)."""
    return queries.get_latest_alert(conn, patient_id, on)


def alert_to_result(row: AlertRow) -> AlertResult:
    """저장된 판정 행을 `AlertResult`로. `basis_period`가 없으면 기간은 None이다."""
    period_start: date | None = None
    period_end: date | None = None
    if row.basis_period is not None:
        start_text, end_text = row.basis_period.split(_BASIS_PERIOD_SEPARATOR)
        period_start, period_end = date.fromisoformat(start_text), date.fromisoformat(end_text)
    return AlertResult(
        level=row.level,
        nutrients=row.nutrients,
        period_start=period_start,
        period_end=period_end,
        evidence=row.basis_values,
        unrecorded_meals=row.unrecorded_meals,
    )


def intake_summary(
    conn: sqlite3.Connection, engine: NutritionEngine, patient_id: str, days: int, on: date
) -> IntakeSummary:
    """`on - (days - 1)` ~ `on` 섭취 요약 (포트 `get_intake_summary`).

    환자 없음 → `PatientNotFoundError`, `days < 1` → `ValueError`.
    """
    patient = _require_patient(conn, patient_id)
    start = _period_start(days, on)
    alert = latest_alert(conn, patient_id, on)
    return IntakeSummary(
        patient_id=patient_id,
        period_start=start,
        period_end=on,
        daily=_daily_rows(conn, engine, patient, start, on),
        alert=None if alert is None else alert_to_result(alert),
        frequently_left_menus=left_menus(conn, patient_id, start, on),
    )


# 화면 조회 -----------------------------------------------------------------


def list_patients_with_alert(conn: sqlite3.Connection) -> tuple[PatientListEntry, ...]:
    """모든 환자와 시연일 이하 최신 판정 수준, `patient_id` 순."""
    on = queries.get_demo_date(conn)
    entries: list[PatientListEntry] = []
    for patient in queries.list_patients(conn):
        alert = latest_alert(conn, patient.patient_id, on)
        entries.append(
            PatientListEntry(
                patient_id=patient.patient_id,
                display_name=patient.display_name,
                room=patient.room,
                alert_level=None if alert is None else alert.level,
                alert_nutrients=() if alert is None else alert.nutrients,
            )
        )
    return tuple(entries)


def _weight_change(weights: tuple[WeightRow, ...], on: date) -> WeightChange | None:
    """시연일-30일 이전(포함) 가장 가까운 측정과 최근 측정의 차이. 하나라도 없으면 None."""
    cutoff = on - timedelta(days=WEIGHT_CHANGE_WINDOW_DAYS)
    baselines = [w for w in weights if w.measured_on <= cutoff]
    if not baselines:
        return None
    baseline, latest = baselines[-1], weights[-1]
    kg = latest.weight_kg - baseline.weight_kg
    return WeightChange(kg=kg, pct=kg / baseline.weight_kg * _PCT_SCALE)


def _bmi(latest: WeightRow | None, height_cm: float | None) -> float | None:
    if latest is None or height_cm is None:
        return None
    return latest.weight_kg / (height_cm / _CM_PER_M) ** 2


def _target_view(target: DailyTarget, history: PatientHistory, on: date) -> TargetView:
    effective_from: date | None = None
    if target.source == TargetSource.TEAM_SET:
        effective_from = next(
            (
                t.effective_from
                for t in reversed(history.targets)
                if t.source == TargetSource.TEAM_SET and t.effective_from <= on
            ),
            None,
        )
    return TargetView(target.energy_kcal, target.protein_g, target.source, effective_from)


def _latest_assessments(history: PatientHistory, on: date) -> tuple[AssessmentRow, ...]:
    """`kind`별 시연일 이하 최신 평가, `kind` 순. 이력은 날짜 오름차순이라 뒤 값이 이긴다."""
    latest = {a.kind: a for a in history.assessments if a.assessed_on <= on}
    return tuple(latest[kind] for kind in sorted(latest))


def patient_detail(
    conn: sqlite3.Connection, engine: NutritionEngine, patient_id: str
) -> PatientDetailView:
    """환자 요약. 기준일은 시연일이고, 시연일 뒤 측정·평가는 쓰지 않는다."""
    on = queries.get_demo_date(conn)
    patient = _require_patient(conn, patient_id)
    history = queries.get_patient_history(conn, patient_id)
    weights = tuple(w for w in history.weights if w.measured_on <= on)
    latest_weight = weights[-1] if weights else None
    target = engine.daily_target(*_engine_inputs(patient, history), on)
    return PatientDetailView(
        patient_id=patient.patient_id,
        display_name=patient.display_name,
        room=patient.room,
        sex=patient.sex,
        age=on.year - patient.birth_year,
        height_cm=patient.height_cm,
        conditions=patient.conditions,
        diet_restrictions=patient.diet_restrictions,
        ckd_dialysis=patient.ckd_dialysis,
        latest_weight=latest_weight,
        weight_change_30d=_weight_change(weights, on),
        bmi=_bmi(latest_weight, patient.height_cm),
        target=_target_view(target, history, on),
        assessments=_latest_assessments(history, on),
    )


def intake_trend(
    conn: sqlite3.Connection, engine: NutritionEngine, patient_id: str, days: int
) -> IntakeTrendView:
    """시연일을 끝으로 하는 `days`일 섭취 추이와 기간 안 처방 확정 시점.

    환자 없음 → `PatientNotFoundError`, `days < 1` → `ValueError`(1~60 범위는 API가 검증).
    """
    patient = _require_patient(conn, patient_id)
    end = queries.get_demo_date(conn)
    start = _period_start(days, end)
    marks = tuple(
        sorted(
            (
                PrescriptionMark(p.prescription_id, p.confirmed_at)
                for p in list_prescriptions(conn, patient_id)
                if start <= date.fromisoformat(p.confirmed_at[:10]) <= end
            ),
            key=lambda mark: (mark.confirmed_at, mark.prescription_id),
        )
    )
    return IntakeTrendView(
        patient_id=patient_id,
        period_start=start,
        period_end=end,
        days=_daily_rows(conn, engine, patient, start, end),
        prescriptions=marks,
    )
