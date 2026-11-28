"""빌드된 프론트엔드 정적 제공과 SPA 대체 응답 테스트.

`docs/specs/frontend-shell-upload.md` '정적 제공과 SPA 대체 응답'의 응답 표와 정책을 검증한다.

`TestClient(app)`를 `with` 없이 써서 lifespan(앱 잠금·자동 시드)을 건너뛴다. 정적 등록은
`create_app()` 안에서 하므로 lifespan 없이도 검증된다.
"""

from __future__ import annotations

import logging
import shutil
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import API_PREFIX, create_app

INDEX_HTML = "<!doctype html><title>NutriSight</title><div id=root></div>"
APP_JS = b"console.info('app');"
FAVICON = b"\x00\x00\x01\x00fake-icon"
SECRET = "outside-dist-secret"
HTML = {"Accept": "text/html"}
ANY = {"Accept": "*/*"}


def _make_dist(root: Path) -> Path:
    """`index.html`, `assets/app.js`, `favicon.ico`를 가진 가짜 `dist`를 만든다."""
    dist = root / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(INDEX_HTML, encoding="utf-8")
    (dist / "assets" / "app.js").write_bytes(APP_JS)
    (dist / "favicon.ico").write_bytes(FAVICON)
    return dist


def _app(dist: Path) -> FastAPI:
    """`frontend_dist`만 바꾼 설정으로 앱을 만든다."""
    return create_app(Settings(_env_file=None, frontend_dist=dist))


def _app_with_probe(dist: Path) -> FastAPI:
    """앱을 만든 뒤 POST 전용 `/api/_probe` 라우트를 등록한다."""
    application = _app(dist)

    @application.post("/api/_probe")
    def probe() -> dict[str, str]:
        return {"probe": "ok"}

    return application


def _assert_index(response: httpx.Response) -> None:
    assert response.status_code == 200
    assert response.text == INDEX_HTML
    assert response.headers["content-type"].startswith("text/html")


def _assert_json_404(response: httpx.Response) -> None:
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"detail": "Not Found"}


def _info_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    """`app.main` 로거의 INFO 기록만 고른다."""
    return [
        record
        for record in caplog.records
        if record.name == "app.main" and record.levelno == logging.INFO
    ]


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    return TestClient(_app_with_probe(_make_dist(tmp_path)))


@pytest.mark.parametrize(
    ("path", "headers"),
    [("/post-meal", HTML), ("/baseline/extra", HTML), ("/", ANY), ("/", HTML)],
)
def test_index_is_returned_for_root_and_client_routes(
    client: TestClient, path: str, headers: dict[str, str]
) -> None:
    _assert_index(client.get(path, headers=headers))


@pytest.mark.parametrize(
    ("path", "expected_bytes"), [("/assets/app.js", APP_JS), ("/favicon.ico", FAVICON)]
)
def test_existing_file_is_served(client: TestClient, path: str, expected_bytes: bytes) -> None:
    response = client.get(path, headers=ANY)

    assert response.status_code == 200
    assert response.content == expected_bytes


@pytest.mark.parametrize(
    ("path", "headers"),
    [
        ("/assets/missing.js", ANY),
        ("/post-meal", ANY),
        ("/api/missing", HTML),
        ("/api/missing", ANY),
    ],
)
def test_non_fallback_requests_get_json_404(
    client: TestClient, path: str, headers: dict[str, str]
) -> None:
    _assert_json_404(client.get(path, headers=headers))


@pytest.mark.parametrize(
    ("method", "path", "allow"), [("GET", "/api/_probe", "POST"), ("POST", "/api/health", "GET")]
)
def test_api_method_mismatch_is_405(client: TestClient, method: str, path: str, allow: str) -> None:
    response = client.request(method, path, headers=HTML)

    assert response.status_code == 405
    assert response.headers["allow"] == allow


def test_health_still_returns_ok(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_head_client_route_html_request_is_200(client: TestClient) -> None:
    response = client.head("/post-meal", headers=HTML)

    assert response.status_code == 200
    assert response.content == b""
    assert response.headers["content-type"].startswith("text/html")


def test_post_client_route_gets_no_index_fallback(client: TestClient) -> None:
    _assert_json_404(client.post("/post-meal", headers=HTML))


@pytest.fixture
def traversal_client(tmp_path: Path) -> TestClient:
    """`dist` 밖에 비밀 파일과, 그 파일·상위 디렉토리를 가리키는 심볼릭 링크를 둔 앱."""
    dist = _make_dist(tmp_path)
    secret = tmp_path / "secret.txt"
    secret.write_text(SECRET, encoding="utf-8")
    (dist / "leak.txt").symlink_to(secret)
    (dist / "assets" / "up").symlink_to(tmp_path, target_is_directory=True)
    return TestClient(_app_with_probe(dist))


@pytest.mark.parametrize(
    "path",
    [
        "/..%2Fsecret.txt",
        "/%2e%2e/secret.txt",
        "/assets/..%2F..%2Fsecret.txt",
        "/leak.txt",
        "/assets/up/secret.txt",
    ],
)
@pytest.mark.parametrize(
    ("headers", "check"), [(ANY, _assert_json_404), (HTML, _assert_index)], ids=["any", "html"]
)
def test_path_traversal_does_not_escape_dist(
    traversal_client: TestClient,
    path: str,
    headers: dict[str, str],
    check: Callable[[httpx.Response], None],
) -> None:
    response = traversal_client.get(path, headers=headers)

    check(response)
    assert SECRET not in response.text


def test_dist_without_assets_starts_and_serves_index(tmp_path: Path) -> None:
    dist = _make_dist(tmp_path)
    shutil.rmtree(dist / "assets")
    client = TestClient(_app_with_probe(dist))

    _assert_index(client.get("/", headers=ANY))
    _assert_index(client.get("/post-meal", headers=HTML))
    _assert_json_404(client.get("/assets/app.js", headers=ANY))
    assert client.get("/api/health").status_code == 200


def test_openapi_paths_exclude_static_routes(tmp_path: Path) -> None:
    application = _app_with_probe(_make_dist(tmp_path))

    paths = set(application.openapi()["paths"])

    assert {"/api/health", "/api/_probe"} <= paths
    assert all(path.startswith(f"{API_PREFIX}/") for path in paths)


def test_index_removed_after_startup_falls_back_to_json_404(tmp_path: Path) -> None:
    dist = _make_dist(tmp_path)
    client = TestClient(_app_with_probe(dist), raise_server_exceptions=False)
    (dist / "index.html").unlink()

    _assert_json_404(client.get("/post-meal", headers=HTML))


def _no_dist(root: Path) -> Path:
    """존재하지 않는 `dist` 경로."""
    return root / "no-dist"


def _dist_without_index(root: Path) -> Path:
    """`assets/app.js`만 있고 `index.html`이 없는 `dist`."""
    dist = root / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "assets" / "app.js").write_bytes(APP_JS)
    return dist


@pytest.mark.parametrize("build_dist", [_no_dist, _dist_without_index], ids=["missing", "no-index"])
def test_static_serving_is_disabled_without_index_and_logs_info(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    build_dist: Callable[[Path], Path],
) -> None:
    dist = build_dist(tmp_path)

    with caplog.at_level(logging.INFO, logger="app.main"):
        client = TestClient(_app(dist))

    _assert_json_404(client.get("/", headers=HTML))
    _assert_json_404(client.get("/post-meal", headers=HTML))
    _assert_json_404(client.get("/assets/app.js", headers=ANY))
    records = _info_records(caplog)
    assert len(records) == 1
    assert str(dist) in records[0].getMessage()
