"""저장소 테스트가 함께 쓰는 행 만들기 도우미.

각 `insert_*`는 스키마 제약을 모두 통과하는 기본 행에 바꿀 열만 덮어써서 넣는다.
시나리오(여러 행을 엮는 준비)는 각 테스트 파일에 둔다.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping

PATIENT_ID = "NS07"
MEAL_PLAN_ID = "2026-11-23_lunch_general"
MEAL_ORDER_ID = "NS07_2026-11-23_lunch"


def insert_row(conn: sqlite3.Connection, table: str, row: Mapping[str, object]) -> None:
    columns = ", ".join(row)
    placeholders = ", ".join("?" for _ in row)
    conn.execute(f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", tuple(row.values()))


def insert_patient(conn: sqlite3.Connection, **overrides: object) -> None:
    row = {
        "patient_id": PATIENT_ID,
        "display_name": "NS07",
        "room": "302호",
        "sex": "female",
        "birth_year": 1944,
        "height_cm": 154.0,
        "default_diet_type": "general",
        "conditions": '["고혈압"]',
        "diet_restrictions": "",
        "ckd_dialysis": "none",
        "observation_start": "2026-11-16",
        "data_source": "mock",
    }
    insert_row(conn, "patients", {**row, **overrides})


def insert_meal_plan(conn: sqlite3.Connection, **overrides: object) -> None:
    row = {
        "meal_plan_id": MEAL_PLAN_ID,
        "date": "2026-11-23",
        "meal": "lunch",
        "diet_type": "general",
        "baseline_photo_id": None,
    }
    insert_row(conn, "meal_plans", {**row, **overrides})


def insert_slot(conn: sqlite3.Connection, **overrides: object) -> None:
    row = {
        "meal_plan_id": MEAL_PLAN_ID,
        "slot_id": "slot_3",
        "position": "윗줄 1 (왼쪽 끝)",
        "dish_type": "main",
        "menu_name": "두부조림",
        "served_g": 60.0,
        "energy_kcal": 90.0,
        "protein_g": 10.0,
    }
    insert_row(conn, "meal_plan_slots", {**row, **overrides})


def insert_meal_order(conn: sqlite3.Connection, **overrides: object) -> None:
    row = {
        "meal_order_id": MEAL_ORDER_ID,
        "patient_id": PATIENT_ID,
        "meal_plan_id": MEAL_PLAN_ID,
        "diet_category": "상식",
        "diet_code": "일반상식",
        "order_status": "ordered",
        "order_from": "2026-11-16 breakfast",
        "order_note": "",
        "record_status": "recorded",
        "post_photo_id": None,
        "staff_zero_reason": None,
        "energy_kcal_est": 300.0,
        "protein_g_est": 12.0,
        "incomplete": 0,
        "data_source": "mock",
    }
    insert_row(conn, "meal_orders", {**row, **overrides})


def insert_slot_intake(conn: sqlite3.Connection, **overrides: object) -> None:
    row = {
        "meal_order_id": MEAL_ORDER_ID,
        "slot_id": "slot_3",
        "intake_fraction_est": 0.5,
        "status": "estimated",
        "quality_issues": "[]",
        "estimate_basis": "mock",
    }
    insert_row(conn, "slot_intakes", {**row, **overrides})


def insert_photo(conn: sqlite3.Connection, **overrides: object) -> None:
    row = {
        "photo_id": "P0001",
        "kind": "baseline",
        "meal_plan_id": MEAL_PLAN_ID,
        "meal_order_id": None,
        "uploader_role": "dietitian",
        "file_path": "var/photos/P0001.jpg",
        "status": "done",
        "stage": None,
        "outcome": None,
        "error": None,
        "uploaded_at": "2026-11-23T11:50:00",
        "updated_at": "2026-11-23T11:50:00",
        "data_source": "mock",
    }
    insert_row(conn, "photos", {**row, **overrides})


def insert_assessment(conn: sqlite3.Connection, **overrides: object) -> None:
    row = {
        "patient_id": PATIENT_ID,
        "assessed_on": "2026-11-23",
        "kind": "mna_sf",
        "result": "at_risk",
        "score": 10.0,
        "note": "",
    }
    insert_row(conn, "patient_assessments", {**row, **overrides})


def insert_alert(conn: sqlite3.Connection, **overrides: object) -> None:
    row = {
        "alert_id": "A0001",
        "patient_id": PATIENT_ID,
        "evaluated_at": "2026-11-23T00:00:00",
        "level": "caution",
        "basis_period": "2026-11-17~2026-11-23",
        "basis_values": "[]",
        "nutrients": '["protein"]',
        "unrecorded_meals": 0,
    }
    insert_row(conn, "alerts", {**row, **overrides})


def insert_recommendation(conn: sqlite3.Connection, **overrides: object) -> None:
    row = {
        "recommendation_id": "R0001",
        "patient_id": PATIENT_ID,
        "alert_id": None,
        "items": "[]",
        "cautions": "[]",
        "last_modified_by": "agent",
        "thread_id": None,
        "created_at": "2026-11-23T12:00:00.000000",
        "updated_at": "2026-11-23T12:00:00.000000",
        "status": "active",
    }
    insert_row(conn, "recommendations", {**row, **overrides})
