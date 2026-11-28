"""환자 라우터 (스펙 3.3: 목록·요약·섭취 추이·경고·추천 카드·다시 만들기·처방 작성·이력).

다시 만들기만 `async def`다. 생성 서비스 `create_recommendation(mode="manual")`을 기다리며, 그
서비스가 앱 소유 태스크에서 잠금·생성기 대기·저장·발행까지 끝낸다(스펙 3.5). 나머지는 `def`
라우터다(FastAPI 스레드풀). 읽기는 그 요청 스레드에서 `read_db`(`run_in_db(…, mode="read")`)로,
처방 작성은 `write_db`(쓰기 실행기)로 실행한다. DB 경로와 판단 엔진은 `deps(request)`에서 읽는다.
서비스 예외는 `read_db`·`write_db`·`http_errors`가 상태 코드로 바꾼다(`app/api/deps.py`).
처방은 확정 뒤 바꾸지 않으므로 처방 수정·삭제 경로는 두지 않는다.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Request, status

from app.api.deps import deps, read_db, write_db
from app.api.errors import http_errors
from app.api.schemas import (
    AlertOut,
    IntakeTrend,
    PatientDetail,
    PatientListItem,
    PrescriptionCreate,
    PrescriptionOut,
    RecommendationOut,
)
from app.services.generation import create_recommendation
from app.services.patients import (
    alert_for_patient,
    intake_trend,
    list_patients_with_alert,
    patient_detail,
)
from app.services.prescriptions import create_prescription, list_prescriptions
from app.services.recommendations import current_card

INTAKE_DAYS_DEFAULT = 14
INTAKE_DAYS_MIN = 1
INTAKE_DAYS_MAX = 60

router = APIRouter(prefix="/api", tags=["patients"])


@router.get("/patients")
def list_patients(request: Request) -> list[PatientListItem]:
    """모든 환자와 시연일 이하 최신 판정 수준, `patient_id` 순."""
    entries = read_db(request, list_patients_with_alert)
    return [PatientListItem.model_validate(e) for e in entries]


@router.get("/patients/{patient_id}")
def get_patient(request: Request, patient_id: str) -> PatientDetail:
    """환자 요약. 없는 환자 → 404."""
    engine = deps(request).engine
    view = read_db(request, lambda conn: patient_detail(conn, engine, patient_id))
    return PatientDetail.model_validate(view)


@router.get("/patients/{patient_id}/intake")
def get_intake(
    request: Request,
    patient_id: str,
    days: Annotated[int, Query(ge=INTAKE_DAYS_MIN, le=INTAKE_DAYS_MAX)] = INTAKE_DAYS_DEFAULT,
) -> IntakeTrend:
    """시연일을 끝으로 하는 `days`일(1~60, 기본 14) 섭취 추이. 없는 환자 → 404."""
    engine = deps(request).engine
    view = read_db(request, lambda conn: intake_trend(conn, engine, patient_id, days))
    return IntakeTrend.model_validate(view)


@router.get("/patients/{patient_id}/alert")
def get_alert(request: Request, patient_id: str) -> AlertOut | None:
    """시연일 이하 최신 판정. 판정이 없으면 null, 없는 환자 → 404."""
    row = read_db(request, lambda conn: alert_for_patient(conn, patient_id))
    return None if row is None else AlertOut.from_row(row)


@router.get("/patients/{patient_id}/recommendation")
def get_recommendation(request: Request, patient_id: str) -> RecommendationOut | None:
    """현재 추천 카드(`active`·`failed` 중 가장 늦은 것). 없으면 null, 없는 환자 → 404."""
    card = read_db(request, lambda conn: current_card(conn, patient_id))
    return None if card is None else RecommendationOut.model_validate(card)


@router.post(
    "/patients/{patient_id}/recommendation/regenerate", status_code=status.HTTP_201_CREATED
)
async def regenerate_recommendation(request: Request, patient_id: str) -> RecommendationOut:
    """추천 카드를 새로 만든다(`manual`: 판정과 상관없이 항상).

    이전 `active`·`failed` 카드는 `superseded`가 된다. 생성기가 실패하면 201 `failed` 카드,
    경고가 없는 환자는 `alert_id = null` 카드다. 없는 환자 → 404, 저장 실패 → 500(이벤트 없음).
    """
    with http_errors():
        card = await create_recommendation(patient_id, mode="manual", deps=deps(request))
    return RecommendationOut.model_validate(card)


@router.post("/patients/{patient_id}/prescriptions", status_code=status.HTTP_201_CREATED)
def post_prescription(
    request: Request, patient_id: str, body: PrescriptionCreate
) -> PrescriptionOut:
    """추천 없이 처방을 만든다(`recommendation_id = null`, 항목 `added_by = doctor`).

    그 환자의 추천 카드는 건드리지 않는다. 빈 `items`·항목 규칙 위반 422, 없는 환자 404.
    """
    clock = deps(request).runtime.clock
    edits = body.edits()
    record = write_db(
        request, lambda conn: create_prescription(conn, patient_id, edits, now=clock.now())
    )
    return PrescriptionOut.model_validate(record)


@router.get("/patients/{patient_id}/prescriptions")
def get_prescriptions(request: Request, patient_id: str) -> list[PrescriptionOut]:
    """그 환자의 처방 이력, 확정 시각 내림차순. 없는 환자 → 404."""
    records = read_db(request, lambda conn: list_prescriptions(conn, patient_id))
    return [PrescriptionOut.model_validate(r) for r in records]
