"""추천 카드 서비스 테스트가 함께 쓰는 상수·도우미 (`card_db` fixture는 `conftest.py`).

`card_db`는 환자 NS07, 대화 하나, 항목 2개(`rx1` 에이전트, `rx2` 의사)인 `active` 카드 R0001을
가진 빈 스키마 DB다.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import pytest

from app.services.clock import format_app_timestamp
from app.services.ports import RecommendationCard, RecommendationItem
from app.storage.db import connect
from app.storage.recommendations import insert_prescription, select_card
from tests.storage.items import DOCTOR_ITEM
from tests.storage.rows import PATIENT_ID

CARD_ID = "R0001"
THREAD_ID = "T0001"
STORED_AT = "2026-11-23T12:00:00.000000"  # insert_recommendation 기본 시각
NOW = datetime(2026, 12, 5, 9, 0, 0, 123456)  # 서비스에 넘기는 시계 값
NOW_TEXT = format_app_timestamp(NOW)


def read_card(db: Path, recommendation_id: str = CARD_ID) -> RecommendationCard:
    """카드를 새 연결로 읽는다. 없으면 실패한다."""
    with connect(db) as conn:
        card = select_card(conn, recommendation_id)
    assert card is not None
    return card


@contextmanager
def assert_card_unchanged(db: Path, exc_type: type[BaseException]) -> Iterator[None]:
    """블록이 `exc_type`을 던지고, 그 뒤에도 카드가 블록 전과 같은지 확인한다."""
    before = read_card(db)
    with pytest.raises(exc_type):
        yield
    assert read_card(db) == before


def set_status(db: Path, status: str, recommendation_id: str = CARD_ID) -> None:
    """카드 상태를 직접 바꾼다."""
    with connect(db) as conn:
        conn.execute(
            "UPDATE recommendations SET status = ? WHERE recommendation_id = ?",
            (status, recommendation_id),
        )


def insert_rx(
    db: Path,
    prescription_id: str,
    confirmed_at: str,
    *,
    patient_id: str = PATIENT_ID,
    recommendation_id: str | None = None,
    items: tuple[RecommendationItem, ...] = (DOCTOR_ITEM,),
) -> None:
    """처방 행을 직접 넣는다(서비스를 거치지 않는 준비용)."""
    with connect(db) as conn:
        insert_prescription(
            conn,
            prescription_id=prescription_id,
            patient_id=patient_id,
            recommendation_id=recommendation_id,
            items=items,
            confirmed_at=confirmed_at,
        )
