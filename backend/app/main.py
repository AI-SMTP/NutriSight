"""FastAPI 앱 진입점. `fastapi dev`는 이 모듈의 `app`을 찾는다.

모듈 수준 `app = create_app()`은 import만으로 잠금을 잡거나 파일을 만들지 않는다. 시연일 검사,
앱 잠금, 자동 시드, 시계 고정, 종료 정책은 lifespan에서만 일어난다(스펙 3.2·3.8).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, AsyncExitStack, asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import FileResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import Settings, StoragePaths, resolve_demo_date, storage_paths
from app.services.generation import PatientLocks, RecommendationDeps
from app.services.runtime import AppRuntime
from app.services.unit_of_work import run_in_db
from app.storage.app_lock import AppLock
from app.storage.queries import get_demo_date
from app.storage.seed import ensure_storage
from app.wiring import build_components

logger = logging.getLogger(__name__)

Lifespan = Callable[[FastAPI], AbstractAsyncContextManager[None]]

API_PREFIX = "/api"
INDEX_FILE = "index.html"
_SPA_FALLBACK_METHODS = frozenset({"GET", "HEAD"})
ALREADY_STARTED_MESSAGE = "앱 인스턴스는 한 번만 시작한다"


def _make_lifespan(settings: Settings, runtime: AppRuntime, paths: StoragePaths) -> Lifespan:
    """시연일 형식 검사 → 앱 잠금 → `ensure_storage` → 버스 루프 묶기 → 시계 고정 → 서비스 →
    런타임 종료 → 잠금 해제 순서의 lifespan.

    형식 오류(`ConfigError`)는 잠금 파일을 만들기 전에 낸다. 시계는 `seed_meta.demo_date`와 오늘
    날짜의 차이로 고정한다(설정 시연일이 아니라 DB에 적재된 시연일). 잠금을 잡은 뒤에는 시작
    실패든 정상 종료든 런타임을 먼저 닫고(`AppRuntime.aclose`, 스펙 3.2 종료 정책) 잠금을 놓는다.
    런타임 종료가 실패해도 잠금은 놓는다. 그래서 실행 중인 DB 쓰기가 끝나기 전에는 리셋 CLI가
    잠금을 잡지 못한다. 시작 실패 예외는 그대로 전달해 앱 시작을 멈춘다.

    런타임이 이미 닫힌 앱(종료했거나 잠금을 잡은 뒤 시작에 실패한 앱)으로 다시 시작하면 잠금을
    잡기 전에 `RuntimeError`를 낸다(새 앱은 `create_app`으로 만든다). 잠금을 잡기 전 실패(형식
    오류·잠금 충돌)는 런타임을 닫지 않으므로 같은 앱으로 다시 시작할 수 있다. 시작 단계는 요청을
    받기 전이라 동기 파일·DB 작업을 이벤트 루프에서 바로 실행해도 막히는 요청이 없으므로 스레드로
    넘기지 않는다.
    """

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        if runtime.closed:
            raise RuntimeError(ALREADY_STARTED_MESSAGE)
        today = date.today()
        resolve_demo_date(None, settings, today)
        lock = AppLock(paths.app_lock)
        lock.acquire()
        # 정리는 등록 역순이다: 런타임 종료 → 잠금 해제. 종료가 실패해도 잠금 해제는 실행된다.
        async with AsyncExitStack() as cleanup:
            cleanup.callback(lock.release)
            cleanup.push_async_callback(runtime.aclose)
            ensure_storage(settings)
            runtime.bus.bind_loop(asyncio.get_running_loop())
            demo_date = run_in_db(paths.app_db, get_demo_date, mode="read")
            runtime.clock.anchor(demo_date, today)
            yield

    return lifespan


def _wants_spa_fallback(request: Request) -> bool:
    """SPA 대체 응답 대상인지 판정한다: `/api` 밖, GET·HEAD, `Accept`에 `text/html`."""
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
    설계상(`docs/specs/frontend-shell-upload.md` '정적 제공과 SPA 대체 응답') `text/html`
    부분 문자열 포함 여부만 보고 q값은 해석하지 않는다.
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

    맨 먼저 앱 런타임(버스·태스크·쓰기 실행기·고정 전 시계)을 만들고, 설정으로 다섯 계약의
    구현을 만들어 `app.state`에 둔다. 포트와 추천 의존성은 같은 런타임을 쓴다(스펙 3.8 등록 경로).
    런타임과 구현 생성은 파일을 만들지 않는다. 등록되지 않은 구현 이름이면 `ConfigError`를 던진다.
    저장소 준비와 시계 고정은 lifespan이 한다. `frontend_dist`에 빌드 결과가 있으면 정적 제공과
    SPA 대체 응답을 등록한다.
    """
    resolved = settings if settings is not None else Settings()
    paths = storage_paths(resolved)
    runtime = AppRuntime.create(paths.app_db)
    components = build_components(resolved, runtime)
    application = FastAPI(title="NutriSight", lifespan=_make_lifespan(resolved, runtime, paths))
    application.state.runtime = runtime
    application.state.event_bus = runtime.bus
    application.state.intake_estimator = components.intake_estimator
    application.state.nutrition_engine = components.nutrition_engine
    application.state.guideline_search = components.guideline_search
    application.state.patient_data = components.patient_data
    application.state.recommendation_generator = components.recommendation_generator
    application.state.recommendation_deps = RecommendationDeps(
        generator=components.recommendation_generator,
        runtime=runtime,
        db_path=paths.app_db,
        engine=components.nutrition_engine,
        locks=PatientLocks(),
        timeout_s=resolved.recommendation_timeout_s,
    )

    @application.get("/api/health")
    def health() -> dict[str, str]:
        """서버가 응답하는지 확인한다."""
        return {"status": "ok"}

    # 모든 `/api` 라우트를 등록한 뒤에 정적 제공을 건다(참조 문서 '정적 제공과 SPA 대체 응답').
    _register_frontend(application, resolved.frontend_dist)
    return application


app = create_app()
