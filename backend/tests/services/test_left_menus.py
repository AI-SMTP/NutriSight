"""자주 남긴 메뉴 집계 `left_menus` 테스트 (스펙 3.8 자주 남긴 메뉴 규칙).

빈 스키마에 끼니를 직접 넣어 대상 행·묶음·경계·정렬을 하나씩 확인한다.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import pytest

from app.services.patients import left_menus
from app.services.ports import LeftMenu
from app.storage.db import connect
from tests.storage.rows import (
    insert_meal_order,
    insert_meal_plan,
    insert_patient,
    insert_slot,
    insert_slot_intake,
)

PID = "NS07"
START = date(2026, 11, 23)
END = date(2026, 11, 29)


@dataclass(frozen=True)
class Dish:
    """끼니 한 칸: 메뉴와 그 칸의 섭취 비율."""

    menu_name: str
    fraction: float | None
    dish_type: str = "side"
    basis: str = "mock"


def _add_meal(
    conn: sqlite3.Connection,
    day: date,
    meal: str,
    dishes: Sequence[Dish],
    *,
    patient_id: str = PID,
    record_status: str = "recorded",
) -> None:
    """그날 끼니의 배식 계획(없으면 만든다)·발주·칸별 섭취를 넣는다. 칸 ID는 환자마다 따로 둔다."""
    plan_id = f"{day.isoformat()}_{meal}_general"
    exists = conn.execute("SELECT 1 FROM meal_plans WHERE meal_plan_id = ?", (plan_id,)).fetchone()
    if exists is None:
        insert_meal_plan(conn, meal_plan_id=plan_id, date=day.isoformat(), meal=meal)
    order_id = f"{patient_id}_{plan_id}"
    insert_meal_order(
        conn,
        meal_order_id=order_id,
        patient_id=patient_id,
        meal_plan_id=plan_id,
        record_status=record_status,
    )
    for index, dish in enumerate(dishes):
        slot_id = f"{patient_id}_slot_{index}"
        insert_slot(
            conn,
            meal_plan_id=plan_id,
            slot_id=slot_id,
            dish_type=dish.dish_type,
            menu_name=dish.menu_name,
        )
        insert_slot_intake(
            conn,
            meal_order_id=order_id,
            slot_id=slot_id,
            intake_fraction_est=dish.fraction,
            status="estimated" if dish.fraction is not None else "not_determinable",
            estimate_basis=dish.basis,
        )


def _day(offset: int) -> date:
    return START + timedelta(days=offset)


def _run(db_path: Path, meals: Sequence[tuple[int, str, Sequence[Dish]]]) -> tuple[LeftMenu, ...]:
    with connect(db_path) as conn:
        insert_patient(conn)
        for offset, meal, dishes in meals:
            _add_meal(conn, _day(offset), meal, dishes)
        return left_menus(conn, PID, START, END)


def test_left_menus_averages_by_menu_and_dish_type(db_path: Path) -> None:
    result = _run(
        db_path,
        [
            (0, "lunch", [Dish("시금치나물", 0.2), Dish("두부조림", 0.3, "main")]),
            (1, "lunch", [Dish("시금치나물", 0.4), Dish("두부조림", 0.1, "side")]),
        ],
    )

    # 같은 이름이라도 dish_type이 다르면 다른 묶음이고, 각각 끼니 1개라 빠진다.
    assert len(result) == 1
    assert result[0].menu_name == "시금치나물"
    assert result[0].dish_type == "side"
    assert result[0].avg_intake_fraction == pytest.approx(0.3)
    assert result[0].meal_count == 2


def test_left_menus_ignores_orders_that_are_not_recorded(db_path: Path) -> None:
    with connect(db_path) as conn:
        insert_patient(conn)
        _add_meal(conn, _day(0), "lunch", [Dish("미역국", 0.4, "soup")])
        _add_meal(conn, _day(1), "lunch", [Dish("미역국", 0.4, "soup")])
        _add_meal(conn, _day(2), "lunch", [Dish("미역국", 0.0, "soup")], record_status="pending")
        _add_meal(conn, _day(3), "lunch", [Dish("미역국", 0.0, "soup")], record_status="failed")
        result = left_menus(conn, PID, START, END)

    assert result == (LeftMenu("미역국", "soup", pytest.approx(0.4), 2),)


def test_left_menus_ignores_null_fraction(db_path: Path) -> None:
    result = _run(
        db_path,
        [
            (0, "lunch", [Dish("잡채", 0.2)]),
            (1, "lunch", [Dish("잡채", 0.4)]),
            (2, "lunch", [Dish("잡채", None)]),
        ],
    )

    assert result == (LeftMenu("잡채", "side", pytest.approx(0.3), 2),)


def test_left_menus_ignores_staff_estimates(db_path: Path) -> None:
    result = _run(
        db_path,
        [
            (0, "lunch", [Dish("잡채", 0.4)]),
            (1, "lunch", [Dish("잡채", 0.4, basis="vlm:fake")]),
            (2, "lunch", [Dish("잡채", 0.0, basis="staff")]),
            (3, "dinner", [Dish("잡채", 0.0, basis="staff")]),
        ],
    )

    assert result == (LeftMenu("잡채", "side", pytest.approx(0.4), 2),)


def test_left_menus_threshold_boundaries(db_path: Path) -> None:
    result = _run(
        db_path,
        [
            # 평균 0.5 정확히 → 포함
            (0, "lunch", [Dish("평균반", 0.4), Dish("평균초과", 0.5), Dish("한끼", 0.0)]),
            (1, "lunch", [Dish("평균반", 0.6), Dish("평균초과", 0.52)]),
        ],
    )

    assert [menu.menu_name for menu in result] == ["평균반"]
    assert result[0].avg_intake_fraction == pytest.approx(0.5)


def test_left_menus_counts_meals_not_slots(db_path: Path) -> None:
    result = _run(
        db_path,
        [
            # 한 끼니에 같은 메뉴 두 칸이어도 끼니는 1개다. 평균은 칸 비율의 평균이다.
            (0, "lunch", [Dish("깍두기", 0.2, "kimchi"), Dish("깍두기", 0.4, "kimchi")]),
            (1, "lunch", [Dish("깍두기", 0.3, "kimchi")]),
            (2, "lunch", [Dish("나물", 0.1), Dish("나물", 0.1)]),  # 끼니 1개 → 제외
        ],
    )

    assert result == (LeftMenu("깍두기", "kimchi", pytest.approx(0.3), 2),)


def test_left_menus_orders_by_avg_then_count_then_name(db_path: Path) -> None:
    result = _run(
        db_path,
        [
            (0, "breakfast", [Dish("다", 0.1), Dish("가", 0.3), Dish("나", 0.3), Dish("라", 0.3)]),
            (0, "lunch", [Dish("다", 0.1), Dish("가", 0.3), Dish("나", 0.3), Dish("라", 0.3)]),
            (0, "dinner", [Dish("라", 0.3), Dish("마", 0.5), Dish("바", 0.5)]),
            (1, "lunch", [Dish("마", 0.5), Dish("바", 0.5)]),
        ],
    )

    # 평균 0.1(다) → 평균 0.3 중 끼니 3개(라) → 끼니 2개는 이름 순(가, 나) → 0.5(마). 6번째(바) 제외
    assert [(m.menu_name, m.meal_count) for m in result] == [
        ("다", 2),
        ("라", 3),
        ("가", 2),
        ("나", 2),
        ("마", 2),
    ]


def test_left_menus_limits_to_period_and_patient(db_path: Path) -> None:
    with connect(db_path) as conn:
        insert_patient(conn)
        insert_patient(conn, patient_id="NS08", display_name="NS08")
        _add_meal(conn, START, "lunch", [Dish("멸치볶음", 0.2)])
        _add_meal(conn, END, "lunch", [Dish("멸치볶음", 0.4)])
        _add_meal(conn, date(2026, 11, 22), "lunch", [Dish("멸치볶음", 0.0)])
        _add_meal(conn, date(2026, 11, 30), "lunch", [Dish("멸치볶음", 0.0)])
        _add_meal(conn, _day(2), "lunch", [Dish("멸치볶음", 0.0)], patient_id="NS08")
        result = left_menus(conn, PID, START, END)

    assert result == (LeftMenu("멸치볶음", "side", pytest.approx(0.3), 2),)


def test_left_menus_without_records_is_empty(db_path: Path) -> None:
    assert _run(db_path, []) == ()


def test_left_menus_on_seed_follows_rules(service_db: Path) -> None:
    with connect(service_db) as conn:
        result = left_menus(conn, "NS03", date(2026, 11, 22), date(2026, 12, 5))

    assert 1 <= len(result) <= 5
    assert all(m.meal_count >= 2 and 0.0 <= m.avg_intake_fraction <= 0.5 for m in result)
    keys = [(m.avg_intake_fraction, -m.meal_count, m.menu_name) for m in result]
    assert keys == sorted(keys)
