"""OpenAPI 내보내기 CLI(`scripts.export_openapi`) 테스트.

같은 앱이면 내보낸 바이트가 매번 같고, 키가 정렬되며, `/api/health`가 들어 있는지 확인한다.
파일은 `tmp_path`에만 쓴다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.config import REPO_ROOT
from scripts import export_openapi as export_cli


def test_export_is_byte_identical_across_runs(tmp_path: Path) -> None:
    first = export_cli.export_openapi(tmp_path / "a" / "openapi.json")
    second = export_cli.export_openapi(tmp_path / "b" / "openapi.json")

    assert first.read_bytes() == second.read_bytes()


def test_export_contains_health_path_with_sorted_keys(tmp_path: Path) -> None:
    out = export_cli.export_openapi(tmp_path / "openapi.json")
    text = out.read_text(encoding="utf-8")
    spec = json.loads(text)

    assert "/api/health" in spec["paths"]
    assert text == json.dumps(spec, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def test_export_creates_missing_parent_directories(tmp_path: Path) -> None:
    out = tmp_path / "nested" / "deeper" / "openapi.json"

    assert export_cli.export_openapi(out) == out
    assert out.is_file()


def test_main_writes_to_out_argument(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "x.json"

    assert export_cli.main(["--out", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["openapi"]
    assert str(out) in capsys.readouterr().out


def test_default_out_path_is_frontend_generated_dir() -> None:
    relative = export_cli.DEFAULT_OUT_PATH.relative_to(REPO_ROOT)

    assert relative.as_posix() == "frontend/src/api/generated/openapi.json"


def test_main_reports_config_error_with_exit_code_1(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("INTAKE_ADAPTER", "bogus")
    out = tmp_path / "x.json"

    assert export_cli.main(["--out", str(out)]) == 1
    assert not out.exists()
    assert "설정 오류" in capsys.readouterr().err


def test_export_ignores_frontend_dist_setting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline = export_cli.export_openapi(tmp_path / "base.json").read_bytes()
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html>", encoding="utf-8")
    monkeypatch.setenv("FRONTEND_DIST", str(dist))

    assert export_cli.export_openapi(tmp_path / "with_dist.json").read_bytes() == baseline
