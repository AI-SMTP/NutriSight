"""실제 LangChain/LLM 없이 T5 도구 호출 및 SSE 이벤트 모양을 점검하는 FakeAgent.

HTTP 라우터, 체크포인터, 추천 카드 저장 및 의료 처방 기능은 없다.
팀 T5 구현과 충돌하지 않도록 독립 테스트 모듈로만 제공한다.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import date
from typing import Literal

from app.agent_preview.bridge import ScopedPatientTools
from app.recommender.retrieval_guard import RetrievalStatus
from app.services.ports import PatientNotFoundError

EventName = Literal["token", "tool_start", "tool_end", "card_updated", "done", "error"]


@dataclass(frozen=True)
class PreviewEvent:
    name: EventName
    data: dict[str, object]

    def to_sse(self) -> str:
        """T5 문서의 fetch SSE 방식과 호환되는 이벤트 프레임."""
        return f"event: {self.name}\ndata: {json.dumps(self.data, ensure_ascii=False)}\n\n"


class FakeAgentPreview:
    """환자별 도구 묶음을 1회 주입받는 읽기 전용 데모 오케스트레이터."""

    def __init__(self, tools: ScopedPatientTools) -> None:
        self._tools = tools

    async def stream(
        self, question: str, *, on: date, days: int = 7
    ) -> AsyncIterator[PreviewEvent]:
        """각 호출은 도구 결과만 활용한다. 환자 간 공유 메모리를 만들지 않는다."""
        if days < 1:
            raise ValueError("days는 1 이상이어야 합니다")

        yield PreviewEvent("tool_start", {"tool": "get_intake_summary"})
        try:
            summary = await self._tools.get_intake_summary(days=days, on=on)
        except PatientNotFoundError:
            yield PreviewEvent("error", {"message": "선택한 환자를 찾을 수 없습니다."})
            yield PreviewEvent("done", {"status": "error"})
            return

        if summary.patient_id != self._tools.patient_id:
            yield PreviewEvent("error", {"message": "환자 범위 검증 실패"})
            yield PreviewEvent("done", {"status": "error"})
            return

        alert = summary.alert.level.value if summary.alert is not None else "none"
        yield PreviewEvent(
            "tool_end",
            {
                "tool": "get_intake_summary",
                "patient_id": self._tools.patient_id,
                "recorded_days": len(summary.daily),
                "alert": alert,
            },
        )

        yield PreviewEvent("tool_start", {"tool": "search_guidelines"})
        result = await self._tools.search_guidelines(question)
        yield PreviewEvent(
            "tool_end",
            {
                "tool": "search_guidelines",
                "status": result.status.value,
                "hit_count": len(result.hits),
                "requires_clinical_review": result.requires_clinical_review,
            },
        )
        if result.status is RetrievalStatus.FOUND:
            message = (
                "관련 문헌 후보를 조회했습니다. 인용 원문 검증과 의료진 검토 전에는 "
                "환자별 처방이나 추천을 확정할 수 없습니다."
            )
        else:
            message = (
                "승인 문헌에서 안전한 근거를 확보하지 못했거나 지원 범위를 벗어납니다. "
                "자동 처방을 보류하고 의료진 확인이 필요합니다."
            )

        yield PreviewEvent("token", {"text": message})
        yield PreviewEvent("done", {"status": "read_only_preview"})

    # card_updated 이벤트를 만들지 않는다. 모의 실행에서는 실제 카드 변경이 없어야 한다.
