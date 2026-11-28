"""서비스 예외를 HTTP 오류로 바꾸는 라우터 도우미 (스펙 3.3 오류 코드).

전역 예외 처리기를 두지 않고 각 라우터가 `with http_errors():` 안에서 서비스를 부른다.
409의 `detail`은 화면이 구분하는 고정 값 `"stale"`·`"not_editable"`이다. 그 밖의 예외는
그대로 올린다(FastAPI가 500으로 응답한다).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import HTTPException, status

from app.services.ports import (
    PatientNotFoundError,
    RecommendationNotEditableError,
    RecommendationNotFoundError,
)
from app.services.recommendations import StaleRecommendationError, UnknownItemError

STALE_DETAIL = "stale"
NOT_EDITABLE_DETAIL = "not_editable"


@contextmanager
def http_errors() -> Iterator[None]:
    """블록 안 서비스 예외를 `HTTPException`으로 바꾼다. 원래 예외는 `__cause__`로 남긴다."""
    try:
        yield
    except (PatientNotFoundError, RecommendationNotFoundError) as err:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(err)) from err
    except RecommendationNotEditableError as err:
        raise HTTPException(status.HTTP_409_CONFLICT, NOT_EDITABLE_DETAIL) from err
    except StaleRecommendationError as err:
        raise HTTPException(status.HTTP_409_CONFLICT, STALE_DETAIL) from err
    except UnknownItemError as err:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(err)) from err
