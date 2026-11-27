"""FastAPI 앱 진입점. `fastapi dev`는 이 모듈의 `app`을 찾는다."""

from __future__ import annotations

from fastapi import FastAPI

from app.config import Settings
from app.wiring import build_components


def create_app(settings: Settings | None = None) -> FastAPI:
    """화면 4개가 공유하는 HTTP API 앱을 만든다.

    시작할 때 설정으로 네 계약의 구현을 만들어 `app.state`에 둔다.
    등록되지 않은 구현 이름이면 `ConfigError`를 던진다.
    """
    components = build_components(settings if settings is not None else Settings())
    application = FastAPI(title="NutriSight")
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
