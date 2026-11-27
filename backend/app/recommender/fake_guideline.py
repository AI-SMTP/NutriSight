"""외부 호출 없이 고정 구절을 돌려주는 `FakeGuidelineSearch`.

실행 중 더미 구현이자 계약 테스트 대상이다. 질의와 무관하게 같은 순서의 구절을 낸다.
"""

from __future__ import annotations

from app.recommender.guideline_types import GuidelineHit

_ESPEN_GERIATRICS_URL = (
    "https://www.espen.org/files/ESPEN-Guidelines/"
    "ESPEN%5Fpractical%5Fguideline%5FClinical%5Fnutrition%5Fand%5Fhydration%5Fin%5Fgeriatrics.pdf"
)
_KJG_ELDERLY_NUTRITION_URL = "https://doi.org/10.4166/kjg.2019.73.4.196"

# 출처: docs/research/rag-sources/README.md. 본문은 원문을 짧게 풀어 쓴 모의 구절이다.
FIXED_PASSAGES: tuple[GuidelineHit, ...] = (
    GuidelineHit(
        doc_id="espen_geriatrics",
        section="R20",
        text="영양불량이거나 위험이 있는 노인에게는 식사 강화로 "
        "에너지·단백질 섭취를 늘리도록 권한다.",
        source_url=_ESPEN_GERIATRICS_URL,
    ),
    GuidelineHit(
        doc_id="espen_geriatrics",
        section="R23",
        text="식사만으로 섭취가 부족한 노인에게는 경구 영양 보충(ONS)을 제공해 "
        "섭취량과 체중을 개선하도록 권한다.",
        source_url=_ESPEN_GERIATRICS_URL,
    ),
    GuidelineHit(
        doc_id="kjg_elderly_nutrition_2019",
        section="단백질 섭취",
        text="고령자는 근육량 유지를 위해 체중 1 kg당 하루 1.0~1.2 g 이상의 "
        "단백질 섭취가 권장된다.",
        source_url=_KJG_ELDERLY_NUTRITION_URL,
    ),
)


class FakeGuidelineSearch:
    """고정 구절 3개 중 앞에서부터 `limit`개를 돌려주는 가이드라인 검색 더미."""

    async def search(self, query: str, limit: int = 5) -> tuple[GuidelineHit, ...]:
        """질의는 쓰지 않고 고정 구절을 `limit`개까지 돌려준다."""
        if limit < 1:
            raise ValueError("limit은 1 이상이어야 한다")
        return FIXED_PASSAGES[:limit]
