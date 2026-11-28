"""환자 조회 API 테스트 (스펙 3.3: 목록·요약·섭취 추이·경고·추천 카드).

시드 DB(D=2026-12-05, `FakeNutritionEngine` 목표 1500 kcal·55 g `kdri`)로 시작한 모듈 앱을 쓴다.
시드에는 모든 환자에 `none` 판정이 있고 카드·처방은 없다. 판정·카드·처방·환자는 테스트가
`scratch`로 넣고 테스트가 끝나면 지운다.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.storage.codec import items_to_json
from tests.api.conftest import make_api_settings
from tests.api.scratch import ScratchRows
from tests.storage.items import AGENT_ITEM, DOCTOR_ITEM
from tests.storage.rows import insert_alert, insert_patient, insert_recommendation, insert_row

PATIENT_IDS = [f"NS{n:02d}" for n in range(1, 11)]
LIST_KEYS = {"patient_id", "display_name", "room", "alert_level", "alert_nutrients"}
DETAIL_KEYS = {
    "patient_id",
    "display_name",
    "room",
    "sex",
    "age",
    "height_cm",
    "conditions",
    "diet_restrictions",
    "ckd_dialysis",
    "latest_weight",
    "weight_change_30d",
    "bmi",
    "target",
    "assessments",
}
DAY_KEYS = {
    "date",
    "energy_kcal",
    "protein_g",
    "energy_pct",
    "protein_pct",
    "recorded_meals",
    "unrecorded_meals",
    "npo_meals",
    "target",
}
FAKE_DAY_TARGET = {"energy_kcal": 1500.0, "protein_g": 55.0, "source": "kdri"}
NEW_PATIENT = "NS99"
CAUTION_ALERT_ID = "alert_NS03_2026-12-05"
CARD_ID = "rec_api_read"
CREATED_AT = "2026-12-05T09:30:00.123456"
UPDATED_AT = "2026-12-05T10:00:00.000000"
HTML = {"Accept": "text/html"}
INDEX_HTML = "<!doctype html><title>NutriSight</title>"


def _add_caution_alert(scratch: ScratchRows) -> None:
    """NS03에 시연일 `caution` 판정(단백질, 근거 하나)을 넣는다."""
    scratch.add(
        insert_alert,
        "alerts",
        "alert_id",
        alert_id=CAUTION_ALERT_ID,
        patient_id="NS03",
        evaluated_at="2026-12-05T23:59:59",
        level="caution",
        basis_period="2026-11-29~2026-12-05",
        basis_values=json.dumps([{"nutrient": "protein", "avg_pct": 61.5, "low_days_streak": 3}]),
        nutrients='["protein"]',
        unrecorded_meals=2,
    )


def _add_new_patient(scratch: ScratchRows) -> None:
    """판정·체중·평가·카드가 없는 환자를 넣는다."""
    scratch.add(insert_patient, "patients", "patient_id", patient_id=NEW_PATIENT)


def _add_prescription(scratch: ScratchRows, prescription_id: str, confirmed_at: str) -> None:
    scratch.add(
        lambda conn, **row: insert_row(conn, "prescriptions", row),
        "prescriptions",
        "prescription_id",
        prescription_id=prescription_id,
        patient_id="NS03",
        recommendation_id=None,
        items=items_to_json((DOCTOR_ITEM,)),
        confirmed_at=confirmed_at,
        status="confirmed",
    )


# 목록 ----------------------------------------------------------------------


def test_list_returns_ten_patients_in_id_order(client: TestClient) -> None:
    response = client.get("/api/patients")

    assert response.status_code == 200
    body = response.json()
    assert [p["patient_id"] for p in body] == PATIENT_IDS
    assert all(set(p) == LIST_KEYS for p in body)
    assert body[0] == {
        "patient_id": "NS01",
        "display_name": "NS01",
        "room": "301호",
        "alert_level": "none",
        "alert_nutrients": [],
    }


def test_list_shows_latest_caution_alert(client: TestClient, scratch: ScratchRows) -> None:
    _add_caution_alert(scratch)

    body = client.get("/api/patients").json()

    ns03 = next(p for p in body if p["patient_id"] == "NS03")
    assert ns03["alert_level"] == "caution"
    assert ns03["alert_nutrients"] == ["protein"]


def test_list_alert_level_is_null_without_alert(client: TestClient, scratch: ScratchRows) -> None:
    _add_new_patient(scratch)

    body = client.get("/api/patients").json()

    assert body[-1]["patient_id"] == NEW_PATIENT
    assert body[-1]["alert_level"] is None
    assert body[-1]["alert_nutrients"] == []


# 요약 ----------------------------------------------------------------------


def test_detail_has_spec_fields_unrounded(client: TestClient) -> None:
    response = client.get("/api/patients/NS07")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == DETAIL_KEYS
    assert body["sex"] == "female"
    assert body["age"] == 82
    assert body["conditions"] == ["고혈압", "퇴행성 무릎관절염"]
    assert body["ckd_dialysis"] == "none"
    assert body["latest_weight"] == {"measured_on": "2026-11-28", "weight_kg": 50.0}
    assert body["weight_change_30d"]["kg"] == pytest.approx(-2.0)
    assert body["weight_change_30d"]["pct"] == pytest.approx(-2.0 / 52.0 * 100)
    assert body["bmi"] == pytest.approx(50.0 / 1.54**2)
    assert body["target"] == {
        "energy_kcal": 1500.0,
        "protein_g": 55.0,
        "source": "kdri",
        "effective_from": None,
    }
    kinds = [a["kind"] for a in body["assessments"]]
    assert kinds == sorted(kinds)
    mna = next(a for a in body["assessments"] if a["kind"] == "mna_sf")
    assert mna == {
        "kind": "mna_sf",
        "assessed_on": "2026-11-28",
        "result": "at_risk",
        "score": 10.0,
        "note": "위험 있음, MNA-SF 10/14점",
    }


def test_detail_nulls_without_weights(client: TestClient, scratch: ScratchRows) -> None:
    _add_new_patient(scratch)

    body = client.get(f"/api/patients/{NEW_PATIENT}").json()

    assert body["latest_weight"] is None
    assert body["weight_change_30d"] is None
    assert body["bmi"] is None
    assert body["assessments"] == []


@pytest.mark.parametrize(
    "path",
    [
        "/api/patients/XX",
        "/api/patients/XX/intake",
        "/api/patients/XX/alert",
        "/api/patients/XX/recommendation",
    ],
)
def test_unknown_patient_is_404(client: TestClient, path: str) -> None:
    response = client.get(path)

    assert response.status_code == 404
    assert "XX" in response.json()["detail"]


# 섭취 추이 -----------------------------------------------------------------


def test_intake_returns_period_days_and_targets(client: TestClient) -> None:
    response = client.get("/api/patients/NS03/intake", params={"days": 14})

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"patient_id", "period_start", "period_end", "days", "prescriptions"}
    assert body["patient_id"] == "NS03"
    assert (body["period_start"], body["period_end"]) == ("2026-11-22", "2026-12-05")
    days = body["days"]
    assert [d["date"] for d in days] == sorted(d["date"] for d in days)
    assert all(set(d) == DAY_KEYS for d in days)
    assert all(d["target"] == FAKE_DAY_TARGET for d in days)
    assert days[0]["date"] == "2026-11-28"
    assert days[0]["energy_kcal"] == pytest.approx(949.2)
    assert days[0]["recorded_meals"] == 3
    assert body["prescriptions"] == []


def test_intake_defaults_to_14_days(client: TestClient) -> None:
    default = client.get("/api/patients/NS03/intake").json()

    assert default == client.get("/api/patients/NS03/intake", params={"days": 14}).json()


@pytest.mark.parametrize(("days", "start"), [(1, "2026-12-05"), (60, "2026-10-07")])
def test_intake_accepts_range_bounds(client: TestClient, days: int, start: str) -> None:
    response = client.get("/api/patients/NS03/intake", params={"days": days})

    assert response.status_code == 200
    assert response.json()["period_start"] == start


@pytest.mark.parametrize("days", [0, 61, -1, "abc"])
def test_intake_rejects_days_out_of_range(client: TestClient, days: object) -> None:
    response = client.get("/api/patients/NS03/intake", params={"days": days})

    assert response.status_code == 422


def test_intake_marks_prescriptions_in_period(client: TestClient, scratch: ScratchRows) -> None:
    _add_prescription(scratch, "rx_in", "2026-12-03T10:00:00.000000")
    _add_prescription(scratch, "rx_old", "2026-11-01T08:00:00.500000")

    recent = client.get("/api/patients/NS03/intake", params={"days": 14}).json()
    wide = client.get("/api/patients/NS03/intake", params={"days": 60}).json()

    assert recent["prescriptions"] == [
        {"prescription_id": "rx_in", "confirmed_at": "2026-12-03T10:00:00.000000"}
    ]
    assert wide["prescriptions"] == [
        {"prescription_id": "rx_old", "confirmed_at": "2026-11-01T08:00:00.500000"},
        {"prescription_id": "rx_in", "confirmed_at": "2026-12-03T10:00:00.000000"},
    ]


# 경고 ----------------------------------------------------------------------


def test_alert_returns_latest_judgement(client: TestClient, scratch: ScratchRows) -> None:
    _add_caution_alert(scratch)

    response = client.get("/api/patients/NS03/alert")

    assert response.status_code == 200
    assert response.json() == {
        "alert_id": CAUTION_ALERT_ID,
        "evaluated_at": "2026-12-05T23:59:59",
        "level": "caution",
        "nutrients": ["protein"],
        "period_start": "2026-11-29",
        "period_end": "2026-12-05",
        "evidence": [{"nutrient": "protein", "avg_pct": 61.5, "low_days_streak": 3}],
        "unrecorded_meals": 2,
    }


def test_alert_without_basis_period_has_null_period(client: TestClient) -> None:
    body = client.get("/api/patients/NS01/alert").json()

    assert body["alert_id"] == "alert_NS01_2026-12-04"
    assert body["level"] == "none"
    assert (body["period_start"], body["period_end"]) == (None, None)
    assert body["evidence"] == []
    assert body["nutrients"] == []


def test_alert_is_null_without_judgement(client: TestClient, scratch: ScratchRows) -> None:
    _add_new_patient(scratch)

    response = client.get(f"/api/patients/{NEW_PATIENT}/alert")

    assert response.status_code == 200
    assert response.json() is None


# 추천 카드 -----------------------------------------------------------------


def test_recommendation_is_null_without_card(client: TestClient) -> None:
    response = client.get("/api/patients/NS01/recommendation")

    assert response.status_code == 200
    assert response.json() is None


def test_recommendation_keeps_stored_timestamps(client: TestClient, scratch: ScratchRows) -> None:
    scratch.add(
        insert_recommendation,
        "recommendations",
        "recommendation_id",
        recommendation_id=CARD_ID,
        patient_id="NS05",
        items=items_to_json((AGENT_ITEM, DOCTOR_ITEM)),
        cautions='["신장 기능 확인"]',
        created_at=CREATED_AT,
        updated_at=UPDATED_AT,
    )

    response = client.get("/api/patients/NS05/recommendation")

    assert response.status_code == 200
    assert response.json() == {
        "recommendation_id": CARD_ID,
        "patient_id": "NS05",
        "alert_id": None,
        "items": [
            {
                "item_id": "rx1",
                "type": "food_fortification",
                "title": "식사 강화 7일",
                "detail": "단백질 반찬 강화로 에너지·단백질 밀도 높이기",
                "duration_days": 7,
                "review_date": None,
                "added_by": "agent",
                "evidence": [
                    {"doc_id": "espen_geriatrics", "section": "R20"},
                    {"doc_id": "espen_geriatrics", "section": "R23"},
                ],
            },
            {
                "item_id": "rx2",
                "type": "monitoring_review",
                "title": "재평가",
                "detail": "",
                "duration_days": None,
                "review_date": "2026-12-04",
                "added_by": "doctor",
                "evidence": [],
            },
        ],
        "cautions": ["신장 기능 확인"],
        "last_modified_by": "agent",
        "thread_id": None,
        "created_at": CREATED_AT,
        "updated_at": UPDATED_AT,
        "status": "active",
    }


# 라우터 등록 ---------------------------------------------------------------


def test_openapi_lists_patient_read_paths(client: TestClient) -> None:
    paths = client.app.openapi()["paths"]

    assert {
        "/api/patients",
        "/api/patients/{patient_id}",
        "/api/patients/{patient_id}/intake",
        "/api/patients/{patient_id}/alert",
        "/api/patients/{patient_id}/recommendation",
    } <= set(paths)


@pytest.fixture
def spa_client(tmp_path: Path, seeded_db: Path) -> Iterator[TestClient]:
    """프론트엔드 빌드(`index.html`)를 둔 앱. SPA 대체 응답이 켜져 있다."""
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text(INDEX_HTML, encoding="utf-8")
    settings: Settings = make_api_settings(tmp_path / "spa", seeded_db, frontend_dist=dist)
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def test_api_routes_win_over_spa_fallback(spa_client: TestClient) -> None:
    listed = spa_client.get("/api/patients", headers=HTML)
    missing = spa_client.get("/api/patients/XX", headers=HTML)

    assert spa_client.get("/some-screen", headers=HTML).text == INDEX_HTML
    assert listed.status_code == 200
    assert len(listed.json()) == 10
    assert missing.status_code == 404
    assert missing.headers["content-type"].startswith("application/json")
    assert "XX" in missing.json()["detail"]
