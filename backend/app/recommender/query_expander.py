"""한·영 혼합 가이드라인 검색을 위한 임상 용어 쿼리 확장 유틸리티.

공식 RAG 원문 4종(영문 ESPEN·GLIM + 국문 KJG·대한간호협회) 환경에서
한국어·영문 교차언어 검색 편향을 완화하되, 중복 힌트 토큰으로 BM25 점수가
왜곡되지 않도록 힌트 토큰을 정규화·중복 제거한다.
"""

from __future__ import annotations

import unicodedata

# (한국어 원형 또는 복합명사, 영문 핵심 용어)
_KO_TO_EN_GLOSSARY: tuple[tuple[str, str], ...] = (
    ("경구영양보충", "oral nutritional supplements ONS"),
    ("강화식", "food fortification fortified diet"),
    ("식사강화", "food fortification energy protein density"),
    ("에너지필요량", "energy requirements kcal/kg body weight"),
    ("체중기준", "body weight kg per day"),
    ("단백질", "protein g/kg"),
    ("영양불량", "malnutrition undernutrition older adults"),
    ("연하곤란", "dysphagia swallowing texture modified diet"),
    ("사레", "dysphagia choking aspiration swallowing"),
    ("씹기", "chewing mastication denture oral health"),
    ("틀니", "denture chewing difficulty"),
    ("식사보조", "mealtime assistance feeding support"),
    ("치료식", "restrictive diet therapeutic diet"),
    ("욕창", "pressure injury pressure ulcer"),
    ("섭취감소", "reduced food intake energy requirements GLIM"),
    ("섭취부족", "reduced intake inadequate energy protein"),
    ("체중감소", "unintended weight loss"),
    ("영양관리팀", "multidisciplinary nutrition support team"),
    ("치매", "dementia cognitive impairment"),
    ("인지저하", "cognitive impairment dementia"),
    ("식욕저하", "loss of appetite anorexia reduced intake"),
    ("탈수", "dehydration low-intake fluid hydration"),
    ("저수분", "low-intake dehydration fluid intake hydration"),
    ("수분섭취량", "fluid intake hydration drinks"),
)

# (영문 임상 키워드, 한국어 핵심 용어) — 영문 질의 → 국문 가이드라인(KJG, 욕창) 검색 지원
_EN_TO_KO_GLOSSARY: tuple[tuple[str, str], ...] = (
    ("pressure injury", "욕창 영양관리팀 고단백"),
    ("pressure ulcer", "욕창 영양관리팀 고단백"),
    ("restrictive diet", "치료식 제한식 고령자 영양"),
    ("oral nutritional supplements", "경구영양보충 고령자"),
    ("food fortification", "식사 강화 강화식"),
    ("dysphagia", "연하곤란 사레 삼킴"),
    ("malnutrition", "영양불량 고령자 영양"),
    ("dementia", "치매 인지저하 식욕저하 고령자"),
    ("dehydration", "탈수 저수분 수분 섭취 고령자"),
    ("hydration", "수분 섭취 탈수 예방 고령자"),
)


def expand_bilingual_query(query: str) -> str:
    """한·영 임상 키워드를 상호 병기한다. 범위 외 질의는 원문을 그대로 유지한다."""
    normalized = unicodedata.normalize("NFKC", query).strip()
    if not normalized:
        return ""

    compact_ko = normalized.replace(" ", "")
    lowered = normalized.lower()
    seen_words: set[str] = set(lowered.split())
    added_terms: list[str] = []

    for ko_term, en_hint in _KO_TO_EN_GLOSSARY:
        if ko_term in compact_ko:
            for word in en_hint.split():
                w_low = word.lower()
                if w_low not in seen_words:
                    seen_words.add(w_low)
                    added_terms.append(word)

    for en_term, ko_hint in _EN_TO_KO_GLOSSARY:
        if en_term in lowered:
            for word in ko_hint.split():
                w_low = word.lower()
                if w_low not in seen_words:
                    seen_words.add(w_low)
                    added_terms.append(word)

    if not added_terms:
        return normalized
    return f"{normalized} ({' '.join(added_terms)})"
