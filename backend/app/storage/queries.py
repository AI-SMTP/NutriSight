"""시드 대상 조회 함수 (스펙 3.5).

`demo_timestamp`를 뺀 모든 함수는 첫 인자로 `connect()`가 연 연결(`row_factory=sqlite3.Row`)을
받는다. 기간 인자 `start`·`end`는 양 끝을 포함한다. 컬렉션은 `tuple`로 돌려준다.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime

from app.intake.types import SlotStatus
from app.nutrition.types import (
    AlertLevel,
    MealType,
    OrderStatus,
    RecordStatus,
    Sex,
    TargetSource,
)
from app.services.ports import LeftMenu
from app.storage.codec import (
    evidence_from_json,
    nutrients_from_json,
    quality_issues_from_json,
    strings_from_json,
)
from app.storage.records import (
    AlertRow,
    AssessmentRow,
    DailyIntakeRow,
    MealOrder,
    MealPlan,
    MealPlanSlot,
    Patient,
    PatientHistory,
    SlotIntakeRow,
    TargetRow,
    WeightRow,
)

# 끼니 정렬 키. 문자열 순서(breakfast < dinner < lunch)가 아니라 하루 순서로 정렬한다.
_MEAL_ORDER_SQL = "CASE p.meal WHEN 'breakfast' THEN 0 WHEN 'lunch' THEN 1 ELSE 2 END"


def get_demo_date(conn: sqlite3.Connection) -> date:
    """`seed_meta.demo_date`를 읽는다. 행이 없으면 `LookupError`."""
    row = conn.execute("SELECT value FROM seed_meta WHERE key = 'demo_date'").fetchone()
    if row is None or row["value"] is None:
        raise LookupError("seed_meta에 demo_date가 없다")
    return date.fromisoformat(row["value"])


def demo_timestamp(demo_date: date, now: datetime) -> str:
    """시연일 날짜와 실제 시각의 시:분:초를 합친 `YYYY-MM-DDTHH:MM:SS` (DB를 읽지 않는다)."""
    return f"{demo_date.isoformat()}T{now.strftime('%H:%M:%S')}"


# 환자 ----------------------------------------------------------------------


def _patient(row: sqlite3.Row) -> Patient:
    return Patient(
        patient_id=row["patient_id"],
        display_name=row["display_name"],
        room=row["room"],
        sex=Sex(row["sex"]),
        birth_year=row["birth_year"],
        height_cm=row["height_cm"],
        default_diet_type=row["default_diet_type"],
        conditions=strings_from_json(row["conditions"]),
        diet_restrictions=row["diet_restrictions"],
        ckd_dialysis=row["ckd_dialysis"],
        observation_start=date.fromisoformat(row["observation_start"]),
        data_source=row["data_source"],
    )


def list_patients(conn: sqlite3.Connection) -> tuple[Patient, ...]:
    """모든 환자, `patient_id` 순."""
    rows = conn.execute("SELECT * FROM patients ORDER BY patient_id").fetchall()
    return tuple(_patient(row) for row in rows)


def get_patient(conn: sqlite3.Connection, patient_id: str) -> Patient | None:
    """환자 한 명. 없으면 None."""
    row = conn.execute("SELECT * FROM patients WHERE patient_id = ?", (patient_id,)).fetchone()
    return None if row is None else _patient(row)


def get_patient_history(conn: sqlite3.Connection, patient_id: str) -> PatientHistory:
    """체중·목표·평가 이력, 각각 날짜 오름차순. 없는 환자는 빈 이력이다."""
    weights = conn.execute(
        "SELECT measured_on, weight_kg FROM patient_weights "
        "WHERE patient_id = ? ORDER BY measured_on",
        (patient_id,),
    ).fetchall()
    targets = conn.execute(
        "SELECT effective_from, energy_kcal, protein_g, source, note FROM patient_targets "
        "WHERE patient_id = ? ORDER BY effective_from",
        (patient_id,),
    ).fetchall()
    assessments = conn.execute(
        "SELECT assessed_on, kind, result, score, note FROM patient_assessments "
        "WHERE patient_id = ? ORDER BY assessed_on, kind",
        (patient_id,),
    ).fetchall()
    return PatientHistory(
        patient_id=patient_id,
        weights=tuple(
            WeightRow(measured_on=date.fromisoformat(r["measured_on"]), weight_kg=r["weight_kg"])
            for r in weights
        ),
        targets=tuple(
            TargetRow(
                effective_from=date.fromisoformat(r["effective_from"]),
                energy_kcal=r["energy_kcal"],
                protein_g=r["protein_g"],
                source=TargetSource(r["source"]),
                note=r["note"],
            )
            for r in targets
        ),
        assessments=tuple(
            AssessmentRow(
                assessed_on=date.fromisoformat(r["assessed_on"]),
                kind=r["kind"],
                result=r["result"],
                score=r["score"],
                note=r["note"],
            )
            for r in assessments
        ),
    )


# 배식 계획 -----------------------------------------------------------------


def get_meal_plan(
    conn: sqlite3.Connection, on: date, meal: MealType, diet_type: str = "general"
) -> MealPlan | None:
    """날짜·끼니·식사 종류의 배식 계획과 칸(`slot_id` 순). 없으면 None."""
    plan = conn.execute(
        "SELECT * FROM meal_plans WHERE date = ? AND meal = ? AND diet_type = ?",
        (on.isoformat(), str(meal), diet_type),
    ).fetchone()
    if plan is None:
        return None
    slots = conn.execute(
        "SELECT * FROM meal_plan_slots WHERE meal_plan_id = ? ORDER BY slot_id",
        (plan["meal_plan_id"],),
    ).fetchall()
    return MealPlan(
        meal_plan_id=plan["meal_plan_id"],
        on=date.fromisoformat(plan["date"]),
        meal=MealType(plan["meal"]),
        diet_type=plan["diet_type"],
        baseline_photo_id=plan["baseline_photo_id"],
        slots=tuple(
            MealPlanSlot(
                slot_id=s["slot_id"],
                position=s["position"],
                dish_type=s["dish_type"],
                menu_name=s["menu_name"],
                served_g=s["served_g"],
                energy_kcal=s["energy_kcal"],
                protein_g=s["protein_g"],
            )
            for s in slots
        ),
    )


# 발주 ----------------------------------------------------------------------


def _slot_intakes_by_order(
    conn: sqlite3.Connection, patient_id: str, start: str, end: str
) -> dict[str, tuple[SlotIntakeRow, ...]]:
    """기간 안 환자 발주의 칸별 섭취를 발주 ID별로(`slot_id` 순) 묶는다."""
    rows = conn.execute(
        "SELECT i.* FROM slot_intakes AS i "
        "JOIN meal_orders AS o ON o.meal_order_id = i.meal_order_id "
        "JOIN meal_plans AS p ON p.meal_plan_id = o.meal_plan_id "
        "WHERE o.patient_id = ? AND p.date BETWEEN ? AND ? "
        "ORDER BY i.meal_order_id, i.slot_id",
        (patient_id, start, end),
    ).fetchall()
    grouped: dict[str, list[SlotIntakeRow]] = {}
    for r in rows:
        grouped.setdefault(r["meal_order_id"], []).append(
            SlotIntakeRow(
                slot_id=r["slot_id"],
                intake_fraction_est=r["intake_fraction_est"],
                status=SlotStatus(r["status"]),
                quality_issues=quality_issues_from_json(r["quality_issues"]),
                estimate_basis=r["estimate_basis"],
            )
        )
    return {order_id: tuple(items) for order_id, items in grouped.items()}


def list_meal_orders(
    conn: sqlite3.Connection, patient_id: str, start: date, end: date
) -> tuple[MealOrder, ...]:
    """기간 안 환자의 발주, 날짜·끼니(아침→점심→저녁) 순. 칸별 섭취를 포함한다."""
    period = (start.isoformat(), end.isoformat())
    rows = conn.execute(
        "SELECT o.*, p.date AS plan_date, p.meal AS plan_meal "
        "FROM meal_orders AS o JOIN meal_plans AS p ON p.meal_plan_id = o.meal_plan_id "
        "WHERE o.patient_id = ? AND p.date BETWEEN ? AND ? "
        f"ORDER BY p.date, {_MEAL_ORDER_SQL}, o.meal_order_id",
        (patient_id, *period),
    ).fetchall()
    intakes = _slot_intakes_by_order(conn, patient_id, *period)
    return tuple(
        MealOrder(
            meal_order_id=r["meal_order_id"],
            patient_id=r["patient_id"],
            meal_plan_id=r["meal_plan_id"],
            on=date.fromisoformat(r["plan_date"]),
            meal=MealType(r["plan_meal"]),
            diet_category=r["diet_category"],
            diet_code=r["diet_code"],
            order_status=OrderStatus(r["order_status"]),
            order_from=r["order_from"],
            order_note=r["order_note"],
            record_status=RecordStatus(r["record_status"]),
            post_photo_id=r["post_photo_id"],
            staff_zero_reason=r["staff_zero_reason"],
            energy_kcal_est=r["energy_kcal_est"],
            protein_g_est=r["protein_g_est"],
            incomplete=bool(r["incomplete"]),
            data_source=r["data_source"],
            slot_intakes=intakes.get(r["meal_order_id"], ()),
        )
        for r in rows
    )


# 일별 섭취·경고 ------------------------------------------------------------


def list_daily_intakes(
    conn: sqlite3.Connection, patient_id: str, start: date, end: date
) -> tuple[DailyIntakeRow, ...]:
    """기간 안 환자의 일별 섭취, 날짜 오름차순. NULL 섭취량은 None이다."""
    rows = conn.execute(
        "SELECT * FROM daily_intakes WHERE patient_id = ? AND date BETWEEN ? AND ? ORDER BY date",
        (patient_id, start.isoformat(), end.isoformat()),
    ).fetchall()
    return tuple(
        DailyIntakeRow(
            patient_id=r["patient_id"],
            on=date.fromisoformat(r["date"]),
            energy_kcal=r["energy_kcal"],
            protein_g=r["protein_g"],
            energy_pct=r["energy_pct"],
            protein_pct=r["protein_pct"],
            recorded_meals=r["recorded_meals"],
            unrecorded_meals=r["unrecorded_meals"],
            npo_meals=r["npo_meals"],
        )
        for r in rows
    )


def _alert(r: sqlite3.Row) -> AlertRow:
    return AlertRow(
        alert_id=r["alert_id"],
        patient_id=r["patient_id"],
        evaluated_at=r["evaluated_at"],
        level=AlertLevel(r["level"]),
        basis_period=r["basis_period"],
        basis_values=evidence_from_json(r["basis_values"]),
        nutrients=nutrients_from_json(r["nutrients"]),
        unrecorded_meals=r["unrecorded_meals"],
    )


def list_alerts(
    conn: sqlite3.Connection, patient_id: str, start: date, end: date
) -> tuple[AlertRow, ...]:
    """판정일(`evaluated_at`의 날짜 부분)이 기간 안인 경고, `evaluated_at`·`alert_id` 오름차순."""
    rows = conn.execute(
        "SELECT * FROM alerts WHERE patient_id = ? AND substr(evaluated_at, 1, 10) BETWEEN ? AND ? "
        "ORDER BY evaluated_at, alert_id",
        (patient_id, start.isoformat(), end.isoformat()),
    ).fetchall()
    return tuple(_alert(r) for r in rows)


def get_latest_alert(conn: sqlite3.Connection, patient_id: str, on: date) -> AlertRow | None:
    """판정일이 `on` 이하인 경고 중 최신 한 건(`evaluated_at`, 같으면 `alert_id`가 큰 것).

    없으면 None.
    """
    row = conn.execute(
        "SELECT * FROM alerts WHERE patient_id = ? AND substr(evaluated_at, 1, 10) <= ? "
        "ORDER BY evaluated_at DESC, alert_id DESC LIMIT 1",
        (patient_id, on.isoformat()),
    ).fetchone()
    return None if row is None else _alert(row)


def get_alert(conn: sqlite3.Connection, patient_id: str, alert_id: str) -> AlertRow | None:
    """그 환자의 판정 `alert_id`. 없거나 다른 환자의 판정이면 None."""
    row = conn.execute(
        "SELECT * FROM alerts WHERE alert_id = ? AND patient_id = ?", (alert_id, patient_id)
    ).fetchone()
    return None if row is None else _alert(row)


# 자주 남긴 메뉴 ----------------------------------------------------------------

# 전량 거부·미섭취(`staff`)는 메뉴 선호가 아니라 뺀다. 끼니 수는 발주 수로 센다(한 끼니에 같은
# 메뉴 칸이 둘이면 1끼). 평균은 칸 섭취 비율의 평균이다.
_LEFT_MENU_SQL = """
SELECT s.menu_name, s.dish_type,
       AVG(i.intake_fraction_est) AS avg_fraction,
       COUNT(DISTINCT i.meal_order_id) AS meal_count
FROM slot_intakes AS i
JOIN meal_orders AS o ON o.meal_order_id = i.meal_order_id
JOIN meal_plans AS p ON p.meal_plan_id = o.meal_plan_id
JOIN meal_plan_slots AS s ON s.meal_plan_id = p.meal_plan_id AND s.slot_id = i.slot_id
WHERE o.patient_id = ? AND p.date BETWEEN ? AND ?
  AND o.record_status = ?
  AND i.intake_fraction_est IS NOT NULL
  -- 스키마가 막지만 방어로 둔다: 칸별 섭취는 trg_slot_intakes_slot_insert·_update 트리거로
  -- 배식 칸(served_g > 0)만 가리키고, CHECK ((served_g = 0) = (menu_name IS NULL))로 배식 칸은
  -- menu_name이 있다.
  AND s.menu_name IS NOT NULL
  AND i.estimate_basis <> 'staff'
GROUP BY s.menu_name, s.dish_type
HAVING meal_count >= ? AND avg_fraction <= ?
ORDER BY avg_fraction ASC, meal_count DESC, s.menu_name ASC
LIMIT ?
"""


def list_left_menu_candidates(
    conn: sqlite3.Connection,
    patient_id: str,
    start: date,
    end: date,
    *,
    min_meals: int,
    max_avg_fraction: float,
    limit: int,
) -> tuple[LeftMenu, ...]:
    """기간 안 `recorded` 발주의 메뉴별 평균 섭취 비율과 끼니 수 (스펙 3.8 자주 남긴 메뉴 규칙).

    끼니 수 `min_meals` 이상·평균 `max_avg_fraction` 이하만, 평균 오름차순 → 끼니 수 내림차순 →
    `menu_name` 순으로 최대 `limit`개.
    """
    rows = conn.execute(
        _LEFT_MENU_SQL,
        (
            patient_id,
            start.isoformat(),
            end.isoformat(),
            str(RecordStatus.RECORDED),
            min_meals,
            max_avg_fraction,
            limit,
        ),
    ).fetchall()
    return tuple(
        LeftMenu(
            menu_name=r["menu_name"],
            dish_type=r["dish_type"],
            avg_intake_fraction=r["avg_fraction"],
            meal_count=r["meal_count"],
        )
        for r in rows
    )
