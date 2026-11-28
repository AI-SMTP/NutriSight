"""라우터가 함께 쓰는 앱 의존성·DB 실행 도우미 (스펙 3.2 동기 라우터 경로).

연결용 `Depends`는 쓰지 않는다(yield 의존성은 라우터와 다른 스레드에서 돌 수 있다). 읽기는 요청
스레드에서 `run_in_db(…, mode="read")`로, 쓰기는 `runtime.writer.run_sync`로 쓰기 실행기 스레드에서
실행한다. 이벤트는 쓰기 실행기 작업이 커밋 직후 발행하므로 라우터는 발행하지 않는다. 두 도우미 모두
서비스 예외를 `http_errors`로 상태 코드로 바꾼다.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable

from fastapi import Request

from app.api.errors import http_errors
from app.services.generation import RecommendationDeps
from app.services.unit_of_work import WriteResult, run_in_db


def deps(request: Request) -> RecommendationDeps:
    """앱의 추천 의존성. 라우터가 쓰는 DB 경로·판단 엔진·런타임의 단일 출처다."""
    return request.app.state.recommendation_deps


def read_db[T](request: Request, fn: Callable[[sqlite3.Connection], T]) -> T:
    """요청 스레드에서 읽기 연결로 `fn`을 실행하고, 서비스 예외를 HTTP 오류로 바꾼다."""
    with http_errors():
        return run_in_db(deps(request).db_path, fn, mode="read")


def write_db[T](request: Request, fn: Callable[[sqlite3.Connection], WriteResult[T]]) -> T:
    """쓰기 실행기에서 `fn`을 실행해(커밋 → 발행) 결과를 기다리고, 서비스 예외를 HTTP 오류로 바꾼다.

    요청 스레드가 결과를 받기 전에 사라져도 실행 중인 쓰기는 커밋·발행까지 끝난다.
    """
    with http_errors():
        return deps(request).runtime.writer.run_sync(fn)
