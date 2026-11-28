"""DB 리셋 CLI (스펙 3.8): `uv run python -m scripts.seed [--demo-date YYYY-MM-DD]`.

앱을 끈 상태에서 실행한다. 인자 파싱과 결과 출력만 맡고, 리셋은 `app.storage.seed`의
`reset_storage`가 한다. 저장소 오류는 종료 코드 1과 한국어 안내(표준 오류)로 바꾼다.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from datetime import date

from app.config import ConfigError, Settings, resolve_demo_date
from app.storage.errors import (
    AppLockedError,
    DemoDateRangeError,
    ResetBusyError,
    ResetCleanupError,
    SeedError,
    StoragePrepareError,
    StorageReplaceError,
)
from app.storage.seed import ResetResult, reset_storage

EXIT_OK = 0
EXIT_ERROR = 1

DESCRIPTION = (
    "시연 DB를 시드로 다시 만들고 대화 DB와 사진을 지운다. 앱을 끈 상태에서 실행한다. "
    "시연일은 --demo-date → 설정 DEMO_DATE → 오늘 순서로 정한다."
)


def _cleanup_message(err: Exception) -> str:
    failures = err.failures if isinstance(err, ResetCleanupError) else ()
    return (
        f"DB는 새 시드 상태다. 실패 항목: {', '.join(failures)}. "
        "원인을 고친 뒤 리셋을 다시 하거나 앱을 시작하면 정리를 이어 간다"
    )


# 오류 → 안내 문구. 위에서부터 처음 맞는 클래스를 쓰므로 하위 클래스를 상위 클래스보다 먼저 둔다
# (`DemoDateRangeError`는 `ConfigError`의 하위 클래스다).
ERROR_MESSAGES: dict[type[Exception], Callable[[Exception], str]] = {
    AppLockedError: lambda _err: "앱이 실행 중이다. 앱을 끈 뒤 다시 실행하라",
    DemoDateRangeError: lambda err: f"시연일이 시드 날짜 범위에 맞지 않는다: {err}",
    ConfigError: lambda err: str(err),
    SeedError: lambda err: f"시드 내용이 잘못됐다: {err}",
    StoragePrepareError: lambda err: f"리셋을 준비하지 못했다. 기존 데이터는 그대로다: {err}",
    StorageReplaceError: lambda err: f"새 DB로 바꾸지 못했다. 기존 데이터는 그대로다: {err}",
    ResetBusyError: lambda err: (
        f"DB를 연 다른 프로그램(sqlite3 셸, DB 브라우저 등)이 있어 리셋하지 못했다. "
        f"기존 데이터는 그대로다. 그 프로그램을 닫은 뒤 다시 실행하라: {err}"
    ),
    ResetCleanupError: _cleanup_message,
}


def _today() -> date:
    """시연일 기본값으로 쓰는 로컬 날짜. 테스트가 덮어쓴다."""
    return date.today()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m scripts.seed", description=DESCRIPTION)
    parser.add_argument(
        "--demo-date",
        metavar="YYYY-MM-DD",
        default=None,
        help="시연일(D0). 주지 않으면 설정 DEMO_DATE, 그것도 없으면 오늘",
    )
    return parser


def _error_message(err: Exception) -> str:
    """`ERROR_MESSAGES`에서 처음 맞는 클래스의 안내 문구를 만든다."""
    for cls, render in ERROR_MESSAGES.items():
        if isinstance(err, cls):
            return render(err)
    return str(err)


def _print_result(result: ResetResult) -> None:
    print(f"리셋을 마쳤다. 시연일: {result.demo_date.isoformat()}")
    print(f"patients: {result.patients}")
    print(f"meal_orders: {result.meal_orders}")
    print(f"daily_intakes: {result.daily_intakes}")
    print(f"alerts: {result.alerts}")


def main(argv: list[str] | None = None) -> int:
    """리셋을 실행하고 종료 코드를 돌려준다. 알려진 오류는 1과 한국어 안내로 바꾼다."""
    args = _build_parser().parse_args(argv)
    try:
        settings = Settings()
        demo_date = resolve_demo_date(args.demo_date, settings, _today())
        result = reset_storage(settings, demo_date=demo_date)
    except tuple(ERROR_MESSAGES) as err:
        print(_error_message(err), file=sys.stderr)
        return EXIT_ERROR
    _print_result(result)
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
