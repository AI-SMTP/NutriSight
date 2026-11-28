# NutriSight RAG — 빠른 인계 기준선 (2026-11-28)

> **상태:** 최소 인계 준비 / 비임상 / 미병합  
> **작업 브랜치:** `HJ-GJ/NutriSight:feature/rag-v0-4-agent-preview-20261128`  
> **대상:** SMTP T5 담당자 / T2 백엔드 검토자  
> **정식 계약 소유권:** 팀 `AI-SMTP/NutriSight`의 기존 계약을 우선

## 이번 빠른 마무리 범위

1. 기존 v0.4 검증 결과 보존: 안티그래비티 보고서 기준 **637 passed** (2026-11-28), 이번 변경 뒤 전체 재실행 수치로 재사용하지 않음.
2. `backend/tests/test_rag_scope_smoke_18.py`: 위험 처방 요청 **9건** / 일반 정보 질문 **9건**을 자동 회귀 사례로 고정. 기존 수동 9+9 평가와는 별도로 작성된 대표 문구임.
3. T5가 RAG를 붙일 수 있도록 최소 호출 규격을 명시. **유료 임베딩 재색인·38문항 전체 재평가·실제 LLM/SSE 구현은 이번 범위에서 제외**.

## T5 최소 연결 계약 (읽기 전용)

- 환자 ID는 `bind_patient_tools(patient_id, patient_data=..., guideline_search=...)` 시점에 고정한다. Agent 도구에서 임의 환자 ID를 다시 받지 않는다.
- `ScopedPatientTools.get_intake_summary(days, on)`: 섭취·경고 조회.
- `ScopedPatientTools.search_guidelines(query, limit=3)`: `SafeRetrievalResult` 반환.
  - `found` = 검색된 후보가 있다는 뜻일 뿐 **환자 처방 승인 아님**.
  - `no_evidence`, `unsupported_scope`, `search_error` = 근거 인용/자동 초안 생성을 보류하고 의료진 검토로 넘긴다.
- 추천 항목을 공식 근거로 표시하기 전에 `verify_evidence_refs(items.evidence, guideline_search)`로 출처 ID를 역조회한다. `can_display_as_official=False`라면 공식 인용 표기를 금지한다.
- `draft_prescription_preview(items)`는 `saved=False`인 **테스트용 사전검증**이며 DB 저장·실제 처방·의사 승인 동작을 하지 않는다.
- 모의 `FakeGuidelineSearch`의 `R20`/`R23`을 실제 검증된 근거로 표시하지 않는다.

## 최소 검증 명령

```bash
cd backend
uv sync --locked
uv run ruff check
uv run ruff format --check
uv run pytest tests/test_rag_scope_smoke_18.py tests/test_agent_preview.py -q
uv run python scripts/agent_preview_smoke.py --patient NS01
```

**검증 게이트:** 새 테스트 포함 전체 PASS/FAIL/SKIP를 실제 실행 로그로 기록. 원본 문헌·유료 API 없이 실행할 수 있다.

## 아직 완료로 처리하면 안 되는 항목

- **Large Chroma v2.2 색인**: 기존 v2.1의 1,142청크만 검색되며, 신규 GLIM 표 17청크는 BM25 v2.2에만 반영된 상태. 유료 호출 전 형주 승인 필요.
- **최신 팀 `develop` 기반 E2E**: 팀의 실제 T5 Agent·대화/SSE·추천 저장이 아직 구현·검증되지 않았다.
- **의료 안전성**: 18개 예시 회귀는 정규식의 좁은 범위 검사일 뿐 모든 표현·기저질환을 보호하는 임상 판단이 아니다.
- **Windows 네이티브 실행**: `fcntl` 제약은 남아 있다.

## 병합 기준

- 기존 Draft PR #18은 v0.2 그대로 유지. 본 v0.4 보완 사항을 PR #18에 섞지 않는다.
- 팀 `develop`·`main` 자동 병합 및 배포 금지.
- T5 담당자에게 본 문서·기존 `RAG_AGENT_PREVIEW_HANDOFF.md`·검증 보고서를 전달하고, 실제 도구 호출/추천 보류 방식을 합의한 다음 후속 PR을 검토한다.
