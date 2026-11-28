"""추천 항목 공통 검증 규칙 테스트 (스펙 3.5절 항목 규칙 표)."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime

import pytest

from app.services.item_rules import (
    check_detail,
    check_duration_days,
    check_item_id,
    check_review_date,
    check_title,
    validate_cautions,
    validate_generated_items,
    validate_items,
)
from app.services.ports import AddedBy, EvidenceRef, PrescriptionType, RecommendationItem


def _item(**overrides: object) -> RecommendationItem:
    """규칙을 모두 지키는 기본 항목에서 필드만 바꾼 항목."""
    base = RecommendationItem(
        item_id="fortify",
        type=PrescriptionType.FOOD_FORTIFICATION,
        title="식사 강화 7일",
        detail="",
        duration_days=7,
        review_date=None,
        added_by=AddedBy.AGENT,
        evidence=(EvidenceRef("espen_geriatrics", "R20"),),
    )
    return replace(base, **overrides)


# ── 값 단위 검사기: 통과값은 그대로 돌려준다 ──


@pytest.mark.parametrize("value", ["a", "A-z_09", "x" * 32])
def test_check_item_id_returns_valid_value(value):
    assert check_item_id(value) == value


@pytest.mark.parametrize("value", ["", "x" * 33, "has space", "한글", "a.b", "abc\n", None, 1])
def test_check_item_id_rejects_invalid_value(value):
    with pytest.raises(ValueError):
        check_item_id(value)


@pytest.mark.parametrize("value", ["a", "가" * 100])
def test_check_title_returns_valid_value(value):
    assert check_title(value) == value


@pytest.mark.parametrize("value", ["", "가" * 101, None, 1])
def test_check_title_rejects_invalid_value(value):
    with pytest.raises(ValueError):
        check_title(value)


@pytest.mark.parametrize("value", ["", "가" * 1000])
def test_check_detail_returns_valid_value(value):
    assert check_detail(value) == value


@pytest.mark.parametrize("value", ["가" * 1001, None, 1])
def test_check_detail_rejects_invalid_value(value):
    with pytest.raises(ValueError):
        check_detail(value)


@pytest.mark.parametrize("value", [1, 365, None])
def test_check_duration_days_returns_valid_value(value):
    assert check_duration_days(value) == value


@pytest.mark.parametrize("value", [0, 366, -1, True, False, 7.0, "7"])
def test_check_duration_days_rejects_invalid_value(value):
    with pytest.raises(ValueError):
        check_duration_days(value)


@pytest.mark.parametrize("value", [date(2026, 12, 12), None])
def test_check_review_date_returns_valid_value(value):
    assert check_review_date(value) == value


@pytest.mark.parametrize("value", ["2026-12-12", datetime(2026, 12, 12, 9, 0), 20261212])
def test_check_review_date_rejects_invalid_value(value):
    with pytest.raises(ValueError):
        check_review_date(value)


# ── validate_items: 공통 항목 규칙 + 근거 규칙 ──


@pytest.mark.parametrize(
    "overrides",
    [
        {},
        {"item_id": "x" * 32},
        {"title": "가" * 100},
        {"detail": "가" * 1000},
        {"duration_days": 1},
        {"duration_days": 365},
        {"duration_days": None},
        {"review_date": date(2026, 12, 12)},
        {"added_by": AddedBy.DOCTOR, "evidence": ()},
        {"evidence": (EvidenceRef("d" * 100, "s" * 100),)},
        {"type": PrescriptionType.OTHER},
    ],
)
def test_validate_items_accepts_boundary_values(overrides):
    assert validate_items((_item(**overrides),)) is None


def test_validate_items_accepts_empty_tuple():
    assert validate_items(()) is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"item_id": "bad id"},
        {"item_id": "x" * 33},
        {"type": "ons"},
        {"type": "unknown"},
        {"type": None},
        {"title": ""},
        {"title": "가" * 101},
        {"title": None},
        {"detail": "가" * 1001},
        {"detail": None},
        {"duration_days": 0},
        {"duration_days": 366},
        {"duration_days": True},
        {"review_date": "2026-12-12"},
        {"review_date": datetime(2026, 12, 12, 9, 0)},
        {"added_by": "agent"},
        {"evidence": [EvidenceRef("espen_geriatrics", "R20")]},
        {"evidence": (("espen_geriatrics", "R20"),)},
        {"evidence": (EvidenceRef("", "R20"),)},
        {"evidence": (EvidenceRef("d" * 101, "R20"),)},
        {"evidence": (EvidenceRef("espen_geriatrics", ""),)},
        {"evidence": (EvidenceRef("espen_geriatrics", "s" * 101),)},
        {"evidence": (EvidenceRef(None, "R20"),)},
    ],
)
def test_validate_items_rejects_rule_violation(overrides):
    with pytest.raises(ValueError):
        validate_items((_item(**overrides),))


def test_validate_items_rejects_duplicate_item_id():
    items = (_item(item_id="same"), _item(item_id="same", title="다른 제목"))

    with pytest.raises(ValueError):
        validate_items(items)


def test_validate_items_rejects_violation_in_later_item():
    items = (_item(item_id="ok"), _item(item_id="bad", duration_days=0))

    with pytest.raises(ValueError):
        validate_items(items)


@pytest.mark.parametrize("items", [[_item()], (object(),), (None,), None])
def test_validate_items_rejects_non_item_container_or_element(items):
    with pytest.raises(ValueError):
        validate_items(items)


# ── validate_cautions: 공통 카드 규칙 ──


@pytest.mark.parametrize(
    "cautions",
    [(), ("a",), ("가" * 300,), tuple(f"주의 {i}" for i in range(10))],
)
def test_validate_cautions_accepts_boundary_values(cautions):
    assert validate_cautions(cautions) is None


@pytest.mark.parametrize(
    "cautions",
    [
        tuple(f"주의 {i}" for i in range(11)),
        ("",),
        ("가" * 301,),
        (1,),
        (None,),
        ["주의"],
        "주의",
        None,
    ],
)
def test_validate_cautions_rejects_rule_violation(cautions):
    with pytest.raises(ValueError):
        validate_cautions(cautions)


# ── validate_generated_items: 생성기 전용 규칙 + 공통 규칙 ──


def test_validate_generated_items_accepts_agent_items():
    items = (_item(item_id="fortify"), _item(item_id="review", duration_days=None))

    assert validate_generated_items(items, ("주의",)) is None


def test_validate_generated_items_rejects_empty_items():
    with pytest.raises(ValueError):
        validate_generated_items((), ())


def test_validate_generated_items_rejects_doctor_item():
    items = (_item(item_id="fortify"), _item(item_id="extra", added_by=AddedBy.DOCTOR))

    with pytest.raises(ValueError):
        validate_generated_items(items, ())


@pytest.mark.parametrize(
    ("items", "cautions"),
    [
        ((_item(item_id="same"), _item(item_id="same")), ()),
        ((_item(duration_days=True),), ()),
        ((_item(),), (1,)),
        ((_item(),), tuple("주" for _ in range(11))),
    ],
)
def test_validate_generated_items_applies_common_rules(items, cautions):
    with pytest.raises(ValueError):
        validate_generated_items(items, cautions)
