"""`FakePatientData`의 계약 테스트와 Fake 전용 동작 테스트."""

from __future__ import annotations

import copy
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, date, datetime
from enum import StrEnum

import pytest

from app.nutrition.types import AlertLevel
from app.services import fake_patient_data as fake
from app.services.fake_patient_data import FakePatientData, default_cards, late_failed_cards
from app.services.ports import (
    AddedBy,
    LeftMenu,
    ModifiedBy,
    PatientDataError,
    PatientNotFoundError,
    PrescriptionType,
    RecommendationNotEditableError,
    RecommendationNotFoundError,
    RecommendationStatus,
)
from tests.contracts.patient_data import (
    LateFailedFixture,
    PatientDataPortContract,
    PortFixture,
    build_items,
)

# 구현 상수를 가져오지 않고 기대값을 따로 고정한다 (구현을 자기 자신과 비교하지 않기 위해).
# 기간 2026-11-20 ~ 2026-11-26 중 발주가 없는 11-22만 빠진다.
EXPECTED_SUMMARY_DATES = (
    date(2026, 11, 20),
    date(2026, 11, 21),
    date(2026, 11, 23),
    date(2026, 11, 24),
    date(2026, 11, 25),
    date(2026, 11, 26),
)
# 3일(11-24 ~ 11-26)로 줄이면 11-20·11-21·11-23이 빠진다.
EXPECTED_ALT_DAYS_DATES = (date(2026, 11, 24), date(2026, 11, 25), date(2026, 11, 26))
# 기준일 11-27, 7일(11-21 ~ 11-27).
EXPECTED_ALT_ON_DATES = (
    date(2026, 11, 21),
    date(2026, 11, 23),
    date(2026, 11, 24),
    date(2026, 11, 25),
    date(2026, 11, 26),
    date(2026, 11, 27),
)
EXPECTED_PATIENT_IDS = ("NS01", "NS02", "NS03", "NS04")
EXPECTED_CREATED_AT = {
    "rec-ns01-superseded": datetime(2026, 11, 24, 9, 0, tzinfo=UTC),
    "rec-ns01-failed": datetime(2026, 11, 25, 9, 0, tzinfo=UTC),
    "rec-ns01-active": datetime(2026, 11, 26, 9, 0, tzinfo=UTC),
    "rec-ns01-confirmed": datetime(2026, 11, 26, 15, 0, tzinfo=UTC),
    "rec-ns02-failed": datetime(2026, 11, 25, 12, 0, tzinfo=UTC),
    "rec-ns03-active": datetime(2026, 11, 26, 10, 0, tzinfo=UTC),
    "rec-ns03-failed": datetime(2026, 11, 26, 10, 0, tzinfo=UTC),
}
EXPECTED_LATE_FAILED_CREATED_AT = datetime(2026, 11, 26, 12, 0, tzinfo=UTC)
FIXED_NOW = datetime(2026, 11, 27, 8, 30, tzinfo=UTC)


def _fake_port_fixture() -> PortFixture:
    return PortFixture(
        patient_with_active=fake.PATIENT_WITH_ACTIVE,
        expected_active_id=fake.ACTIVE_ID,
        patient_with_failed_only=fake.PATIENT_WITH_FAILED_ONLY,
        expected_failed_id=fake.FAILED_ONLY_ID,
        patient_with_tie=fake.PATIENT_WITH_TIE,
        expected_tie_id=fake.TIE_FAILED_ID,
        patient_without_card=fake.PATIENT_WITHOUT_CARD,
        confirmed_id=fake.CONFIRMED_ID,
        superseded_id=fake.SUPERSEDED_ID,
        failed_id=fake.FAILED_ID,
        unknown_patient_id="NS99",
        unknown_recommendation_id="rec-unknown",
        summary_on=fake.SUMMARY_ON,
        summary_days=fake.SUMMARY_DAYS,
        expected_summary_dates=EXPECTED_SUMMARY_DATES,
        alt_summary_days=fake.ALT_SUMMARY_DAYS,
        expected_alt_days_dates=EXPECTED_ALT_DAYS_DATES,
        alt_summary_on=fake.ALT_SUMMARY_ON,
        expected_alt_on_dates=EXPECTED_ALT_ON_DATES,
        expected_alt_on_alert_level=AlertLevel.WARNING,
        chat_thread_id="t1",
    )


class TestFakePatientPortContract(PatientDataPortContract):
    @pytest.fixture
    def port(self) -> FakePatientData:
        return FakePatientData()

    @pytest.fixture
    def port_fixture(self) -> PortFixture:
        return _fake_port_fixture()

    @pytest.fixture
    def late_failed_port(self) -> FakePatientData:
        return FakePatientData(cards=late_failed_cards())

    @pytest.fixture
    def late_failed(self) -> LateFailedFixture:
        return LateFailedFixture(patient_id=fake.PATIENT_WITH_ACTIVE, expected_id=fake.FAILED_ID)


# ---- 타입 정의 ----


@pytest.mark.parametrize(
    ("enum_type", "expected_values"),
    [
        (
            PrescriptionType,
            (
                "food_fortification",
                "ons",
                "texture_modification",
                "snack_addition",
                "dietitian_referral",
                "monitoring_review",
                "other",
            ),
        ),
        (AddedBy, ("agent", "doctor")),
        (ModifiedBy, ("agent", "chat", "doctor")),
        (RecommendationStatus, ("active", "superseded", "confirmed", "failed")),
    ],
)
def test_enum_values_match_data_model(
    enum_type: type[StrEnum], expected_values: tuple[str, ...]
) -> None:
    assert tuple(member.value for member in enum_type) == expected_values


@pytest.mark.parametrize(
    "error_type",
    [PatientNotFoundError, RecommendationNotFoundError, RecommendationNotEditableError],
)
def test_port_errors_share_base(error_type: type[Exception]) -> None:
    assert issubclass(error_type, PatientDataError)


def test_recommendation_card_is_frozen() -> None:
    card = default_cards()[0]

    with pytest.raises(FrozenInstanceError):
        card.status = RecommendationStatus.CONFIRMED  # type: ignore[misc]


# ---- 고정 데이터 모양 ----


async def test_fake_knows_exactly_the_four_patients() -> None:
    port = FakePatientData()

    for patient_id in EXPECTED_PATIENT_IDS:
        summary = await port.get_intake_summary(patient_id, 7, date(2026, 11, 26))
        assert summary.patient_id == patient_id
    with pytest.raises(PatientNotFoundError):
        await port.get_recommendation("NS05")


def test_default_cards_are_seven_with_fixed_placement() -> None:
    cards = default_cards()

    assert len(cards) == 7
    placement = sorted((card.patient_id, card.status.value) for card in cards)
    assert placement == [
        ("NS01", "active"),
        ("NS01", "confirmed"),
        ("NS01", "failed"),
        ("NS01", "superseded"),
        ("NS02", "failed"),
        ("NS03", "active"),
        ("NS03", "failed"),
    ]


def test_default_cards_have_fixed_created_at() -> None:
    created = {card.recommendation_id: card.created_at for card in default_cards()}

    assert created == EXPECTED_CREATED_AT


def test_late_failed_cards_only_move_failed_card_later() -> None:
    defaults = {card.recommendation_id: card for card in default_cards()}
    late = {card.recommendation_id: card for card in late_failed_cards()}

    assert late.keys() == defaults.keys()
    assert late["rec-ns01-failed"].created_at == EXPECTED_LATE_FAILED_CREATED_AT
    # updated_at도 함께 옮겨 updated_at >= created_at을 지킨다.
    assert late["rec-ns01-failed"] == replace(
        defaults["rec-ns01-failed"],
        created_at=EXPECTED_LATE_FAILED_CREATED_AT,
        updated_at=EXPECTED_LATE_FAILED_CREATED_AT,
    )
    for card_id, card in defaults.items():
        if card_id != "rec-ns01-failed":
            assert late[card_id] == card


async def test_frequently_left_menus_are_two_fixed_items() -> None:
    summary = await FakePatientData().get_intake_summary("NS01", 7, date(2026, 11, 26))

    assert summary.frequently_left_menus == (
        LeftMenu(menu_name="시금치나물", dish_type="side", avg_intake_fraction=0.2, meal_count=4),
        LeftMenu(menu_name="생선구이", dish_type="main", avg_intake_fraction=0.45, meal_count=3),
    )


async def test_summary_daily_rows_follow_three_meal_pct() -> None:
    """1,500 kcal·55 g 목표 기준 3끼 환산 %와 끼니 수가 고정값과 같다."""
    summary = await FakePatientData().get_intake_summary("NS01", 7, date(2026, 11, 26))

    rows = {
        row.on: (
            row.energy_kcal,
            row.protein_g,
            row.energy_pct,
            row.protein_pct,
            row.recorded_meals,
            row.unrecorded_meals,
            row.npo_meals,
        )
        for row in summary.daily
    }
    expected = {
        date(2026, 11, 20): (900.0, 33.0, 60.0, 60.0, 3, 0, 0),
        date(2026, 11, 21): (None, None, None, None, 0, 3, 0),
        date(2026, 11, 23): (None, None, None, None, 0, 0, 3),
        date(2026, 11, 24): (600.0, 22.0, 60.0, 60.0, 2, 0, 1),
        date(2026, 11, 25): (900.0, 33.0, 60.0, 60.0, 3, 0, 0),
        date(2026, 11, 26): (250.0, 5.5, 50.0, 30.0, 1, 2, 0),
    }
    assert list(rows) == list(expected)
    for on, values in expected.items():
        assert rows[on] == pytest.approx(values)


async def test_caution_alert_evidence_matches_daily_rows() -> None:
    """11-20 ~ 11-26 기록된 날의 평균 %와 미기록 끼니 합계."""
    summary = await FakePatientData().get_intake_summary("NS01", 7, date(2026, 11, 26))

    assert summary.alert is not None
    assert summary.alert.period_start == date(2026, 11, 20)
    assert summary.alert.period_end == date(2026, 11, 26)
    assert summary.alert.unrecorded_meals == 5
    avg_pct = {item.nutrient.value: item.avg_pct for item in summary.alert.evidence}
    streaks = {item.nutrient.value: item.low_days_streak for item in summary.alert.evidence}
    assert avg_pct == pytest.approx({"energy": 57.5, "protein": 52.5})
    assert streaks == {"energy": 0, "protein": 1}


async def test_summary_alert_before_any_judgement_is_none() -> None:
    summary = await FakePatientData().get_intake_summary("NS01", 7, date(2026, 11, 19))

    assert summary.alert is None


@pytest.mark.parametrize("patient_id", ["NS02", "NS03", "NS04"])
async def test_summary_of_patient_without_orders_is_empty(patient_id: str) -> None:
    summary = await FakePatientData().get_intake_summary(patient_id, 7, date(2026, 11, 26))

    assert summary.daily == ()
    assert summary.alert is None


# ---- 카드 교체 ----


async def test_update_returns_new_card_object_and_keeps_old_one() -> None:
    port = FakePatientData()
    before = await port.get_recommendation("NS01")
    assert before is not None

    result = await port.update_recommendation(
        "rec-ns01-active", build_items("doc"), ModifiedBy.DOCTOR, None
    )

    assert result is not before
    assert before.items != result.items  # 받아 둔 카드는 수정 전 값을 그대로 가진다
    assert before.last_modified_by == ModifiedBy.AGENT
    assert result.last_modified_by == ModifiedBy.DOCTOR


async def test_update_uses_injected_clock_for_updated_at() -> None:
    port = FakePatientData(clock=lambda: FIXED_NOW)

    result = await port.update_recommendation(
        "rec-ns01-active", build_items("doc"), ModifiedBy.DOCTOR, None
    )

    assert result.updated_at == FIXED_NOW


async def test_instances_do_not_share_card_state() -> None:
    first = FakePatientData()
    second = FakePatientData()

    await first.update_recommendation(
        "rec-ns01-active", build_items("doc"), ModifiedBy.DOCTOR, None
    )

    untouched = await second.get_recommendation("NS01")
    assert untouched is not None
    assert untouched.last_modified_by == ModifiedBy.AGENT
    assert untouched.items != build_items("doc")


async def test_injected_cards_are_copied_not_mutated() -> None:
    injected = list(default_cards())
    snapshot = copy.deepcopy(injected)
    port = FakePatientData(cards=injected)

    await port.update_recommendation("rec-ns01-active", build_items("doc"), ModifiedBy.DOCTOR, None)
    assert injected == snapshot  # 주입한 목록과 카드 객체를 고치지 않는다
    injected.clear()  # 원본 목록을 비워도 포트 상태는 그대로다

    card = await port.get_recommendation("NS01")
    assert card is not None
    assert card.items == build_items("doc")
