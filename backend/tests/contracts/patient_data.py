"""`PatientDataPort` 계약 테스트 기반 클래스.

구현별 하위 클래스(`Test*`)는 다음 픽스처 네 개를 정의한다.

- `port`: 스펙 §3.4 "환자 데이터 포트 픽스처 배치"(환자 4명, 카드 7장)를 담은 포트. 함수 범위.
- `port_fixture`: 그 배치의 ID·날짜를 알려 주는 `PortFixture`.
- `late_failed_port`: 위 배치에서 `patient_with_active`의 `failed` 카드 `created_at`만
  `active` 카드보다 늦게 바꾼 별도 포트. 함수 범위.
- `late_failed`: 그 포트의 환자 ID와 기대 카드 ID를 알려 주는 `LateFailedFixture`.

`PortFixture.chat_thread_id`는 채팅 수정 성공 테스트가 넘기는 대화 ID다. T4 하위 클래스는
`recommendations.thread_id`의 외래 키를 만족하도록 테스트 DB에 대화(`chat_threads`) 하나를
미리 넣고 그 ID를 넘긴다. Fake는 대화 테이블이 없으므로 아무 문자열이나 쓴다.

계약은 선택 규칙·기간 계산·결측 규칙·수정 규칙·보존 필드까지만 본다.
`frequently_left_menus`의 집계 규칙은 T4에서 정하므로 모양(값 범위·정렬)만 본다.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, timedelta

import pytest

from app.nutrition.types import AlertLevel, AlertResult, DailyIntake
from app.services.ports import (
    AddedBy,
    EvidenceRef,
    IntakeSummary,
    LeftMenu,
    ModifiedBy,
    PatientDataPort,
    PatientNotFoundError,
    PrescriptionType,
    RecommendationCard,
    RecommendationItem,
    RecommendationNotEditableError,
    RecommendationNotFoundError,
    RecommendationStatus,
)

RULE_VIOLATION_THREAD_ID = "t1"  # 규칙 위반으로 거부되는 입력이라 저장되지 않는다


@dataclass(frozen=True)
class PortFixture:
    """`port`에 넣은 픽스처 배치의 ID·날짜 (스펙 §3.4 표)."""

    patient_with_active: str
    expected_active_id: str
    patient_with_failed_only: str
    expected_failed_id: str
    patient_with_tie: str
    expected_tie_id: str
    patient_without_card: str
    confirmed_id: str
    superseded_id: str
    failed_id: str
    unknown_patient_id: str
    unknown_recommendation_id: str
    summary_on: date
    summary_days: int
    expected_summary_dates: tuple[date, ...]
    alt_summary_days: int  # summary_days보다 작은 유효값
    expected_alt_days_dates: tuple[date, ...]
    alt_summary_on: date  # summary_on 다음 날
    expected_alt_on_dates: tuple[date, ...]
    expected_alt_on_alert_level: AlertLevel
    chat_thread_id: str  # 채팅 수정에 쓸 대화 ID (T4는 미리 넣은 chat_threads 행의 ID)


@dataclass(frozen=True)
class LateFailedFixture:
    """`late_failed_port`에서 더 늦은 `failed` 카드를 가진 환자와 그 카드 ID."""

    patient_id: str
    expected_id: str


def build_items(prefix: str = "rx") -> tuple[RecommendationItem, ...]:
    """`item_id`가 서로 다른 유효한 추천 항목 2개 (수정 입력용)."""
    return (
        RecommendationItem(
            item_id=f"{prefix}1",
            type=PrescriptionType.ONS,
            title="경구영양보충 14일",
            detail="하루 400 kcal · 단백질 30 g 이상, 2~3회",
            duration_days=14,
            review_date=None,
            added_by=AddedBy.DOCTOR,
            evidence=(EvidenceRef(doc_id="espen_geriatrics", section="R23"),),
        ),
        RecommendationItem(
            item_id=f"{prefix}2",
            type=PrescriptionType.MONITORING_REVIEW,
            title="재평가",
            detail="주 1회 체중 측정",
            duration_days=None,
            review_date=date(2026, 12, 4),
            added_by=AddedBy.DOCTOR,
            evidence=(),
        ),
    )


def build_duplicate_items() -> tuple[RecommendationItem, ...]:
    """`item_id`가 겹치는 추천 항목 2개."""
    first, second = build_items("dup")
    return (first, replace(second, item_id=first.item_id))


def _dates(summary: IntakeSummary) -> tuple[date, ...]:
    return tuple(row.on for row in summary.daily)


def _assert_alert_level(summary: IntakeSummary, expected: AlertLevel) -> None:
    assert isinstance(summary.alert, AlertResult)
    assert isinstance(summary.alert.level, AlertLevel)
    assert summary.alert.level == expected


def _assert_editable_fields(
    card: RecommendationCard | None,
    items: tuple[RecommendationItem, ...],
    modified_by: ModifiedBy,
    thread_id: str | None,
) -> None:
    assert isinstance(card, RecommendationCard)
    assert card.items == items
    assert isinstance(card.last_modified_by, ModifiedBy)
    assert card.last_modified_by == modified_by
    assert card.thread_id == thread_id


class PatientDataPortContract:
    """모든 `PatientDataPort` 구현이 지켜야 하는 불변 조건."""

    # ---- 하위 클래스가 정의할 픽스처 ----

    @pytest.fixture
    def port(self) -> PatientDataPort:
        """스펙 §3.4 배치를 담은 포트. 테스트마다 새 상태여야 한다."""
        raise NotImplementedError("하위 클래스가 port 픽스처를 정의해야 한다")

    @pytest.fixture
    def port_fixture(self) -> PortFixture:
        raise NotImplementedError("하위 클래스가 port_fixture 픽스처를 정의해야 한다")

    @pytest.fixture
    def late_failed_port(self) -> PatientDataPort:
        """`failed` 카드가 `active`보다 늦게 만들어진 별도 포트."""
        raise NotImplementedError("하위 클래스가 late_failed_port 픽스처를 정의해야 한다")

    @pytest.fixture
    def late_failed(self) -> LateFailedFixture:
        raise NotImplementedError("하위 클래스가 late_failed 픽스처를 정의해야 한다")

    # ---- 계약이 제공하는 픽스처 ----

    @pytest.fixture
    async def default_summary(
        self, port: PatientDataPort, port_fixture: PortFixture
    ) -> IntakeSummary:
        """`patient_with_active`의 기본 기간(`summary_days`, `summary_on`) 요약."""
        return await port.get_intake_summary(
            port_fixture.patient_with_active, port_fixture.summary_days, port_fixture.summary_on
        )

    # ---- get_recommendation: 선택 규칙 ----

    @pytest.mark.parametrize(
        ("patient_field", "expected_field"),
        [
            ("patient_with_failed_only", "expected_failed_id"),
            ("patient_with_tie", "expected_tie_id"),
        ],
        ids=["failed_only", "tie_larger_id"],
    )
    async def test_get_recommendation_returns_expected_card(
        self,
        port: PatientDataPort,
        port_fixture: PortFixture,
        patient_field: str,
        expected_field: str,
    ) -> None:
        patient_id = getattr(port_fixture, patient_field)

        card = await port.get_recommendation(patient_id)

        assert isinstance(card, RecommendationCard)
        assert card.recommendation_id == getattr(port_fixture, expected_field)
        assert card.patient_id == patient_id

    async def test_get_recommendation_tie_has_no_status_priority(
        self, port: PatientDataPort, port_fixture: PortFixture
    ) -> None:
        """같은 시각이면 `active`가 아니라 사전순으로 큰 ID의 `failed`를 고른다."""
        card = await port.get_recommendation(port_fixture.patient_with_tie)

        assert isinstance(card, RecommendationCard)
        assert isinstance(card.status, RecommendationStatus)
        assert card.status == RecommendationStatus.FAILED

    async def test_get_recommendation_orders_by_created_at_before_id(
        self, port: PatientDataPort, port_fixture: PortFixture
    ) -> None:
        """`created_at`으로 `active` 카드를 고른다.

        가장 늦은 `confirmed` 카드는 고르지 않고, ID만 정렬하는 구현이면 고를
        사전순으로 큰 `failed` 카드도 고르지 않는다.
        """
        # 배치 확인: ID만 정렬하면 failed 카드가 이기도록 ID가 지어져 있어야 한다.
        assert port_fixture.expected_active_id < port_fixture.failed_id

        card = await port.get_recommendation(port_fixture.patient_with_active)

        assert isinstance(card, RecommendationCard)
        assert card.recommendation_id == port_fixture.expected_active_id
        assert card.recommendation_id != port_fixture.confirmed_id
        assert card.patient_id == port_fixture.patient_with_active
        assert isinstance(card.status, RecommendationStatus)
        assert card.status == RecommendationStatus.ACTIVE

    async def test_get_recommendation_picks_later_failed_card(
        self, late_failed_port: PatientDataPort, late_failed: LateFailedFixture
    ) -> None:
        card = await late_failed_port.get_recommendation(late_failed.patient_id)

        assert isinstance(card, RecommendationCard)
        assert card.recommendation_id == late_failed.expected_id
        assert isinstance(card.status, RecommendationStatus)
        assert card.status == RecommendationStatus.FAILED

    async def test_get_recommendation_without_card_returns_none(
        self, port: PatientDataPort, port_fixture: PortFixture
    ) -> None:
        assert await port.get_recommendation(port_fixture.patient_without_card) is None

    async def test_get_recommendation_unknown_patient_raises(
        self, port: PatientDataPort, port_fixture: PortFixture
    ) -> None:
        with pytest.raises(PatientNotFoundError):
            await port.get_recommendation(port_fixture.unknown_patient_id)

    # ---- get_intake_summary: 기간·포함 규칙·판정 ----

    async def test_intake_summary_period_and_dates(
        self, port: PatientDataPort, port_fixture: PortFixture
    ) -> None:
        on = port_fixture.summary_on
        days = port_fixture.summary_days
        # 배치 확인: 기간 안에 발주가 없는 날이 하나 이상 있어 날짜 수가 days보다 적다.
        assert len(port_fixture.expected_summary_dates) < days

        summary = await port.get_intake_summary(port_fixture.patient_with_active, days, on)

        assert isinstance(summary, IntakeSummary)
        assert summary.patient_id == port_fixture.patient_with_active
        assert summary.period_start == on - timedelta(days=days - 1)
        assert summary.period_end == on
        assert all(isinstance(row, DailyIntake) for row in summary.daily)
        assert _dates(summary) == port_fixture.expected_summary_dates

    async def test_intake_summary_days_without_recorded_meal_have_no_amounts(
        self, default_summary: IntakeSummary
    ) -> None:
        summary = default_summary

        empty_days = [row for row in summary.daily if row.recorded_meals == 0]
        for row in empty_days:
            assert row.energy_kcal is None
            assert row.protein_g is None
            assert row.energy_pct is None
            assert row.protein_pct is None
        # 배치 확인: 전부 미기록인 날과 전부 금식인 날이 각각 하나 이상 있다.
        assert any(row.unrecorded_meals > 0 for row in empty_days)
        assert any(row.npo_meals > 0 for row in empty_days)

    async def test_intake_summary_recorded_days_have_non_negative_pct(
        self, default_summary: IntakeSummary
    ) -> None:
        summary = default_summary

        recorded_days = [row for row in summary.daily if row.recorded_meals > 0]
        assert recorded_days  # 배치 확인: 기록된 날이 하나 이상 있다
        for row in recorded_days:
            assert row.energy_pct is not None
            assert row.protein_pct is not None
            assert row.energy_pct >= 0.0  # 상한 없음
            assert row.protein_pct >= 0.0

    async def test_intake_summary_alert_is_judgement_of_summary_on(
        self, default_summary: IntakeSummary
    ) -> None:
        """다음 날 판정(`warning`)이 아니라 기준일 당일 판정(`caution`)을 고른다."""
        summary = default_summary

        _assert_alert_level(summary, AlertLevel.CAUTION)

    async def test_intake_summary_filters_by_days(
        self, port: PatientDataPort, port_fixture: PortFixture
    ) -> None:
        on = port_fixture.summary_on
        days = port_fixture.alt_summary_days
        assert 1 <= days < port_fixture.summary_days  # 배치 확인

        summary = await port.get_intake_summary(port_fixture.patient_with_active, days, on)

        assert summary.period_start == on - timedelta(days=days - 1)
        assert summary.period_end == on
        assert _dates(summary) == port_fixture.expected_alt_days_dates
        # 배치 확인: 기간을 줄이면 빠지는 발주일이 있다.
        assert len(port_fixture.expected_alt_days_dates) < len(port_fixture.expected_summary_dates)
        _assert_alert_level(summary, AlertLevel.CAUTION)

    async def test_intake_summary_filters_by_on(
        self, port: PatientDataPort, port_fixture: PortFixture
    ) -> None:
        on = port_fixture.alt_summary_on
        days = port_fixture.summary_days
        assert on == port_fixture.summary_on + timedelta(days=1)  # 배치 확인

        summary = await port.get_intake_summary(port_fixture.patient_with_active, days, on)

        assert summary.period_start == on - timedelta(days=days - 1)
        assert summary.period_end == on
        assert _dates(summary) == port_fixture.expected_alt_on_dates
        _assert_alert_level(summary, port_fixture.expected_alt_on_alert_level)

    async def test_intake_summary_left_menus_shape(self, default_summary: IntakeSummary) -> None:
        summary = default_summary

        menus = summary.frequently_left_menus
        assert isinstance(menus, tuple)
        for menu in menus:
            assert isinstance(menu, LeftMenu)
            assert 0.0 <= menu.avg_intake_fraction <= 1.0
            assert menu.meal_count >= 1
        fractions = [menu.avg_intake_fraction for menu in menus]
        assert fractions == sorted(fractions)  # 덜 먹은 메뉴부터 (비내림차순)

    async def test_intake_summary_unknown_patient_raises(
        self, port: PatientDataPort, port_fixture: PortFixture
    ) -> None:
        with pytest.raises(PatientNotFoundError):
            await port.get_intake_summary(
                port_fixture.unknown_patient_id, port_fixture.summary_days, port_fixture.summary_on
            )

    @pytest.mark.parametrize("days", [0, -1])
    async def test_intake_summary_days_below_one_raises_value_error(
        self, port: PatientDataPort, port_fixture: PortFixture, days: int
    ) -> None:
        with pytest.raises(ValueError):
            await port.get_intake_summary(
                port_fixture.patient_with_active, days, port_fixture.summary_on
            )

    # ---- update_recommendation: 실패 ----

    async def test_update_unknown_recommendation_raises(
        self, port: PatientDataPort, port_fixture: PortFixture
    ) -> None:
        with pytest.raises(RecommendationNotFoundError):
            await port.update_recommendation(
                port_fixture.unknown_recommendation_id, build_items(), ModifiedBy.DOCTOR, None
            )

    @pytest.mark.parametrize("card_field", ["confirmed_id", "superseded_id", "failed_id"])
    async def test_update_non_active_card_raises_not_editable(
        self, port: PatientDataPort, port_fixture: PortFixture, card_field: str
    ) -> None:
        # 유효한 items·modified_by·thread_id로 불러 선행 검사를 모두 통과시킨다.
        with pytest.raises(RecommendationNotEditableError):
            await port.update_recommendation(
                getattr(port_fixture, card_field), build_items(), ModifiedBy.DOCTOR, None
            )

    @pytest.mark.parametrize(
        ("modified_by", "thread_id"),
        [
            (ModifiedBy.CHAT, None),
            (ModifiedBy.AGENT, RULE_VIOLATION_THREAD_ID),
            (ModifiedBy.DOCTOR, RULE_VIOLATION_THREAD_ID),
        ],
        ids=["chat_without_thread", "agent_with_thread", "doctor_with_thread"],
    )
    async def test_update_thread_id_rule_violation_raises_value_error(
        self,
        port: PatientDataPort,
        port_fixture: PortFixture,
        modified_by: ModifiedBy,
        thread_id: str | None,
    ) -> None:
        with pytest.raises(ValueError):
            await port.update_recommendation(
                port_fixture.expected_active_id, build_items(), modified_by, thread_id
            )

    async def test_update_duplicate_item_id_raises_value_error(
        self, port: PatientDataPort, port_fixture: PortFixture
    ) -> None:
        with pytest.raises(ValueError):
            await port.update_recommendation(
                port_fixture.expected_active_id, build_duplicate_items(), ModifiedBy.DOCTOR, None
            )

    @pytest.mark.parametrize(
        ("items_kind", "modified_by", "thread_id"),
        [
            ("duplicate", ModifiedBy.DOCTOR, None),
            ("valid", ModifiedBy.CHAT, None),
        ],
        ids=["duplicate_item_id", "chat_without_thread"],
    )
    async def test_rejected_update_leaves_card_unchanged(
        self,
        port: PatientDataPort,
        port_fixture: PortFixture,
        items_kind: str,
        modified_by: ModifiedBy,
        thread_id: str | None,
    ) -> None:
        before = await port.get_recommendation(port_fixture.patient_with_active)
        assert isinstance(before, RecommendationCard)
        items = build_duplicate_items() if items_kind == "duplicate" else build_items("bad")
        assert before.items != items  # 배치 확인: 거부된 값이 반영되면 드러난다

        with pytest.raises(ValueError):
            await port.update_recommendation(
                port_fixture.expected_active_id, items, modified_by, thread_id
            )

        reread = await port.get_recommendation(port_fixture.patient_with_active)
        _assert_editable_fields(reread, before.items, before.last_modified_by, before.thread_id)

    # ---- update_recommendation: 성공 ----

    async def test_update_by_doctor_changes_items_and_preserves_fields(
        self, port: PatientDataPort, port_fixture: PortFixture
    ) -> None:
        before = await port.get_recommendation(port_fixture.patient_with_active)
        assert isinstance(before, RecommendationCard)
        new_items = build_items("doc")
        assert before.items != new_items  # 배치 확인: 새 값이 기존 값과 다르다

        result = await port.update_recommendation(
            port_fixture.expected_active_id, new_items, ModifiedBy.DOCTOR, None
        )

        _assert_editable_fields(result, new_items, ModifiedBy.DOCTOR, None)
        preserved = (
            "recommendation_id",
            "patient_id",
            "alert_id",
            "cautions",
            "created_at",
            "status",
        )
        for name in preserved:
            assert getattr(result, name) == getattr(before, name), name

        reread = await port.get_recommendation(port_fixture.patient_with_active)
        assert isinstance(reread, RecommendationCard)
        assert reread.recommendation_id == port_fixture.expected_active_id
        _assert_editable_fields(reread, new_items, ModifiedBy.DOCTOR, None)

    async def test_update_by_chat_sets_thread_id(
        self, port: PatientDataPort, port_fixture: PortFixture
    ) -> None:
        new_items = build_items("chat")
        thread_id = port_fixture.chat_thread_id

        result = await port.update_recommendation(
            port_fixture.expected_active_id, new_items, ModifiedBy.CHAT, thread_id
        )

        _assert_editable_fields(result, new_items, ModifiedBy.CHAT, thread_id)
        reread = await port.get_recommendation(port_fixture.patient_with_active)
        _assert_editable_fields(reread, new_items, ModifiedBy.CHAT, thread_id)

    async def test_update_by_doctor_after_chat_clears_thread_id(
        self, port: PatientDataPort, port_fixture: PortFixture
    ) -> None:
        await port.update_recommendation(
            port_fixture.expected_active_id,
            build_items("chat"),
            ModifiedBy.CHAT,
            port_fixture.chat_thread_id,
        )
        doctor_items = build_items("doc")

        result = await port.update_recommendation(
            port_fixture.expected_active_id, doctor_items, ModifiedBy.DOCTOR, None
        )

        _assert_editable_fields(result, doctor_items, ModifiedBy.DOCTOR, None)
        reread = await port.get_recommendation(port_fixture.patient_with_active)
        _assert_editable_fields(reread, doctor_items, ModifiedBy.DOCTOR, None)
