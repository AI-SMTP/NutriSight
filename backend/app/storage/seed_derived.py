"""시드 적재 때 파생 테이블 값을 `NutritionEngine`으로 계산한다 (스펙 3.7 파생 테이블).

환자별로 관찰 시작일(`observation_start_offset`)부터 D-1까지 각 날짜 `d`에 대해 하루 목표 →
일별 섭취 → 그날까지 이력으로 경고를 계산한다. D0은 계산하지 않는다(T3이 끼니 기록 때 만든다).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta

from app.nutrition.types import (
    AlertResult,
    AlertRules,
    DailyIntake,
    MealRecord,
    NutritionEngine,
    PatientProfile,
    TargetRecord,
    WeightRecord,
)
from app.storage.seed_models import DemoSeed, SeedPatient

# (환자, 날짜) → 그날 발주를 끼니 순으로 바꾼 `MealRecord`
MealsByPatientDay = Mapping[tuple[str, date], tuple[MealRecord, ...]]


@dataclass(frozen=True)
class PatientDay:
    """환자 한 명의 판정일 하루 결과. `day`는 엔진 반환값이 아니라 계산을 요청한 날짜다."""

    patient_id: str
    day: date
    intake: DailyIntake
    alert: AlertResult


def evaluate_patients(
    seed: DemoSeed, demo_date: date, engine: NutritionEngine, meals: MealsByPatientDay
) -> tuple[PatientDay, ...]:
    """모든 환자의 판정일별 결과, 환자 순 → 날짜 오름차순. 발주가 없는 날은 끼니 0개다."""
    return tuple(
        result
        for patient in seed.patients
        for result in _evaluate_patient(seed, patient, demo_date, engine, meals)
    )


def _evaluate_patient(
    seed: DemoSeed,
    patient: SeedPatient,
    demo_date: date,
    engine: NutritionEngine,
    meals: MealsByPatientDay,
) -> tuple[PatientDay, ...]:
    pid = patient.patient_id
    profile, targets, weights = _engine_inputs(seed, patient, demo_date)
    history: tuple[DailyIntake, ...] = ()
    results: tuple[PatientDay, ...] = ()
    for offset in range(patient.observation_start_offset, 0):
        day = demo_date + timedelta(days=offset)
        target = engine.daily_target(profile, targets, weights, on=day)
        intake = engine.daily_intake(day, meals.get((pid, day), ()), target)
        history = (*history, intake)
        alert = engine.evaluate_alert(history, AlertRules(), on=day)
        results = (*results, PatientDay(pid, day, intake, alert))
    return results


def _engine_inputs(
    seed: DemoSeed, patient: SeedPatient, demo_date: date
) -> tuple[PatientProfile, tuple[TargetRecord, ...], tuple[WeightRecord, ...]]:
    """환자의 프로필과 날짜 오름차순 목표·체중 이력."""
    pid = patient.patient_id
    targets = (
        TargetRecord(
            effective_from=demo_date + timedelta(days=t.effective_from_offset),
            energy_kcal=t.energy_kcal,
            protein_g=t.protein_g,
            source=t.source,
        )
        for t in seed.patient_targets
        if t.patient_id == pid
    )
    weights = (
        WeightRecord(measured_on=demo_date + timedelta(days=w.day_offset), weight_kg=w.weight_kg)
        for w in seed.patient_weights
        if w.patient_id == pid
    )
    return (
        PatientProfile(sex=patient.sex, birth_year=demo_date.year - patient.age_at_d0),
        tuple(sorted(targets, key=lambda t: t.effective_from)),
        tuple(sorted(weights, key=lambda w: w.measured_on)),
    )
