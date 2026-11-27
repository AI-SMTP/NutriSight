"""FastAPI 앱 진입점. `fastapi dev`는 이 모듈의 `app`을 찾는다."""

from __future__ import annotations

from fastapi import FastAPI


def create_app() -> FastAPI:
    """화면 4개가 공유하는 HTTP API 앱을 만든다."""
    application = FastAPI(title="NutriSight")

    @application.get("/api/health")
    def health() -> dict[str, str]:
        """서버가 응답하는지 확인한다."""
        return {"status": "ok"}

    return application


app = create_app()
