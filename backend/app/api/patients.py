"""환자 조회 라우터 (스펙 3.3: 목록·요약·섭취 추이·경고·추천 카드).

모든 조회는 `def` 라우터다(FastAPI 스레드풀). 연결은 그 요청 스레드에서
`run_in_db(…, mode="read")`로 열고 닫는다. 연결용 `Depends`는 쓰지 않는다(yield 의존성은
라우터와 다른 스레드에서 돌 수 있다). DB 경로와 판단 엔진은 `app.state.recommendation_deps`에서
읽는다. 서비스 예외는 `http_errors`가 상태 코드로 바꾼다.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Query, Request

from app.api.errors import http_errors
from app.api.schemas import (
    AlertOut,
    IntakeTrend,
    PatientDetail,
    PatientListItem,
    RecommendationOut,
)
from app.services.generation import RecommendationDeps
from app.services.patients import (
    alert_for_patient,
    intake_trend,
    list_patients_with_alert,
    patient_detail,
)
from app.services.recommendations import current_card
from app.services.unit_of_work import run_in_db

INTAKE_DAYS_DEFAULT = 14
INTAKE_DAYS_MIN = 1
INTAKE_DAYS_MAX = 60

router = APIRouter(prefix="/api", tags=["patients"])


def _deps(request: Request) -> RecommendationDeps:
    """앱의 추천 의존성. 라우터가 쓰는 DB 경로·판단 엔진·런타임(조회·쓰기 의존성)의 단일 출처다."""
    return request.app.state.recommendation_deps


def _read[T](request: Request, fn: Callable[[sqlite3.Connection], T]) -> T:
    """요청 스레드에서 읽기 연결로 `fn`을 실행하고, 서비스 예외를 HTTP 오류로 바꾼다."""
    with http_errors():
        return run_in_db(_deps(request).db_path, fn, mode="read")


@router.get("/patients")
def list_patients(request: Request) -> list[PatientListItem]:
    """모든 환자와 시연일 이하 최신 판정 수준, `patient_id` 순."""
    entries = _read(request, list_patients_with_alert)
    return [PatientListItem.model_validate(e) for e in entries]


@router.get("/patients/{patient_id}")
def get_patient(request: Request, patient_id: str) -> PatientDetail:
    """환자 요약. 없는 환자 → 404."""
    engine = _deps(request).engine
    view = _read(request, lambda conn: patient_detail(conn, engine, patient_id))
    return PatientDetail.model_validate(view)


@router.get("/patients/{patient_id}/intake")
def get_intake(
    request: Request,
    patient_id: str,
    days: Annotated[int, Query(ge=INTAKE_DAYS_MIN, le=INTAKE_DAYS_MAX)] = INTAKE_DAYS_DEFAULT,
) -> IntakeTrend:
    """시연일을 끝으로 하는 `days`일(1~60, 기본 14) 섭취 추이. 없는 환자 → 404."""
    engine = _deps(request).engine
    view = _read(request, lambda conn: intake_trend(conn, engine, patient_id, days))
    return IntakeTrend.model_validate(view)


@router.get("/patients/{patient_id}/alert")
def get_alert(request: Request, patient_id: str) -> AlertOut | None:
    """시연일 이하 최신 판정. 판정이 없으면 null, 없는 환자 → 404."""
    row = _read(request, lambda conn: alert_for_patient(conn, patient_id))
    return None if row is None else AlertOut.from_row(row)


@router.get("/patients/{patient_id}/recommendation")
def get_recommendation(request: Request, patient_id: str) -> RecommendationOut | None:
    """현재 추천 카드(`active`·`failed` 중 가장 늦은 것). 없으면 null, 없는 환자 → 404."""
    card = _read(request, lambda conn: current_card(conn, patient_id))
    return None if card is None else RecommendationOut.model_validate(card)
