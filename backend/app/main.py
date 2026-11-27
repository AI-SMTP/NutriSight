"""FastAPI 앱 진입점. `fastapi dev`는 이 모듈의 `app`을 찾는다.

모듈 수준 `app = create_app()`은 import만으로 잠금을 잡거나 파일을 만들지 않는다. 시연일 검사,
앱 잠금, 자동 시드는 lifespan에서만 일어난다(스펙 3.8).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import date

from fastapi import FastAPI

from app.config import Settings, resolve_demo_date, storage_paths
from app.storage.app_lock import AppLock
from app.storage.seed import ensure_storage
from app.wiring import build_components

Lifespan = Callable[[FastAPI], AbstractAsyncContextManager[None]]


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


def create_app(settings: Settings | None = None) -> FastAPI:
    """화면 4개가 공유하는 HTTP API 앱을 만든다.

    시작할 때 설정으로 네 계약의 구현을 만들어 `app.state`에 둔다.
    등록되지 않은 구현 이름이면 `ConfigError`를 던진다. 저장소 준비는 lifespan이 한다.
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

    return application


app = create_app()
