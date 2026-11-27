"""저장소·시드·리셋 오류 (스펙 3.8).

CLI·lifespan·시드 적재·앱 잠금이 함께 import하므로 한 모듈에 모은다.
"""

from __future__ import annotations

from app.config import ConfigError


class SeedError(Exception):
    """시드 내용 때문에 생긴 실패. 형식 오류, 적재 전 관계 검증 실패, 적재 중 제약 위반."""


class DemoDateRangeError(ConfigError):
    """시연일에 시드 날짜 오프셋을 더하면 날짜 범위(1~9999년)를 벗어난다.

    원인이 시드가 아니라 시연일 입력이므로 형식 오류와 같은 `ConfigError` 계열로 둔다.
    """


class StoragePrepareError(Exception):
    """리셋 준비 중 파일 시스템 오류나 `IntegrityError`가 아닌 `sqlite3.Error`가 났다."""


class StorageReplaceError(Exception):
    """임시 DB로 `app.db`를 교체하지 못했다(`os.replace`의 `OSError`)."""


class ResetBusyError(Exception):
    """기존 `app.db`의 WAL을 본체에 모두 반영하지 못해 교체를 건너뛰었다."""


class ResetCleanupError(Exception):
    """교체 뒤 정리(대화 DB·사진 삭제, 정리 표시 삭제) 중 실패한 항목이 있다."""

    def __init__(self, failures: tuple[str, ...]) -> None:
        self.failures = tuple(failures)
        super().__init__(f"정리에 실패한 항목: {', '.join(self.failures)}")


class AppLockedError(Exception):
    """앱 잠금(`var/app.lock`)을 다른 프로세스가 쥐고 있다."""
