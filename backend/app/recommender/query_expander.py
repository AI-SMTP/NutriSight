"""한·영 혼합 가이드라인 검색을 위한 임상 용어 쿼리 확장 유틸리티.

공식 RAG 원문 4종(영문 ESPEN·GLIM + 국문 KJG·대한간호협회) 환경에서
한국어 임상 질의가 영문 원문에서 누락되는 교차언어 편향을 완화한다.
"""

from __future__ import annotations

_BILINGUAL_CLINICAL_GLOSSARY: tuple[tuple[str, str], ...] = (
    ("경구영양보충", "oral nutritional supplements ONS"),
    ("경구 영양 보충", "oral nutritional supplements ONS"),
    ("강화식", "food fortification fortified diet"),
    ("식사 강화", "food fortification energy protein density"),
    ("에너지 필요량", "energy requirements kcal/kg body weight"),
    ("체중 기준", "body weight kg per day"),
    ("단백질", "protein g/kg"),
    ("영양불량", "malnutrition undernutrition older adults"),
    ("연하곤란", "dysphagia swallowing texture modified diet"),
    ("사레", "dysphagia choking aspiration swallowing"),
    ("씹기", "chewing mastication denture oral health"),
    ("틀니", "denture chewing difficulty"),
    ("식사 보조", "mealtime assistance feeding support"),
    ("치료식", "restrictive diet therapeutic diet"),
    ("욕창", "pressure injury pressure ulcer"),
    ("섭취 감소", "reduced food intake energy requirements GLIM"),
    ("섭취 부족", "reduced intake inadequate energy protein"),
    ("체중 감소", "unintended weight loss"),
)


def expand_bilingual_query(query: str) -> str:
    """한국어 임상 키워드에 핵심 영문 용어를 병기한다. 영문 질의·범위 외 질의는 원문을 유지한다."""
    stripped = query.strip()
    if not stripped:
        return ""

    lowered = stripped.lower()
    extras: list[str] = []
    for ko_term, en_hint in _BILINGUAL_CLINICAL_GLOSSARY:
        first_token = en_hint.split()[0].lower()
        if ko_term in stripped and first_token not in lowered and en_hint not in extras:
            extras.append(en_hint)

    if not extras:
        return stripped
    return f"{stripped} ({', '.join(extras)})"
