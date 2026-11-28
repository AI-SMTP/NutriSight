"""모듈 범위 API 앱의 DB에 테스트 동안만 행을 넣는 도우미.

API 테스트는 모듈마다 앱 하나를 시작해 같은 DB를 쓴다. 테스트가 넣은 행은 `cleanup`이 넣은
역순으로 지워(외래 키 순서) 다음 테스트가 시드 상태를 본다.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from app.storage.db import connect

Inserter = Callable[..., None]


@dataclass
class ScratchRows:
    """`add`로 넣은 행을 기억했다가 `cleanup`에서 지운다."""

    db_path: Path
    _keys: list[tuple[str, str, object]] = field(default_factory=list)

    def add(self, insert: Inserter, table: str, key_column: str, **row: object) -> None:
        """`insert(conn, **row)`로 한 행을 넣는다. `row`에는 `key_column` 값이 있어야 한다."""
        with connect(self.db_path) as conn:
            insert(conn, **row)
        self._keys.append((table, key_column, row[key_column]))

    def cleanup(self) -> None:
        """넣은 역순으로 지운다."""
        with connect(self.db_path) as conn:
            for table, key_column, key in reversed(self._keys):
                conn.execute(f"DELETE FROM {table} WHERE {key_column} = ?", (key,))
        self._keys.clear()
