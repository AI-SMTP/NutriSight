"""JSON·기간 열 인코딩과 디코딩 테스트."""

from __future__ import annotations

import json
from datetime import date

import pytest

from app.intake.types import QualityIssue
from app.nutrition.types import Nutrient, NutrientEvidence
from app.services.item_rules import validate_items
from app.services.ports import AddedBy, EvidenceRef, PrescriptionType
from app.storage.codec import (
    evidence_from_json,
    evidence_to_json,
    format_basis_period,
    items_from_json,
    items_to_json,
    nutrients_from_json,
    nutrients_to_json,
    quality_issues_from_json,
    quality_issues_to_json,
    strings_from_json,
    strings_to_json,
)
from tests.storage.items import AGENT_ITEM, DOCTOR_ITEM

EVIDENCE = (
    NutrientEvidence(nutrient=Nutrient.ENERGY, avg_pct=70.5, low_days_streak=0),
    NutrientEvidence(nutrient=Nutrient.PROTEIN, avg_pct=None, low_days_streak=3),
)


def test_evidence_round_trip() -> None:
    assert evidence_from_json(evidence_to_json(EVIDENCE)) == EVIDENCE


def test_evidence_to_json_uses_field_names() -> None:
    assert json.loads(evidence_to_json(EVIDENCE)) == [
        {"nutrient": "energy", "avg_pct": 70.5, "low_days_streak": 0},
        {"nutrient": "protein", "avg_pct": None, "low_days_streak": 3},
    ]


def test_evidence_empty_round_trip() -> None:
    assert evidence_to_json(()) == "[]"
    assert evidence_from_json("[]") == ()


def test_evidence_from_json_null_is_empty() -> None:
    assert evidence_from_json(None) == ()


def test_evidence_from_json_returns_enum_instances() -> None:
    parsed = evidence_from_json(evidence_to_json(EVIDENCE))
    assert all(isinstance(e.nutrient, Nutrient) for e in parsed)


def test_evidence_from_json_rejects_unknown_nutrient() -> None:
    raw = json.dumps([{"nutrient": "fat", "avg_pct": 1.0, "low_days_streak": 0}])
    with pytest.raises(ValueError):
        evidence_from_json(raw)


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        (date(2026, 11, 22), date(2026, 11, 28), "2026-11-22~2026-11-28"),
        (None, date(2026, 11, 28), None),
        (date(2026, 11, 22), None, None),
        (None, None, None),
    ],
)
def test_format_basis_period(start: date | None, end: date | None, expected: str | None) -> None:
    assert format_basis_period(start, end) == expected


def test_strings_round_trip_keeps_korean() -> None:
    encoded = strings_to_json(("당뇨", "고혈압"))
    assert encoded == '["당뇨", "고혈압"]'
    assert strings_from_json(encoded) == ("당뇨", "고혈압")
    assert strings_from_json("[]") == ()


def test_quality_issues_round_trip() -> None:
    issues = (QualityIssue.BLUR, QualityIssue.TRAY_MISMATCH)
    encoded = quality_issues_to_json(issues)
    assert json.loads(encoded) == ["blur", "tray_mismatch"]
    decoded = quality_issues_from_json(encoded)
    assert decoded == issues
    assert all(isinstance(q, QualityIssue) for q in decoded)


def test_nutrients_round_trip() -> None:
    nutrients = (Nutrient.ENERGY, Nutrient.PROTEIN)
    encoded = nutrients_to_json(nutrients)
    assert json.loads(encoded) == ["energy", "protein"]
    decoded = nutrients_from_json(encoded)
    assert decoded == nutrients
    assert all(isinstance(n, Nutrient) for n in decoded)
    assert nutrients_from_json("[]") == ()


def test_enum_list_decoders_reject_unknown_values() -> None:
    with pytest.raises(ValueError):
        quality_issues_from_json('["noise"]')
    with pytest.raises(ValueError):
        nutrients_from_json('["fat"]')


# 추천 항목 JSON -------------------------------------------------------------------


def test_items_to_json_uses_data_model_keys_and_keeps_korean():
    raw = items_to_json((AGENT_ITEM, DOCTOR_ITEM))

    assert "식사 강화 7일" in raw  # ensure_ascii=False
    assert json.loads(raw) == [
        {
            "item_id": "rx1",
            "type": "food_fortification",
            "title": "식사 강화 7일",
            "detail": "단백질 반찬 강화로 에너지·단백질 밀도 높이기",
            "duration_days": 7,
            "review_date": None,
            "added_by": "agent",
            "evidence": [
                {"doc_id": "espen_geriatrics", "section": "R20"},
                {"doc_id": "espen_geriatrics", "section": "R23"},
            ],
        },
        {
            "item_id": "rx2",
            "type": "monitoring_review",
            "title": "재평가",
            "detail": "",
            "duration_days": None,
            "review_date": "2026-12-04",
            "added_by": "doctor",
            "evidence": [],
        },
    ]


def test_items_round_trip_restores_typed_values():
    restored = items_from_json(items_to_json((AGENT_ITEM, DOCTOR_ITEM)))

    assert restored == (AGENT_ITEM, DOCTOR_ITEM)
    first, second = restored
    assert type(first.type) is PrescriptionType
    assert type(first.added_by) is AddedBy
    assert isinstance(first.evidence, tuple)
    assert type(first.evidence[0]) is EvidenceRef
    assert type(second.review_date) is date
    validate_items(restored)


def test_items_from_json_empty_array():
    assert items_from_json("[]") == ()
    assert items_to_json(()) == "[]"


def test_items_from_json_missing_key_raises_value_error():
    entry = json.loads(items_to_json((AGENT_ITEM,)))[0]
    del entry["added_by"]
    with pytest.raises(ValueError, match="added_by"):
        items_from_json(json.dumps([entry]))


def test_items_from_json_rejects_unknown_type():
    raw = items_to_json((AGENT_ITEM,)).replace("food_fortification", "tube_feeding")
    with pytest.raises(ValueError):
        items_from_json(raw)
