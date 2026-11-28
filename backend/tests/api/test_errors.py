"""라우터 예외 변환 도우미 테스트 (스펙 3.3 오류 코드)."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api.errors import http_errors
from app.services.ports import (
    PatientNotFoundError,
    RecommendationNotEditableError,
    RecommendationNotFoundError,
)
from app.services.recommendations import StaleRecommendationError, UnknownItemError


@pytest.mark.parametrize(
    ("error", "status", "detail"),
    [
        (PatientNotFoundError("환자가 없다: XX"), 404, "환자가 없다: XX"),
        (RecommendationNotFoundError("카드가 없다: R1"), 404, "카드가 없다: R1"),
        (RecommendationNotEditableError("확정된 카드"), 409, "not_editable"),
        (StaleRecommendationError("시각 불일치"), 409, "stale"),
        (UnknownItemError("없는 항목: rx9"), 422, "없는 항목: rx9"),
    ],
)
def test_domain_errors_become_http_errors(error: Exception, status: int, detail: str) -> None:
    with pytest.raises(HTTPException) as caught, http_errors():
        raise error

    assert caught.value.status_code == status
    assert caught.value.detail == detail
    assert caught.value.__cause__ is error


def test_other_errors_pass_through() -> None:
    with pytest.raises(ValueError, match="그대로"), http_errors():
        raise ValueError("그대로")


def test_no_error_passes() -> None:
    with http_errors():
        result = 1

    assert result == 1
