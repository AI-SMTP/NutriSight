"""T5 미구현 상태에서 FakeAgent와 RAG 연결 흐름을 확인하는 오프라인 CLI.

실행: cd backend && uv run python scripts/agent_preview_smoke.py
외부 LLM·OpenAI 호출, DB 변경 및 추천 카드 변경이 없다.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.agent_preview.bridge import bind_patient_tools  # noqa: E402
from app.agent_preview.fake_agent import FakeAgentPreview  # noqa: E402
from app.recommender.fake_guideline import FakeGuidelineSearch  # noqa: E402
from app.services.fake_patient_data import SUMMARY_ON, FakePatientData  # noqa: E402


async def run_demo(patient_id: str, question: str) -> None:
    tools = bind_patient_tools(
        patient_id,
        patient_data=FakePatientData(),
        guideline_search=FakeGuidelineSearch(),
    )
    async for event in FakeAgentPreview(tools).stream(question, on=SUMMARY_ON):
        print(event.to_sse(), end="")


def main() -> None:
    parser = argparse.ArgumentParser(description="NutriSight 읽기 전용 FakeAgent/RAG 연동 미리보기")
    parser.add_argument("--patient", default="NS01", help="가상 환자 ID (NS01~NS04)")
    parser.add_argument(
        "--question",
        default="고령자 식사 강화 시 확인해야 할 근거는?",
        help="승인 문헌 검색으로 전달할 질문",
    )
    args = parser.parse_args()
    asyncio.run(run_demo(args.patient, args.question))


if __name__ == "__main__":
    main()
