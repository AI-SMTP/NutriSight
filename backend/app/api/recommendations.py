"""추천 카드 수정·확정 라우터 (스펙 3.3 PATCH·confirm, 3.4 낙관적 잠금).

`PATCH /api/recommendations/{id}`는 의사 편집을 병합해 저장하고, `POST …/confirm`은 고른 항목으로
처방을 만든다. 쓰기 경로(쓰기 실행기·커밋 뒤 발행·요청 중단)는 `app/api/deps.py`의
`write_db`를 따른다.
시계 값은 쓰기 실행기 스레드의 트랜잭션 안에서 읽는다.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, status

from app.api.deps import deps, write_db
from app.api.schemas import ConfirmRequest, PrescriptionOut, RecommendationOut, RecommendationPatch
from app.services.recommendations import confirm_recommendation, edit_by_doctor

router = APIRouter(prefix="/api", tags=["recommendations"])


@router.patch("/recommendations/{recommendation_id}")
def patch_recommendation(
    request: Request, recommendation_id: str, body: RecommendationPatch
) -> RecommendationOut:
    """의사 편집을 병합해 저장한다.

    없음 404, active 아님 409 `not_editable`, 시각 불일치 409 `stale`, 항목 규칙 위반 422.
    """
    clock = deps(request).runtime.clock
    edits = body.edits()
    card = write_db(
        request,
        lambda conn: edit_by_doctor(
            conn, recommendation_id, edits, body.expected_updated_at, now=clock.now()
        ),
    )
    return RecommendationOut.model_validate(card)


@router.post("/recommendations/{recommendation_id}/confirm", status_code=status.HTTP_201_CREATED)
def confirm(request: Request, recommendation_id: str, body: ConfirmRequest) -> PrescriptionOut:
    """고른 항목으로 처방을 만들고 카드를 `confirmed`로 바꾼다.

    오류 판정 순서: 빈 `item_ids` 422(요청 검증) → 없음 404 → active 아님 409 → stale 409 →
    카드에 없는 `item_id` 422.
    """
    clock = deps(request).runtime.clock
    item_ids = body.to_item_ids()
    record = write_db(
        request,
        lambda conn: confirm_recommendation(
            conn, recommendation_id, item_ids, body.expected_updated_at, now=clock.now()
        ),
    )
    return PrescriptionOut.model_validate(record)
