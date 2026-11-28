"""`FakeRecommendationGenerator`의 계약 테스트와 Fake 전용 규칙 테스트."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.nutrition.types import AlertLevel, AlertResult, DailyIntake, Nutrient
from app.recommender.fake_generator import FakeRecommendationGenerator
from app.recommender.generator_types import GenerationError
from app.services.ports import EvidenceRef, IntakeSummary, PrescriptionType
from tests.contracts.nutrition import build_daily_intake
from tests.contracts.recommendation_generator import RecommendationGeneratorContract

PATIENT_ID = "NS01"
PERIOD_END = date(2026, 12, 5)
# 구현 상수를 가져오지 않고 기대값을 따로 고정한다.
EXPECTED_EVIDENCE = (EvidenceRef("espen_geriatrics", "R20"),)
BASE_TYPES = [PrescriptionType.FOOD_FORTIFICATION, PrescriptionType.MONITORING_REVIEW]


def _alert(level: AlertLevel, unrecorded_meals: int) -> AlertResult:
    nutrients = () if level is AlertLevel.NONE else (Nutrient.ENERGY,)
    return AlertResult(
        level=level,
        nutrients=nutrients,
        period_start=PERIOD_END - timedelta(days=6),
        period_end=PERIOD_END,
        evidence=(),
        unrecorded_meals=unrecorded_meals,
    )


def _summary(
    alert: AlertResult | None,
    period_end: date = PERIOD_END,
    daily: tuple[DailyIntake, ...] = (),
) -> IntakeSummary:
    return IntakeSummary(
        patient_id=PATIENT_ID,
        period_start=period_end - timedelta(days=13),
        period_end=period_end,
        daily=daily,
        alert=alert,
        frequently_left_menus=(),
    )


def _caution(n: int) -> str:
    return f"미기록 끼니 {n}개가 있어 섭취 추이가 실제와 다를 수 있습니다."


# 미기록 합이 3인 daily. 판정의 미기록 수와 다르게 두어 문구의 n 출처를 가린다.
DAILY_WITH_UNRECORDED: tuple[DailyIntake, ...] = tuple(
    build_daily_intake(
        on,
        energy_kcal=None,
        protein_g=None,
        energy_pct=None,
        protein_pct=None,
        recorded_meals=0,
        unrecorded_meals=unrecorded,
    )
    for on, unrecorded in ((PERIOD_END - timedelta(days=1), 2), (PERIOD_END, 1))
)


class _FakeGeneratorContract(RecommendationGeneratorContract):
    """두 계약 하위 클래스가 공유하는 `generator` 픽스처.

    이름이 `Test`로 시작하지 않아 수집되지 않는다.
    """

    @pytest.fixture
    def generator(self) -> FakeRecommendationGenerator:
        return FakeRecommendationGenerator()


class TestFakeGeneratorContractWarning(_FakeGeneratorContract):
    @pytest.fixture
    def summary(self) -> IntakeSummary:
        return _summary(_alert(AlertLevel.WARNING, 2))


class TestFakeGeneratorContractNoAlert(_FakeGeneratorContract):
    @pytest.fixture
    def summary(self) -> IntakeSummary:
        return _summary(None)


@pytest.mark.parametrize(
    ("level", "unrecorded", "expected_types", "expected_cautions"),
    [
        (AlertLevel.NONE, 0, BASE_TYPES, ()),
        (AlertLevel.NONE, 3, BASE_TYPES, (_caution(3),)),
        (AlertLevel.CAUTION, 0, BASE_TYPES, ()),
        (AlertLevel.CAUTION, 1, BASE_TYPES, (_caution(1),)),
        (AlertLevel.WARNING, 0, [*BASE_TYPES, PrescriptionType.ONS], ()),
        (AlertLevel.WARNING, 5, [*BASE_TYPES, PrescriptionType.ONS], (_caution(5),)),
    ],
)
async def test_card_follows_level_and_unrecorded_rules(
    level: AlertLevel,
    unrecorded: int,
    expected_types: list[PrescriptionType],
    expected_cautions: tuple[str, ...],
) -> None:
    card = await FakeRecommendationGenerator().generate(
        PATIENT_ID, _summary(_alert(level, unrecorded))
    )

    assert [item.type for item in card.items] == expected_types
    assert card.cautions == expected_cautions


async def test_no_alert_gives_base_items_without_cautions() -> None:
    card = await FakeRecommendationGenerator().generate(PATIENT_ID, _summary(None))

    assert [item.type for item in card.items] == BASE_TYPES
    assert card.cautions == ()


async def test_no_alert_ignores_unrecorded_meals_in_daily() -> None:
    summary = _summary(None, daily=DAILY_WITH_UNRECORDED)

    card = await FakeRecommendationGenerator().generate(PATIENT_ID, summary)

    assert card.cautions == ()


async def test_caution_count_comes_from_alert_not_daily_sum() -> None:
    summary = _summary(_alert(AlertLevel.CAUTION, 2), daily=DAILY_WITH_UNRECORDED)

    card = await FakeRecommendationGenerator().generate(PATIENT_ID, summary)

    assert card.cautions == (_caution(2),)


@pytest.mark.parametrize("period_end", [date(2026, 12, 5), date(2026, 12, 28)])
@pytest.mark.parametrize("level", [None, AlertLevel.NONE, AlertLevel.CAUTION, AlertLevel.WARNING])
@pytest.mark.parametrize("unrecorded", [0, 2])
async def test_review_date_is_period_end_plus_seven_days(
    period_end: date, level: AlertLevel | None, unrecorded: int
) -> None:
    alert = None if level is None else _alert(level, unrecorded)
    summary = _summary(alert, period_end=period_end)

    card = await FakeRecommendationGenerator().generate(PATIENT_ID, summary)

    review = next(i for i in card.items if i.type is PrescriptionType.MONITORING_REVIEW)
    assert review.review_date == period_end + timedelta(days=7)
    assert review.duration_days is None


async def test_fixed_item_fields() -> None:
    card = await FakeRecommendationGenerator().generate(
        PATIENT_ID, _summary(_alert(AlertLevel.WARNING, 0))
    )

    by_type = {item.type: item for item in card.items}
    assert [item.item_id for item in card.items] == ["fortify", "review", "ons"]
    fortify = by_type[PrescriptionType.FOOD_FORTIFICATION]
    assert fortify.title == "식사 강화 7일"
    assert fortify.duration_days == 7
    assert fortify.review_date is None
    assert by_type[PrescriptionType.MONITORING_REVIEW].title == "재평가"
    assert by_type[PrescriptionType.ONS].title == "경구영양보충 하루 400 kcal"
    for item in card.items:
        assert item.evidence == EXPECTED_EVIDENCE


async def test_fail_true_raises_generation_error() -> None:
    with pytest.raises(GenerationError):
        await FakeRecommendationGenerator(fail=True).generate(PATIENT_ID, _summary(None))
