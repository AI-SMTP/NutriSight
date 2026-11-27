"""DB 전체 내용 비교 도우미.

15개 테이블의 모든 행을 PK 순으로 꺼낸다. 적재 시각인 `seed_meta.seeded_at` 행은 결정성
비교에서 뺀다(스펙 3.3).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from app.storage.db import connect

TableDump = dict[str, list[tuple[object, ...]]]


def dump_tables(conn: sqlite3.Connection) -> TableDump:
    """연결이 가리키는 DB의 모든 테이블 행. `conn.row_factory`는 `sqlite3.Row`여야 한다."""
    tables = [
        r["name"]
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")
    ]
    dump: TableDump = {}
    for table in tables:
        info = conn.execute(f"PRAGMA table_info({table})").fetchall()
        pk = [r["name"] for r in sorted(info, key=lambda r: r["pk"]) if r["pk"] > 0]
        rows = conn.execute(f"SELECT * FROM {table} ORDER BY {', '.join(pk)}").fetchall()
        dump[table] = [
            tuple(r) for r in rows if not (table == "seed_meta" and r["key"] == "seeded_at")
        ]
    return dump


def table_dump(path: Path) -> TableDump:
    """`connect`로 열어 덤프한다. WAL 내용을 반영하므로 닫을 때 보조 파일이 정리될 수 있다."""
    with connect(path) as conn:
        return dump_tables(conn)


def main_file_dump(path: Path) -> TableDump:
    """DB 본체 파일만 읽어 덤프한다(`immutable=1`). 보조 파일을 만들거나 읽지 않는다."""
    conn = sqlite3.connect(f"file:{path.resolve()}?mode=ro&immutable=1", uri=True)
    try:
        conn.row_factory = sqlite3.Row
        return dump_tables(conn)
    finally:
        conn.close()
