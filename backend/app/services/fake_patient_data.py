"""고정 데이터를 메모리에 두는 `FakePatientData`.

실행 중 더미 구현이자 계약 테스트 대상이다. 스펙 §3.4 "환자 데이터 포트 픽스처 배치"
(환자 4명, 카드 7장)를 그대로 갖는다. 공개 상수는 계약 테스트의 `PortFixture` 입력에 쓴다.

`NS01`의 섭취 기록(목표 1,500 kcal·55 g, 3끼 환산 %):

| 날짜 | 상태 |
| --- | --- |
| 11-19 | 3끼 기록 (기본 기간 밖) |
| 11-20 | 3끼 기록 |
| 11-21 | 전부 미기록 |
| 11-22 | 발주 없음 (요약에서 빠짐) |
| 11-23 | 전부 금식 |
| 11-24 | 2끼 기록 + 금식 1끼 |
| 11-25 | 3끼 기록 |
| 11-26 | 1끼 기록 + 미기록 2끼 (기준일) |
| 11-27 | 3끼 기록 (기준일 다음 날) |

판정은 11-24 `none`, 11-26 `caution`, 11-27 `warning`이다.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

from app.nutrition.types import (
    AlertLevel,
    AlertResult,
    DailyIntake,
    DailyTarget,
    Nutrient,
    NutrientEvidence,
    TargetSource,
)
from app.services.ports import (
    AddedBy,
    EvidenceRef,
    IntakeSummary,
    LeftMenu,
    ModifiedBy,
    PatientNotFoundError,
    PrescriptionType,
    RecommendationCard,
    RecommendationItem,
    RecommendationNotEditableError,
    RecommendationNotFoundError,
    RecommendationStatus,
)

# ---- 공개 ID·날짜 상수 ----

PATIENT_WITH_ACTIVE = "NS01"
PATIENT_WITH_FAILED_ONLY = "NS02"
PATIENT_WITH_TIE = "NS03"
PATIENT_WITHOUT_CARD = "NS04"
PATIENT_IDS: tuple[str, ...] = (
    PATIENT_WITH_ACTIVE,
    PATIENT_WITH_FAILED_ONLY,
    PATIENT_WITH_TIE,
    PATIENT_WITHOUT_CARD,
)

# active ID가 failed ID보다 사전순으로 작다 (ID 정렬만 쓰는 구현을 계약 테스트가 잡는다).
SUPERSEDED_ID = "rec-ns01-superseded"
FAILED_ID = "rec-ns01-failed"
ACTIVE_ID = "rec-ns01-active"
CONFIRMED_ID = "rec-ns01-confirmed"
FAILED_ONLY_ID = "rec-ns02-failed"
TIE_ACTIVE_ID = "rec-ns03-active"
TIE_FAILED_ID = "rec-ns03-failed"  # 같은 시각의 두 카드 중 사전순으로 큰 ID

SUMMARY_ON = date(2026, 11, 26)
SUMMARY_DAYS = 7
ALT_SUMMARY_DAYS = 3
ALT_SUMMARY_ON = date(2026, 11, 27)

# ---- 섭취 기록과 판정 ----

_TARGET = DailyTarget(energy_kcal=1500.0, protein_g=55.0, source=TargetSource.KDRI)


def _day(
    on: date,
    amounts: tuple[float, float, float, float] | None,
    counts: tuple[int, int, int],
) -> DailyIntake:
    """`amounts`는 (kcal, g, 에너지 %, 단백질 %), `counts`는 (기록, 미기록, 금식) 끼니 수."""
    energy_kcal, protein_g, energy_pct, protein_pct = amounts or (None, None, None, None)
    recorded, unrecorded, npo = counts
    return DailyIntake(
        on=on,
        energy_kcal=energy_kcal,
        protein_g=protein_g,
        energy_pct=energy_pct,
        protein_pct=protein_pct,
        recorded_meals=recorded,
        unrecorded_meals=unrecorded,
        npo_meals=npo,
        target=_TARGET,
    )


_THREE_MEALS = (900.0, 33.0, 60.0, 60.0)  # 900 ÷ 1,500 × 100, 33 ÷ 55 × 100
_TWO_MEALS = (600.0, 22.0, 60.0, 60.0)  # 600 × 3 ÷ 2 ÷ 1,500 × 100
_ONE_MEAL = (250.0, 5.5, 50.0, 30.0)  # 250 × 3 ÷ 1,500 × 100, 5.5 × 3 ÷ 55 × 100

_DAILY: dict[str, tuple[DailyIntake, ...]] = {
    PATIENT_WITH_ACTIVE: (
        _day(date(2026, 11, 19), _THREE_MEALS, (3, 0, 0)),
        _day(date(2026, 11, 20), _THREE_MEALS, (3, 0, 0)),
        _day(date(2026, 11, 21), None, (0, 3, 0)),
        _day(date(2026, 11, 23), None, (0, 0, 3)),
        _day(date(2026, 11, 24), _TWO_MEALS, (2, 0, 1)),
        _day(date(2026, 11, 25), _THREE_MEALS, (3, 0, 0)),
        _day(date(2026, 11, 26), _ONE_MEAL, (1, 2, 0)),
        _day(date(2026, 11, 27), _THREE_MEALS, (3, 0, 0)),
    ),
}


_ALERT_WINDOW_DAYS = 7  # 판정 기간: 판정일을 포함한 최근 7일


def _none_alert(unrecorded: int) -> AlertResult:
    return AlertResult(
        level=AlertLevel.NONE,
        nutrients=(),
        period_start=None,
        period_end=None,
        evidence=(),
        unrecorded_meals=unrecorded,
    )


def _low_alert(
    level: AlertLevel,
    on: date,
    energy: tuple[float, int],
    protein: tuple[float, int],
    unrecorded: int,
) -> AlertResult:
    """`energy`·`protein`은 (기간 평균 %, 50% 미만 연속 일수)다."""
    return AlertResult(
        level=level,
        nutrients=(Nutrient.ENERGY, Nutrient.PROTEIN),
        period_start=on - timedelta(days=_ALERT_WINDOW_DAYS - 1),
        period_end=on,
        evidence=(
            NutrientEvidence(
                nutrient=Nutrient.ENERGY, avg_pct=energy[0], low_days_streak=energy[1]
            ),
            NutrientEvidence(
                nutrient=Nutrient.PROTEIN, avg_pct=protein[0], low_days_streak=protein[1]
            ),
        ),
        unrecorded_meals=unrecorded,
    )


# (판정일, 판정) 쌍. AlertResult에 판정일 필드가 없어 포트 내부 상태로 둔다.
# level은 계약 테스트용 고정 배치 값이다. AlertRules로 계산한 값이 아니다.
# 근거 수치는 위 `_DAILY`의 판정 기간 행과 맞춘다 (평균은 기록된 날의 %만, 미기록 끼니 합계).
_ALERTS: dict[str, tuple[tuple[date, AlertResult], ...]] = {
    PATIENT_WITH_ACTIVE: (
        # 11-18 ~ 11-24: 미기록 11-21(3끼)
        (date(2026, 11, 24), _none_alert(3)),
        # 11-20 ~ 11-26: 에너지 (60+60+60+50)/4, 단백질 (60+60+60+30)/4,
        # 11-26 단백질 30%로 50% 미만 1일 연속. 미기록 11-21(3끼) + 11-26(2끼)
        (
            date(2026, 11, 26),
            _low_alert(AlertLevel.CAUTION, date(2026, 11, 26), (57.5, 0), (52.5, 1), 5),
        ),
        # 11-21 ~ 11-27: 기록된 날 11-24·25·26·27, 11-27은 60%라 연속 0일
        (
            date(2026, 11, 27),
            _low_alert(AlertLevel.WARNING, date(2026, 11, 27), (57.5, 0), (52.5, 0), 5),
        ),
    ),
}

_LEFT_MENUS: tuple[LeftMenu, ...] = (
    LeftMenu(menu_name="시금치나물", dish_type="side", avg_intake_fraction=0.2, meal_count=4),
    LeftMenu(menu_name="생선구이", dish_type="main", avg_intake_fraction=0.45, meal_count=3),
)

# ---- 추천 카드 ----

_AGENT_ITEMS: tuple[RecommendationItem, ...] = (
    RecommendationItem(
        item_id="rx1",
        type=PrescriptionType.FOOD_FORTIFICATION,
        title="식사 강화 7일",
        detail="단백질 반찬 강화로 에너지·단백질 밀도 높이기",
        duration_days=7,
        review_date=None,
        added_by=AddedBy.AGENT,
        evidence=(
            EvidenceRef(doc_id="espen_geriatrics", section="R20"),
            EvidenceRef(doc_id="espen_geriatrics", section="R23"),
        ),
    ),
    RecommendationItem(
        item_id="rx2",
        type=PrescriptionType.MONITORING_REVIEW,
        title="재평가",
        detail="12/3 재평가, 주 1회 체중 측정",
        duration_days=None,
        review_date=date(2026, 12, 3),
        added_by=AddedBy.AGENT,
        evidence=(EvidenceRef(doc_id="espen_geriatrics", section="R20"),),
    ),
)
_CAUTIONS = ("체중 기록이 없어 필요량을 성별·연령 기준으로 계산했습니다.",)


def _card(
    recommendation_id: str,
    patient_id: str,
    status: RecommendationStatus,
    created_at: datetime,
) -> RecommendationCard:
    has_items = status != RecommendationStatus.FAILED
    return RecommendationCard(
        recommendation_id=recommendation_id,
        patient_id=patient_id,
        alert_id=f"alert-{recommendation_id}",
        items=_AGENT_ITEMS if has_items else (),
        cautions=_CAUTIONS if has_items else (),
        last_modified_by=ModifiedBy.AGENT,
        thread_id=None,
        created_at=created_at,
        updated_at=created_at,
        status=status,
    )


def _at(day: int, hour: int) -> datetime:
    return datetime(2026, 11, day, hour, 0, tzinfo=UTC)


def default_cards() -> tuple[RecommendationCard, ...]:
    """스펙 §3.4 고정 카드 7장."""
    return (
        _card(SUPERSEDED_ID, PATIENT_WITH_ACTIVE, RecommendationStatus.SUPERSEDED, _at(24, 9)),
        _card(FAILED_ID, PATIENT_WITH_ACTIVE, RecommendationStatus.FAILED, _at(25, 9)),
        _card(ACTIVE_ID, PATIENT_WITH_ACTIVE, RecommendationStatus.ACTIVE, _at(26, 9)),
        _card(CONFIRMED_ID, PATIENT_WITH_ACTIVE, RecommendationStatus.CONFIRMED, _at(26, 15)),
        _card(FAILED_ONLY_ID, PATIENT_WITH_FAILED_ONLY, RecommendationStatus.FAILED, _at(25, 12)),
        _card(TIE_ACTIVE_ID, PATIENT_WITH_TIE, RecommendationStatus.ACTIVE, _at(26, 10)),
        _card(TIE_FAILED_ID, PATIENT_WITH_TIE, RecommendationStatus.FAILED, _at(26, 10)),
    )


def late_failed_cards() -> tuple[RecommendationCard, ...]:
    """기본 7장에서 `NS01`의 `failed` 카드 `created_at`만 `active`보다 늦게 바꾼 카드.

    `updated_at`이 `created_at`보다 이르지 않도록 같은 시각으로 함께 옮긴다.
    """
    late_at = _at(26, 12)
    return tuple(
        replace(card, created_at=late_at, updated_at=late_at)
        if card.recommendation_id == FAILED_ID
        else card
        for card in default_cards()
    )


def _utc_now() -> datetime:
    return datetime.now(UTC)


_SELECTABLE = (RecommendationStatus.ACTIVE, RecommendationStatus.FAILED)


class FakePatientData:
    """고정 환자 4명·카드 7장을 메모리에 두는 환자 데이터 포트 더미."""

    def __init__(
        self,
        clock: Callable[[], datetime] | None = None,
        cards: Iterable[RecommendationCard] | None = None,
    ) -> None:
        """`clock`은 수정 시각(`updated_at`) 함수, 기본은 현재 UTC 시각이다.

        `cards`를 주면 기본 7장 대신 그 카드로 시작한다. 주입한 카드의 `patient_id`는
        고정 환자 `PATIENT_IDS` 중 하나여야 한다(환자 목록은 카드에서 만들지 않는다).
        """
        self._clock = clock or _utc_now
        source = default_cards() if cards is None else cards
        self._cards: dict[str, RecommendationCard] = {
            card.recommendation_id: card for card in source
        }

    def _require_patient(self, patient_id: str) -> None:
        if patient_id not in PATIENT_IDS:
            raise PatientNotFoundError(f"환자가 없다: {patient_id}")

    async def get_intake_summary(self, patient_id: str, days: int, on: date) -> IntakeSummary:
        self._require_patient(patient_id)
        if days < 1:
            raise ValueError("days는 1 이상이어야 한다")
        period_start = on - timedelta(days=days - 1)
        daily = tuple(row for row in _DAILY.get(patient_id, ()) if period_start <= row.on <= on)
        latest = max(
            (pair for pair in _ALERTS.get(patient_id, ()) if pair[0] <= on),
            key=lambda pair: pair[0],
            default=None,
        )
        return IntakeSummary(
            patient_id=patient_id,
            period_start=period_start,
            period_end=on,
            daily=daily,
            alert=latest[1] if latest else None,
            frequently_left_menus=_LEFT_MENUS,
        )

    async def get_recommendation(self, patient_id: str) -> RecommendationCard | None:
        self._require_patient(patient_id)
        candidates = [
            card
            for card in self._cards.values()
            if card.patient_id == patient_id and card.status in _SELECTABLE
        ]
        return max(
            candidates,
            key=lambda card: (card.created_at, card.recommendation_id),
            default=None,
        )

    async def update_recommendation(
        self,
        recommendation_id: str,
        items: tuple[RecommendationItem, ...],
        modified_by: ModifiedBy,
        thread_id: str | None,
    ) -> RecommendationCard:
        card = self._cards.get(recommendation_id)
        if card is None:
            raise RecommendationNotFoundError(f"추천 카드가 없다: {recommendation_id}")
        if card.status != RecommendationStatus.ACTIVE:
            raise RecommendationNotEditableError(
                f"{card.status.value} 카드는 고칠 수 없다: {recommendation_id}"
            )
        _check_thread_id(modified_by, thread_id)
        item_ids = [item.item_id for item in items]
        if len(set(item_ids)) != len(item_ids):
            raise ValueError("카드 안의 item_id는 유일해야 한다")
        updated = replace(
            card,
            items=tuple(items),
            last_modified_by=modified_by,
            thread_id=thread_id,
            updated_at=self._clock(),
        )
        self._cards[recommendation_id] = updated
        return updated


def _check_thread_id(modified_by: ModifiedBy, thread_id: str | None) -> None:
    """`chat` 수정은 대화 ID가 있어야 하고, `agent`·`doctor` 수정은 `None`이어야 한다."""
    if modified_by == ModifiedBy.CHAT:
        if not thread_id:
            raise ValueError("chat 수정에는 thread_id가 있어야 한다")
    elif thread_id is not None:
        raise ValueError(f"{modified_by.value} 수정의 thread_id는 None이어야 한다")
