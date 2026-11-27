"""`app.storage.db`의 연결 규칙과 `schema.sql` 제약 테스트."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from pathlib import Path

import pytest

from app.storage.db import SCHEMA_VERSION, connect, create_schema

BUSINESS_TABLES = frozenset(
    {
        "patients",
        "patient_weights",
        "patient_targets",
        "patient_assessments",
        "meal_plans",
        "meal_plan_slots",
        "meal_orders",
        "slot_intakes",
        "photos",
        "daily_intakes",
        "alerts",
        "recommendations",
        "prescriptions",
        "chat_threads",
    }
)
EXPECTED_INDEXED_COLUMNS = {
    ("meal_orders", ("patient_id",)),
    ("meal_orders", ("meal_plan_id",)),
    ("alerts", ("patient_id", "evaluated_at")),
    ("recommendations", ("patient_id", "status")),
    ("photos", ("status",)),
}

PATIENT_ID = "NS07"
MEAL_PLAN_ID = "2026-11-23_lunch_general"
MEAL_ORDER_ID = "NS07_2026-11-23_lunch"


# ---------------------------------------------------------------------------
# 행 만들기 도우미: 유효한 기본 행에 바꿀 열만 덮어쓴다.
# ---------------------------------------------------------------------------


def _insert(conn: sqlite3.Connection, table: str, row: Mapping[str, object]) -> None:
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
    _insert(conn, "patients", {**row, **overrides})


def insert_meal_plan(conn: sqlite3.Connection, **overrides: object) -> None:
    row = {
        "meal_plan_id": MEAL_PLAN_ID,
        "date": "2026-11-23",
        "meal": "lunch",
        "diet_type": "general",
        "baseline_photo_id": None,
    }
    _insert(conn, "meal_plans", {**row, **overrides})


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
    _insert(conn, "meal_plan_slots", {**row, **overrides})


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
    _insert(conn, "meal_orders", {**row, **overrides})


def insert_slot_intake(conn: sqlite3.Connection, **overrides: object) -> None:
    row = {
        "meal_order_id": MEAL_ORDER_ID,
        "slot_id": "slot_3",
        "intake_fraction_est": 0.5,
        "status": "estimated",
        "quality_issues": "[]",
        "estimate_basis": "mock",
    }
    _insert(conn, "slot_intakes", {**row, **overrides})


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
    _insert(conn, "photos", {**row, **overrides})


def insert_assessment(conn: sqlite3.Connection, **overrides: object) -> None:
    row = {
        "patient_id": PATIENT_ID,
        "assessed_on": "2026-11-23",
        "kind": "mna_sf",
        "result": "at_risk",
        "score": 10.0,
        "note": "",
    }
    _insert(conn, "patient_assessments", {**row, **overrides})


def insert_alert(conn: sqlite3.Connection, **overrides: object) -> None:
    row = {
        "alert_id": "A0001",
        "patient_id": PATIENT_ID,
        "evaluated_at": "2026-11-23T00:00:00",
        "level": "caution",
        "basis_period": "2026-11-17~2026-11-23",
        "basis_values": "{}",
        "nutrients": '["protein"]',
        "unrecorded_meals": 0,
    }
    _insert(conn, "alerts", {**row, **overrides})


def insert_recommendation(conn: sqlite3.Connection, **overrides: object) -> None:
    row = {
        "recommendation_id": "R0001",
        "patient_id": PATIENT_ID,
        "alert_id": None,
        "items": "[]",
        "cautions": "[]",
        "last_modified_by": "agent",
        "thread_id": None,
        "created_at": "2026-11-23T12:00:00",
        "updated_at": "2026-11-23T12:00:00",
        "status": "active",
    }
    _insert(conn, "recommendations", {**row, **overrides})


def _seed_order_context(conn: sqlite3.Connection) -> None:
    """환자 1명, 계획 1끼, 배식 칸 1개, 발주 1건."""
    insert_patient(conn)
    insert_meal_plan(conn)
    insert_slot(conn)
    insert_meal_order(conn)


# ---------------------------------------------------------------------------
# connect
# ---------------------------------------------------------------------------


def test_connect_sets_pragmas_and_row_factory(tmp_path: Path) -> None:
    with connect(tmp_path / "app.db") as conn:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
        assert conn.row_factory is sqlite3.Row


def test_connect_journal_mode_delete_option(tmp_path: Path) -> None:
    with connect(tmp_path / "app.db", journal_mode="DELETE") as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_connect_raises_when_journal_mode_is_not_applied() -> None:
    # 메모리 DB는 WAL로 바뀌지 않고 "memory"를 돌려준다.
    with pytest.raises(sqlite3.OperationalError, match="journal_mode"), connect(Path(":memory:")):
        pass


def test_connect_rejects_unknown_journal_mode(tmp_path: Path) -> None:
    with pytest.raises(ValueError), connect(tmp_path / "app.db", journal_mode="OFF; DROP"):
        pass


def test_connect_rows_are_readable_by_column_name(db_path: Path) -> None:
    with connect(db_path) as conn:
        insert_patient(conn)
    with connect(db_path) as conn:
        row = conn.execute("SELECT patient_id, sex FROM patients").fetchone()
    assert row["patient_id"] == PATIENT_ID
    assert row["sex"] == "female"


def test_connect_commits_on_normal_exit(db_path: Path) -> None:
    with connect(db_path) as conn:
        insert_patient(conn)
    with connect(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM patients").fetchone()[0]
    assert count == 1


def test_connect_rolls_back_on_exception(db_path: Path) -> None:
    with pytest.raises(RuntimeError, match="중단"), connect(db_path) as conn:
        insert_patient(conn)
        raise RuntimeError("중단")
    with connect(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM patients").fetchone()[0]
    assert count == 0


def test_connect_closes_connection_after_block(db_path: Path) -> None:
    with connect(db_path) as conn:
        pass
    with pytest.raises(sqlite3.ProgrammingError):
        conn.execute("SELECT 1")


def test_connect_closes_connection_after_exception(db_path: Path) -> None:
    with pytest.raises(RuntimeError), connect(db_path) as conn:
        raise RuntimeError("중단")
    with pytest.raises(sqlite3.ProgrammingError):
        conn.execute("SELECT 1")


# ---------------------------------------------------------------------------
# create_schema
# ---------------------------------------------------------------------------


def test_schema_version_is_one() -> None:
    assert SCHEMA_VERSION == 1


def test_schema_has_exactly_15_tables(db_path: Path) -> None:
    with connect(db_path) as conn:
        names = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        }
    assert len(names) == 15
    assert names == BUSINESS_TABLES | {"seed_meta"}


def test_schema_has_lookup_indexes(db_path: Path) -> None:
    with connect(db_path) as conn:
        found: set[tuple[str, tuple[str, ...]]] = set()
        for table, _ in EXPECTED_INDEXED_COLUMNS:
            for index in conn.execute(f"PRAGMA index_list({table})"):
                if index["origin"] != "c":
                    continue
                columns = tuple(
                    col["name"] for col in conn.execute(f"PRAGMA index_info({index['name']})")
                )
                found.add((table, columns))
    assert EXPECTED_INDEXED_COLUMNS <= found


def test_create_schema_without_begin_leaves_no_open_transaction(tmp_path: Path) -> None:
    with connect(tmp_path / "app.db") as conn:
        create_schema(conn)
        assert not conn.in_transaction


def test_create_schema_with_begin_rolls_back_ddl(tmp_path: Path) -> None:
    path = tmp_path / "app.db"
    with connect(path, journal_mode="DELETE") as conn:
        create_schema(conn, begin=True)
        assert conn.in_transaction
        conn.rollback()
    with connect(path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type = 'table'").fetchone()[
            0
        ]
    assert count == 0


def test_create_schema_with_begin_commits_ddl_and_rows_together(tmp_path: Path) -> None:
    path = tmp_path / "app.db"
    with connect(path, journal_mode="DELETE") as conn:
        create_schema(conn, begin=True)
        insert_patient(conn)
    with connect(path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM patients").fetchone()[0]
    assert count == 1


def test_seed_meta_stores_key_value(db_path: Path) -> None:
    with connect(db_path) as conn:
        conn.execute("INSERT INTO seed_meta (key, value) VALUES ('schema_version', '1')")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO seed_meta (key, value) VALUES ('schema_version', '2')")


# ---------------------------------------------------------------------------
# 외래 키·복합 키·유일 제약
# ---------------------------------------------------------------------------


def test_meal_order_for_unknown_patient_is_rejected(db_path: Path) -> None:
    with connect(db_path) as conn:
        insert_meal_plan(conn)
        with pytest.raises(sqlite3.IntegrityError):
            insert_meal_order(conn, patient_id="NOBODY")


@pytest.mark.parametrize(
    ("table", "row"),
    [
        ("patient_weights", {"measured_on": "2026-11-23", "weight_kg": 50.0}),
        (
            "patient_targets",
            {
                "effective_from": "2026-11-23",
                "energy_kcal": 1500.0,
                "protein_g": 55.0,
                "source": "team_set",
                "note": "",
            },
        ),
        ("patient_assessments", {"assessed_on": "2026-11-23", "kind": "chewing"}),
    ],
)
def test_history_tables_use_composite_primary_key(
    db_path: Path, table: str, row: dict[str, object]
) -> None:
    with connect(db_path) as conn:
        insert_patient(conn)
        _insert(conn, table, {"patient_id": PATIENT_ID, **row})
        with pytest.raises(sqlite3.IntegrityError):
            _insert(conn, table, {"patient_id": PATIENT_ID, **row})


def test_meal_plans_date_meal_diet_type_is_unique(db_path: Path) -> None:
    with connect(db_path) as conn:
        insert_meal_plan(conn)
        with pytest.raises(sqlite3.IntegrityError):
            insert_meal_plan(conn, meal_plan_id="duplicate_plan")


def test_meal_orders_patient_meal_plan_is_unique(db_path: Path) -> None:
    with connect(db_path) as conn:
        _seed_order_context(conn)
        with pytest.raises(sqlite3.IntegrityError):
            insert_meal_order(conn, meal_order_id="duplicate_order")


def test_photo_cross_references_commit_when_plan_inserted_first(db_path: Path) -> None:
    with connect(db_path) as conn:
        insert_meal_plan(conn, baseline_photo_id="P0001")
        insert_photo(conn, photo_id="P0001")
    with connect(db_path) as conn:
        row = conn.execute("SELECT baseline_photo_id FROM meal_plans").fetchone()
    assert row["baseline_photo_id"] == "P0001"


def test_photo_cross_references_commit_when_photo_inserted_first(db_path: Path) -> None:
    with connect(db_path) as conn:
        insert_patient(conn)
        insert_photo(conn, photo_id="P0001")
        insert_photo(
            conn,
            photo_id="P0002",
            kind="post",
            meal_order_id=MEAL_ORDER_ID,
            uploader_role="caregiver",
            file_path="var/photos/P0002.jpg",
        )
        insert_meal_plan(conn, baseline_photo_id="P0001")
        insert_meal_order(conn, post_photo_id="P0002")
    with connect(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM photos").fetchone()[0]
    assert count == 2


def test_dangling_photo_reference_fails_at_commit(db_path: Path) -> None:
    with pytest.raises(sqlite3.IntegrityError), connect(db_path) as conn:
        insert_meal_plan(conn, baseline_photo_id="MISSING")
    with connect(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM meal_plans").fetchone()[0]
    assert count == 0


# ---------------------------------------------------------------------------
# 열거값 CHECK
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("column", "invalid"),
    [
        ("sex", "unknown"),
        ("ckd_dialysis", "esrd"),
        ("data_source", "manual"),
    ],
)
def test_patient_enum_check_rejects_invalid(db_path: Path, column: str, invalid: str) -> None:
    with connect(db_path) as conn, pytest.raises(sqlite3.IntegrityError):
        insert_patient(conn, **{column: invalid})


@pytest.mark.parametrize(
    ("column", "invalid"),
    [
        ("order_status", "delivered"),
        ("record_status", "done"),
        ("staff_zero_reason", "sleeping"),
        ("data_source", "manual"),
    ],
)
def test_meal_order_enum_check_rejects_invalid(db_path: Path, column: str, invalid: str) -> None:
    with connect(db_path) as conn:
        insert_patient(conn)
        insert_meal_plan(conn)
        with pytest.raises(sqlite3.IntegrityError):
            insert_meal_order(conn, **{column: invalid})


@pytest.mark.parametrize(
    ("column", "valid"),
    [
        ("record_status", None),
        ("staff_zero_reason", "refused"),
        ("staff_zero_reason", "not_eaten"),
        ("order_status", "npo"),
        ("order_status", "cancelled"),
    ],
)
def test_meal_order_enum_check_accepts_valid(db_path: Path, column: str, valid: object) -> None:
    with connect(db_path) as conn:
        insert_patient(conn)
        insert_meal_plan(conn)
        insert_meal_order(conn, **{column: valid})


@pytest.mark.parametrize("invalid", ["midnight", "snack"])
def test_meal_plan_meal_check_rejects_invalid(db_path: Path, invalid: str) -> None:
    with connect(db_path) as conn, pytest.raises(sqlite3.IntegrityError):
        insert_meal_plan(conn, meal=invalid)


def test_slot_dish_type_check_rejects_invalid(db_path: Path) -> None:
    with connect(db_path) as conn:
        insert_meal_plan(conn)
        with pytest.raises(sqlite3.IntegrityError):
            insert_slot(conn, dish_type="dessert")


def test_slot_intake_status_check_rejects_invalid(db_path: Path) -> None:
    with connect(db_path) as conn:
        _seed_order_context(conn)
        with pytest.raises(sqlite3.IntegrityError):
            insert_slot_intake(conn, status="partial")


@pytest.mark.parametrize(
    ("column", "invalid"),
    [
        ("kind", "pre"),
        ("status", "processing"),
        ("stage", "upload"),
        ("outcome", "ok"),
        ("uploader_role", "doctor"),
        ("data_source", "manual"),
    ],
)
def test_photo_enum_check_rejects_invalid(db_path: Path, column: str, invalid: str) -> None:
    with connect(db_path) as conn:
        insert_meal_plan(conn)
        with pytest.raises(sqlite3.IntegrityError):
            insert_photo(conn, **{column: invalid})


@pytest.mark.parametrize(
    "status",
    ["uploaded", "waiting_baseline", "queued", "analyzing", "done", "not_determinable", "failed"],
)
def test_photo_status_accepts_all_data_model_values(db_path: Path, status: str) -> None:
    with connect(db_path) as conn:
        insert_meal_plan(conn)
        insert_photo(conn, status=status)


def test_alert_level_check_rejects_invalid(db_path: Path) -> None:
    with connect(db_path) as conn:
        insert_patient(conn)
        with pytest.raises(sqlite3.IntegrityError):
            insert_alert(conn, level="critical")


@pytest.mark.parametrize(
    ("column", "invalid"),
    [("status", "draft"), ("last_modified_by", "nurse")],
)
def test_recommendation_enum_check_rejects_invalid(
    db_path: Path, column: str, invalid: str
) -> None:
    with connect(db_path) as conn:
        insert_patient(conn)
        with pytest.raises(sqlite3.IntegrityError):
            insert_recommendation(conn, **{column: invalid})


def test_prescription_status_check_rejects_invalid(db_path: Path) -> None:
    with connect(db_path) as conn:
        insert_patient(conn)
        row = {
            "prescription_id": "RX0001",
            "patient_id": PATIENT_ID,
            "recommendation_id": None,
            "items": "[]",
            "confirmed_at": "2026-11-23T13:00:00",
            "status": "draft",
        }
        with pytest.raises(sqlite3.IntegrityError):
            _insert(conn, "prescriptions", row)


def test_patient_target_source_check_rejects_invalid(db_path: Path) -> None:
    with connect(db_path) as conn:
        insert_patient(conn)
        row = {
            "patient_id": PATIENT_ID,
            "effective_from": "2026-11-23",
            "energy_kcal": 1500.0,
            "protein_g": 55.0,
            "source": "guess",
            "note": "",
        }
        with pytest.raises(sqlite3.IntegrityError):
            _insert(conn, "patient_targets", row)


@pytest.mark.parametrize("invalid", ["bmi", "MNA_SF", ""])
def test_assessment_kind_check_rejects_invalid(db_path: Path, invalid: str) -> None:
    with connect(db_path) as conn:
        insert_patient(conn)
        with pytest.raises(sqlite3.IntegrityError):
            insert_assessment(conn, kind=invalid)


@pytest.mark.parametrize(
    "kind",
    [
        "mna_sf",
        "nutrition_screening",
        "swallowing",
        "chewing",
        "appetite_assist",
        "pressure_injury",
        "refeeding_risk",
    ],
)
def test_assessment_kind_accepts_all_data_model_values(db_path: Path, kind: str) -> None:
    with connect(db_path) as conn:
        insert_patient(conn)
        insert_assessment(conn, kind=kind)


# ---------------------------------------------------------------------------
# slot_intakes: estimate_basis·섭취 비율 범위, meal_orders.incomplete
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("basis", ["mock", "staff", "vlm:qwen"])
def test_estimate_basis_accepts_allowed_values(db_path: Path, basis: str) -> None:
    with connect(db_path) as conn:
        _seed_order_context(conn)
        insert_slot_intake(conn, estimate_basis=basis)


@pytest.mark.parametrize("basis", ["vlm", "human", "VLM:qwen", "xvlm:qwen"])
def test_estimate_basis_rejects_other_values(db_path: Path, basis: str) -> None:
    with connect(db_path) as conn:
        _seed_order_context(conn)
        with pytest.raises(sqlite3.IntegrityError):
            insert_slot_intake(conn, estimate_basis=basis)


@pytest.mark.parametrize("fraction", [1.1, -0.1])
def test_intake_fraction_out_of_range_is_rejected(db_path: Path, fraction: float) -> None:
    with connect(db_path) as conn:
        _seed_order_context(conn)
        with pytest.raises(sqlite3.IntegrityError):
            insert_slot_intake(conn, intake_fraction_est=fraction)


@pytest.mark.parametrize("fraction", [None, 0.0, 1.0])
def test_intake_fraction_accepts_null_and_bounds(db_path: Path, fraction: float | None) -> None:
    with connect(db_path) as conn:
        _seed_order_context(conn)
        insert_slot_intake(conn, intake_fraction_est=fraction)


def test_slot_intake_for_unknown_meal_order_is_rejected(db_path: Path) -> None:
    # 외래 키보다 먼저 BEFORE INSERT 트리거가 발주·칸 불일치로 거절한다.
    with connect(db_path) as conn, pytest.raises(sqlite3.IntegrityError, match=SLOT_INTAKE_MESSAGE):
        insert_slot_intake(conn, meal_order_id="NOBODY_order")


@pytest.mark.parametrize("incomplete", [2, -1])
def test_incomplete_must_be_zero_or_one(db_path: Path, incomplete: int) -> None:
    with connect(db_path) as conn:
        insert_patient(conn)
        insert_meal_plan(conn)
        with pytest.raises(sqlite3.IntegrityError):
            insert_meal_order(conn, incomplete=incomplete)


# ---------------------------------------------------------------------------
# meal_plan_slots: 미배식 칸 CHECK
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        {"served_g": 0.0, "menu_name": "두부조림", "energy_kcal": 0.0, "protein_g": 0.0},
        {"served_g": 60.0, "menu_name": None},
        {"served_g": 0.0, "menu_name": None, "energy_kcal": 10.0, "protein_g": 0.0},
        {"served_g": 0.0, "menu_name": None, "energy_kcal": 0.0, "protein_g": 1.0},
        {"served_g": -1.0},
    ],
    ids=[
        "unserved_with_menu",
        "served_without_menu",
        "unserved_with_energy",
        "unserved_with_protein",
        "negative_served",
    ],
)
def test_unserved_slot_check_rejects_inconsistent_rows(
    db_path: Path, overrides: dict[str, object]
) -> None:
    with connect(db_path) as conn:
        insert_meal_plan(conn)
        with pytest.raises(sqlite3.IntegrityError):
            insert_slot(conn, **overrides)


def test_unserved_slot_with_zero_values_is_allowed(db_path: Path) -> None:
    with connect(db_path) as conn:
        insert_meal_plan(conn)
        insert_slot(
            conn,
            slot_id="slot_5",
            dish_type="side",
            menu_name=None,
            served_g=0.0,
            energy_kcal=0.0,
            protein_g=0.0,
        )
    with connect(db_path) as conn:
        row = conn.execute("SELECT menu_name, served_g FROM meal_plan_slots").fetchone()
    assert row["menu_name"] is None
    assert row["served_g"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# 칸별 섭취의 칸 무결성 트리거
# ---------------------------------------------------------------------------

OTHER_MEAL_PLAN_ID = "2026-11-23_dinner_general"
OTHER_MEAL_ORDER_ID = "NS07_2026-11-23_dinner"
UNSERVED_SLOT_ID = "slot_5"
INTAKE_SLOT_IDS = ("slot_1", "slot_2", "slot_3", "slot_4", "slot_6")
SLOT_COLUMNS = (
    "slot_id",
    "position",
    "dish_type",
    "menu_name",
    "served_g",
    "energy_kcal",
    "protein_g",
)
PLAN_SLOTS = (
    ("slot_1", "아랫줄 왼쪽", "rice", "쌀밥", 210.0, 300.0, 5.0),
    ("slot_2", "아랫줄 오른쪽", "soup", "근대국", 250.0, 40.0, 2.0),
    ("slot_3", "윗줄 1 (왼쪽 끝)", "main", "두부조림", 60.0, 90.0, 10.0),
    ("slot_4", "윗줄 2", "side", "시금치나물", 50.0, 30.0, 2.0),
    ("slot_5", "윗줄 3", "side", None, 0.0, 0.0, 0.0),
    ("slot_6", "윗줄 4 (오른쪽 끝)", "kimchi", "배추김치", 40.0, 10.0, 0.5),
)
SLOT_INTAKE_MESSAGE = "칸별 섭취의 발주·칸이 배식 계획의 배식 칸과 맞지 않는다"
ORDER_PLAN_MESSAGE = "발주의 배식 계획은 바꿀 수 없다"
SLOT_KEY_MESSAGE = "배식 칸의 키는 바꿀 수 없다"
SLOT_UNSERVE_MESSAGE = "섭취 기록이 있는 칸은 미배식으로 바꿀 수 없다"
SLOT_DELETE_MESSAGE = "섭취 기록이 있는 칸은 삭제할 수 없다"


SlotValues = tuple[str, str, str, str | None, float, float, float]


def _insert_plan_slots(
    conn: sqlite3.Connection, meal_plan_id: str, slots: tuple[SlotValues, ...]
) -> None:
    for values in slots:
        row = dict(zip(SLOT_COLUMNS, values, strict=True))
        insert_slot(conn, meal_plan_id=meal_plan_id, **row)


@pytest.fixture
def slot_db(db_path: Path) -> Path:
    """환자 1명, 계획 1끼(6칸, slot_5 미배식), 다른 계획 1끼, 발주 1건, 칸별 섭취 5건.

    다른 계획은 slot_1~slot_3만 배식 칸으로 둔다(slot_4·slot_6은 없다).
    """
    with connect(db_path) as conn:
        insert_patient(conn)
        insert_meal_plan(conn)
        _insert_plan_slots(conn, MEAL_PLAN_ID, PLAN_SLOTS)
        insert_meal_plan(conn, meal_plan_id=OTHER_MEAL_PLAN_ID, meal="dinner")
        _insert_plan_slots(conn, OTHER_MEAL_PLAN_ID, PLAN_SLOTS[:3])
        insert_meal_order(conn)
        for slot_id in INTAKE_SLOT_IDS:
            insert_slot_intake(conn, slot_id=slot_id)
    return db_path


def _replace_row(
    conn: sqlite3.Connection, table: str, where: str, params: tuple[object, ...], **changes: object
) -> None:
    """기존 행을 읽어 `changes`를 덮어쓴 뒤 `INSERT OR REPLACE`로 다시 쓴다."""
    current = conn.execute(f"SELECT * FROM {table} WHERE {where}", params).fetchone()
    row = {**dict(current), **changes}
    columns = ", ".join(row)
    placeholders = ", ".join("?" for _ in row)
    conn.execute(
        f"INSERT OR REPLACE INTO {table} ({columns}) VALUES ({placeholders})", tuple(row.values())
    )


def _snapshot(conn: sqlite3.Connection) -> tuple[list[tuple[object, ...]], ...]:
    """칸·칸별 섭취·발주 행 전체를 키 순으로 읽는다."""
    queries = (
        "SELECT * FROM meal_plan_slots ORDER BY meal_plan_id, slot_id",
        "SELECT * FROM slot_intakes ORDER BY meal_order_id, slot_id",
        "SELECT * FROM meal_orders ORDER BY meal_order_id",
    )
    return tuple([tuple(row) for row in conn.execute(query)] for query in queries)


def test_slot_fixture_has_intakes_for_served_slots(slot_db: Path) -> None:
    with connect(slot_db) as conn:
        slot_ids = [r["slot_id"] for r in conn.execute("SELECT slot_id FROM slot_intakes")]
    assert sorted(slot_ids) == list(INTAKE_SLOT_IDS)


# (1) slot_intakes 쓰기


@pytest.mark.parametrize("slot_id", ["slot_7", UNSERVED_SLOT_ID])
def test_slot_intake_insert_outside_served_slots_is_rejected(slot_db: Path, slot_id: str) -> None:
    with connect(slot_db) as conn:
        before = _snapshot(conn)
        with pytest.raises(sqlite3.IntegrityError, match=SLOT_INTAKE_MESSAGE):
            insert_slot_intake(conn, slot_id=slot_id)
        assert _snapshot(conn) == before


@pytest.mark.parametrize("slot_id", ["slot_7", UNSERVED_SLOT_ID])
def test_slot_intake_update_slot_outside_served_slots_is_rejected(
    slot_db: Path, slot_id: str
) -> None:
    with connect(slot_db) as conn:
        before = _snapshot(conn)
        with pytest.raises(sqlite3.IntegrityError, match=SLOT_INTAKE_MESSAGE):
            conn.execute("UPDATE slot_intakes SET slot_id = ? WHERE slot_id = 'slot_4'", (slot_id,))
        assert _snapshot(conn) == before


def test_slot_intake_move_to_order_without_that_slot_is_rejected(slot_db: Path) -> None:
    with connect(slot_db) as conn:
        insert_meal_order(conn, meal_order_id=OTHER_MEAL_ORDER_ID, meal_plan_id=OTHER_MEAL_PLAN_ID)
        before = _snapshot(conn)
        with pytest.raises(sqlite3.IntegrityError, match=SLOT_INTAKE_MESSAGE):
            conn.execute(
                "UPDATE slot_intakes SET meal_order_id = ? WHERE slot_id = 'slot_4'",
                (OTHER_MEAL_ORDER_ID,),
            )
        assert _snapshot(conn) == before


def test_slot_intake_move_to_order_with_that_slot_is_allowed(slot_db: Path) -> None:
    with connect(slot_db) as conn:
        insert_meal_order(conn, meal_order_id=OTHER_MEAL_ORDER_ID, meal_plan_id=OTHER_MEAL_PLAN_ID)
        conn.execute(
            "UPDATE slot_intakes SET meal_order_id = ? WHERE slot_id = 'slot_1'",
            (OTHER_MEAL_ORDER_ID,),
        )
    with connect(slot_db) as conn:
        row = conn.execute("SELECT meal_order_id FROM slot_intakes WHERE slot_id = 'slot_1'")
        assert row.fetchone()["meal_order_id"] == OTHER_MEAL_ORDER_ID


def test_slot_intake_update_of_other_columns_is_allowed(slot_db: Path) -> None:
    with connect(slot_db) as conn:
        conn.execute("UPDATE slot_intakes SET intake_fraction_est = 0.9 WHERE slot_id = 'slot_4'")
    with connect(slot_db) as conn:
        row = conn.execute(
            "SELECT intake_fraction_est FROM slot_intakes WHERE slot_id = 'slot_4'"
        ).fetchone()
    assert row["intake_fraction_est"] == pytest.approx(0.9)


def test_slot_intake_update_slot_to_same_value_is_allowed(slot_db: Path) -> None:
    with connect(slot_db) as conn:
        before = _snapshot(conn)
        cursor = conn.execute("UPDATE slot_intakes SET slot_id = slot_id WHERE slot_id = 'slot_3'")
        assert cursor.rowcount == 1
        assert _snapshot(conn) == before


# (2) meal_orders.meal_plan_id


def test_meal_order_plan_change_is_rejected(slot_db: Path) -> None:
    with connect(slot_db) as conn:
        before = _snapshot(conn)
        with pytest.raises(sqlite3.IntegrityError, match=ORDER_PLAN_MESSAGE):
            conn.execute(
                "UPDATE meal_orders SET meal_plan_id = ? WHERE meal_order_id = ?",
                (OTHER_MEAL_PLAN_ID, MEAL_ORDER_ID),
            )
        assert _snapshot(conn) == before


def test_meal_order_plan_update_to_same_value_is_allowed(slot_db: Path) -> None:
    with connect(slot_db) as conn:
        conn.execute(
            "UPDATE meal_orders SET meal_plan_id = ?, record_status = 'pending' "
            "WHERE meal_order_id = ?",
            (MEAL_PLAN_ID, MEAL_ORDER_ID),
        )
    with connect(slot_db) as conn:
        row = conn.execute("SELECT meal_plan_id, record_status FROM meal_orders").fetchone()
    assert (row["meal_plan_id"], row["record_status"]) == (MEAL_PLAN_ID, "pending")


# (3) meal_plan_slots 변경


@pytest.mark.parametrize(
    ("column", "value"),
    [("meal_plan_id", OTHER_MEAL_PLAN_ID), ("slot_id", "slot_9")],
)
@pytest.mark.parametrize("slot_id", ["slot_4", UNSERVED_SLOT_ID])
def test_slot_key_change_is_rejected(slot_db: Path, column: str, value: str, slot_id: str) -> None:
    with connect(slot_db) as conn:
        before = _snapshot(conn)
        with pytest.raises(sqlite3.IntegrityError, match=SLOT_KEY_MESSAGE):
            conn.execute(
                f"UPDATE meal_plan_slots SET {column} = ? WHERE meal_plan_id = ? AND slot_id = ?",
                (value, MEAL_PLAN_ID, slot_id),
            )
        assert _snapshot(conn) == before


def test_unserving_slot_with_intakes_is_rejected_and_rows_unchanged(slot_db: Path) -> None:
    with connect(slot_db) as conn:
        before = _snapshot(conn)
        with pytest.raises(sqlite3.IntegrityError, match=SLOT_UNSERVE_MESSAGE):
            conn.execute(
                "UPDATE meal_plan_slots SET menu_name = NULL, served_g = 0, energy_kcal = 0, "
                "protein_g = 0 WHERE meal_plan_id = ? AND slot_id = 'slot_4'",
                (MEAL_PLAN_ID,),
            )
        assert _snapshot(conn) == before


def test_served_g_change_on_slot_with_intakes_to_nonzero_is_allowed(slot_db: Path) -> None:
    with connect(slot_db) as conn:
        conn.execute(
            "UPDATE meal_plan_slots SET served_g = 70 "
            "WHERE meal_plan_id = ? AND slot_id = 'slot_4'",
            (MEAL_PLAN_ID,),
        )
    with connect(slot_db) as conn:
        row = conn.execute(
            "SELECT served_g FROM meal_plan_slots WHERE meal_plan_id = ? AND slot_id = 'slot_4'",
            (MEAL_PLAN_ID,),
        ).fetchone()
    assert row["served_g"] == pytest.approx(70.0)


def test_served_g_change_on_slot_without_intakes_is_allowed(slot_db: Path) -> None:
    with connect(slot_db) as conn:
        conn.execute(
            "UPDATE meal_plan_slots SET menu_name = NULL, served_g = 0, energy_kcal = 0, "
            "protein_g = 0 WHERE meal_plan_id = ? AND slot_id = 'slot_3'",
            (OTHER_MEAL_PLAN_ID,),
        )
        conn.execute(
            "UPDATE meal_plan_slots SET menu_name = '계란찜', served_g = 50, energy_kcal = 70 "
            "WHERE meal_plan_id = ? AND slot_id = ?",
            (MEAL_PLAN_ID, UNSERVED_SLOT_ID),
        )
    with connect(slot_db) as conn:
        rows = conn.execute(
            "SELECT meal_plan_id, served_g FROM meal_plan_slots "
            "WHERE (meal_plan_id = ? AND slot_id = 'slot_3') OR (meal_plan_id = ? AND slot_id = ?)",
            (OTHER_MEAL_PLAN_ID, MEAL_PLAN_ID, UNSERVED_SLOT_ID),
        )
        served = {row["meal_plan_id"]: row["served_g"] for row in rows}
    assert served[OTHER_MEAL_PLAN_ID] == pytest.approx(0.0)
    assert served[MEAL_PLAN_ID] == pytest.approx(50.0)


# (4) meal_plan_slots 삭제


def test_deleting_slot_with_intakes_is_rejected_and_row_stays(slot_db: Path) -> None:
    with connect(slot_db) as conn:
        before = _snapshot(conn)
        with pytest.raises(sqlite3.IntegrityError, match=SLOT_DELETE_MESSAGE):
            conn.execute(
                "DELETE FROM meal_plan_slots WHERE meal_plan_id = ? AND slot_id = 'slot_4'",
                (MEAL_PLAN_ID,),
            )
        assert _snapshot(conn) == before


def test_deleting_slot_without_intakes_is_allowed(slot_db: Path) -> None:
    with connect(slot_db) as conn:
        conn.execute(
            "DELETE FROM meal_plan_slots WHERE meal_plan_id = ? AND slot_id = ?",
            (MEAL_PLAN_ID, UNSERVED_SLOT_ID),
        )
        count = conn.execute(
            "SELECT COUNT(*) FROM meal_plan_slots WHERE meal_plan_id = ?", (MEAL_PLAN_ID,)
        ).fetchone()[0]
    assert count == 5


# INSERT OR REPLACE: 기존 행 삭제 + 삽입이라 UPDATE·DELETE 트리거를 우회하지 못하게 막는다.

_ORDER_WHERE = "meal_order_id = ?"
_SLOT_WHERE = "meal_plan_id = ? AND slot_id = ?"


def test_replace_moving_meal_order_to_other_plan_is_rejected(slot_db: Path) -> None:
    with connect(slot_db) as conn:
        before = _snapshot(conn)
        with pytest.raises(sqlite3.IntegrityError, match=ORDER_PLAN_MESSAGE):
            _replace_row(
                conn, "meal_orders", _ORDER_WHERE, (MEAL_ORDER_ID,), meal_plan_id=OTHER_MEAL_PLAN_ID
            )
        assert _snapshot(conn) == before


def test_replace_meal_order_with_same_plan_is_allowed(slot_db: Path) -> None:
    with connect(slot_db) as conn:
        _replace_row(conn, "meal_orders", _ORDER_WHERE, (MEAL_ORDER_ID,), record_status="pending")
    with connect(slot_db) as conn:
        row = conn.execute("SELECT meal_plan_id, record_status FROM meal_orders").fetchone()
        intakes = conn.execute("SELECT COUNT(*) FROM slot_intakes").fetchone()[0]
    assert (row["meal_plan_id"], row["record_status"]) == (MEAL_PLAN_ID, "pending")
    assert intakes == len(INTAKE_SLOT_IDS)


def test_replace_unserving_slot_with_intakes_is_rejected(slot_db: Path) -> None:
    with connect(slot_db) as conn:
        before = _snapshot(conn)
        with pytest.raises(sqlite3.IntegrityError, match=SLOT_UNSERVE_MESSAGE):
            _replace_row(
                conn,
                "meal_plan_slots",
                _SLOT_WHERE,
                (MEAL_PLAN_ID, "slot_4"),
                menu_name=None,
                served_g=0.0,
                energy_kcal=0.0,
                protein_g=0.0,
            )
        assert _snapshot(conn) == before


def test_replace_served_slot_with_intakes_is_allowed(slot_db: Path) -> None:
    with connect(slot_db) as conn:
        before_intakes = _snapshot(conn)[1]
        _replace_row(conn, "meal_plan_slots", _SLOT_WHERE, (MEAL_PLAN_ID, "slot_4"), served_g=70.0)
    with connect(slot_db) as conn:
        row = conn.execute(
            f"SELECT served_g FROM meal_plan_slots WHERE {_SLOT_WHERE}", (MEAL_PLAN_ID, "slot_4")
        ).fetchone()
        assert _snapshot(conn)[1] == before_intakes
    assert row["served_g"] == pytest.approx(70.0)
