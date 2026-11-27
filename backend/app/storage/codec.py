"""DB TEXT 열의 인코딩·디코딩 짝 (스펙 3.4 JSON 필드, 3.7 시드 적재).

시드 적재는 `*_to_json`·`format_basis_period`로 쓰고, 조회 함수는 `*_from_json`으로 읽는다.
한 곳에 짝을 두어 쓰는 형식과 읽는 형식이 어긋나지 않게 한다. JSON은 한글을 그대로 쓴다.
알 수 없는 열거값은 `ValueError`다.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import date

from app.intake.types import QualityIssue
from app.nutrition.types import Nutrient, NutrientEvidence


def _dump(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


def strings_to_json(values: Iterable[str]) -> str:
    """문자열 목록(예: `conditions`)을 JSON 배열로."""
    return _dump([str(v) for v in values])


def strings_from_json(raw: str) -> tuple[str, ...]:
    """JSON 배열을 문자열 tuple로."""
    return tuple(str(v) for v in json.loads(raw))


def quality_issues_to_json(issues: Iterable[QualityIssue]) -> str:
    """`slot_intakes.quality_issues` 인코딩."""
    return strings_to_json(issues)


def quality_issues_from_json(raw: str) -> tuple[QualityIssue, ...]:
    """`slot_intakes.quality_issues` 디코딩."""
    return tuple(QualityIssue(v) for v in json.loads(raw))


def nutrients_to_json(nutrients: Iterable[Nutrient]) -> str:
    """`alerts.nutrients` 인코딩."""
    return strings_to_json(nutrients)


def nutrients_from_json(raw: str) -> tuple[Nutrient, ...]:
    """`alerts.nutrients` 디코딩."""
    return tuple(Nutrient(v) for v in json.loads(raw))


def evidence_to_json(evidence: tuple[NutrientEvidence, ...]) -> str:
    """`alerts.basis_values` 인코딩. 객체 키는 `NutrientEvidence` 필드 이름이다."""
    return _dump(
        [
            {
                "nutrient": str(e.nutrient),
                "avg_pct": e.avg_pct,
                "low_days_streak": e.low_days_streak,
            }
            for e in evidence
        ]
    )


def evidence_from_json(raw: str | None) -> tuple[NutrientEvidence, ...]:
    """`alerts.basis_values` 디코딩. NULL이면 빈 tuple."""
    if raw is None:
        return ()
    return tuple(
        NutrientEvidence(
            nutrient=Nutrient(item["nutrient"]),
            avg_pct=item["avg_pct"],
            low_days_streak=item["low_days_streak"],
        )
        for item in json.loads(raw)
    )


def format_basis_period(start: date | None, end: date | None) -> str | None:
    """`alerts.basis_period` = `<start>~<end>`. 한쪽이라도 없으면 None."""
    if start is None or end is None:
        return None
    return f"{start.isoformat()}~{end.isoformat()}"
