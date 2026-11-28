"""OpenAPI 스키마 내보내기 CLI: `uv run python -m scripts.export_openapi [--out PATH]`.

서버를 띄우지 않고 `create_app().openapi()`를 JSON 파일로 쓴다. 프론트엔드의 `pnpm gen:api`가
이 파일로 TypeScript 타입을 만든다. 키를 정렬하고 들여쓰기·끝 줄바꿈을 고정해, 같은 앱이면
몇 번을 내보내도 바이트가 같다. lifespan(앱 잠금·자동 시드)은 실행하지 않는다.

`app.main`은 import할 때 모듈 수준 앱을 만들어 설정을 읽는다. 그래서 import를 `export_openapi`
안으로 미루고, 설정 오류(`ConfigError`)는 `main()`이 한국어 안내와 종료 코드 1로 바꾼다.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.config import REPO_ROOT, ConfigError

DEFAULT_OUT_PATH = REPO_ROOT / "frontend" / "src" / "api" / "generated" / "openapi.json"


def export_openapi(out_path: Path) -> Path:
    """앱의 OpenAPI 스키마를 `out_path`에 결정적인 JSON으로 쓰고 그 경로를 돌려준다."""
    from app.main import create_app  # import 시 설정을 읽으므로 호출 시점까지 미룬다

    spec = create_app().openapi()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(spec, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    out_path.write_text(text, encoding="utf-8")
    return out_path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.export_openapi",
        description="서버를 띄우지 않고 OpenAPI 스키마를 JSON 파일로 내보낸다.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT_PATH,
        help=(
            f"출력 경로 (기본: {DEFAULT_OUT_PATH.relative_to(REPO_ROOT)}). "
            "상대 경로는 현재 디렉토리 기준이다"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """인자를 파싱해 스키마를 내보내고 쓴 경로를 출력한다. 설정 오류면 종료 코드 1을 돌려준다."""
    args = _build_parser().parse_args(argv)
    try:
        written = export_openapi(args.out)
    except ConfigError as err:
        print(f"OpenAPI 스키마를 내보내지 못했다: 설정 오류 ({err})", file=sys.stderr)
        return 1
    print(f"OpenAPI 스키마를 썼다: {written}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
