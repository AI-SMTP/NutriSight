"""FastAPI 앱 진입점. `fastapi dev`는 이 모듈의 `app`을 찾는다.

모듈 수준 `app = create_app()`은 import만으로 잠금을 잡거나 파일을 만들지 않는다. 시연일 검사,
앱 잠금, 자동 시드는 lifespan에서만 일어난다(스펙 3.8).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import FileResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import Settings, resolve_demo_date, storage_paths
from app.storage.app_lock import AppLock
from app.storage.seed import ensure_storage
from app.wiring import build_components

logger = logging.getLogger(__name__)

Lifespan = Callable[[FastAPI], AbstractAsyncContextManager[None]]

API_PREFIX = "/api"
INDEX_FILE = "index.html"
_SPA_FALLBACK_METHODS = frozenset({"GET", "HEAD"})


def _make_lifespan(settings: Settings) -> Lifespan:
    """시연일 형식 검사 → 앱 잠금 → `ensure_storage` → 서비스 → 잠금 해제 순서의 lifespan.

    형식 오류(`ConfigError`)는 잠금 파일을 만들기 전에 낸다. 잠금을 잡은 뒤 실패하면 잠금을 놓고
    예외를 그대로 전달해 앱 시작을 멈춘다. 시작 단계는 요청을 받기 전이라 동기 파일·DB 작업을
    이벤트 루프에서 바로 실행해도 막히는 요청이 없으므로 스레드로 넘기지 않는다.
    """

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        resolve_demo_date(None, settings, date.today())
        lock = AppLock(storage_paths(settings).app_lock)
        lock.acquire()
        try:
            ensure_storage(settings)
            yield
        finally:
            lock.release()

    return lifespan


def _wants_spa_fallback(request: Request) -> bool:
    """SPA 대체 응답 대상인지 판정한다: `/api` 밖, GET·HEAD, `Accept`에 `text/html`(스펙 3.8)."""
    path = request.url.path
    is_api = path == API_PREFIX or path.startswith(f"{API_PREFIX}/")
    return (
        not is_api
        and request.method in _SPA_FALLBACK_METHODS
        and "text/html" in request.headers.get("accept", "")
    )


def _register_frontend(application: FastAPI, frontend_dist: Path) -> None:
    """`frontend_dist/index.html`이 있으면 빌드 결과를 `/`에서 제공하고 404 대체 응답을 건다.

    정적 파일은 FastAPI 내장 `frontend()`로 대체 응답 없이(`fallback=None`) 등록한다. 일반
    라우트가 먼저 확인되므로 API의 405와 JSON 404는 그대로 남는다. 대체 응답은 라우팅·정적
    파일 결과가 404일 때만 `_wants_spa_fallback`을 보고 `index.html`을 준다. 파일 경로 검사
    (`dist` 밖 접근 차단)는 Starlette `StaticFiles`가 한다. 정적 경로는 OpenAPI에 들어가지 않는다.

    404 처리기는 앱 전역 `StarletteHTTPException` 처리기다. 나중에 같은 예외의 처리기를 등록하면
    서로 덮어쓰므로 `create_app` 끝(모든 라우트·처리기 등록 뒤)에서 부른다. `Accept` 판정은
    스펙 3.8절대로 `text/html` 부분 문자열 포함 여부만 보고 q값은 해석하지 않는다.
    """
    dist = frontend_dist.resolve()
    index = dist / INDEX_FILE
    if not index.is_file():
        logger.info("프론트엔드 빌드(index.html)가 없어 정적 제공을 등록하지 않는다: %s", dist)
        return
    application.frontend("/", directory=dist, fallback=None)

    async def spa_not_found(request: Request, exc: StarletteHTTPException) -> Response:
        """404이고 대체 응답 대상이면 `index.html`, 아니면 기본 HTTP 오류 응답을 돌려준다.

        시작 뒤 `index.html`이 사라졌으면(다시 빌드하는 중 등) 500 대신 기본 404로 넘긴다.
        """
        if exc.status_code == 404 and _wants_spa_fallback(request) and index.is_file():
            return FileResponse(index)
        return await http_exception_handler(request, exc)

    application.add_exception_handler(StarletteHTTPException, spa_not_found)


def create_app(settings: Settings | None = None) -> FastAPI:
    """화면 4개가 공유하는 HTTP API 앱을 만든다.

    시작할 때 설정으로 네 계약의 구현을 만들어 `app.state`에 둔다.
    등록되지 않은 구현 이름이면 `ConfigError`를 던진다. 저장소 준비는 lifespan이 한다.
    `frontend_dist`에 빌드 결과가 있으면 정적 제공과 SPA 대체 응답을 등록한다.
    """
    resolved = settings if settings is not None else Settings()
    components = build_components(resolved)
    application = FastAPI(title="NutriSight", lifespan=_make_lifespan(resolved))
    application.state.intake_estimator = components.intake_estimator
    application.state.nutrition_engine = components.nutrition_engine
    application.state.guideline_search = components.guideline_search
    application.state.patient_data = components.patient_data

    @application.get("/api/health")
    def health() -> dict[str, str]:
        """서버가 응답하는지 확인한다."""
        return {"status": "ok"}

    # 모든 `/api` 라우트를 등록한 뒤에 정적 제공을 건다(스펙 3.8).
    _register_frontend(application, resolved.frontend_dist)
    return application


app = create_app()
