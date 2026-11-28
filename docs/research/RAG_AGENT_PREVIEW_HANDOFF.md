# NutriSight RAG v0.4 — T5 독립 Agent 미리보기 및 인계 규격

> **상태: 작업용 미리보기 구현 (팀 합의 전 / 비임상 / 미병합)**  
> 브랜치: `HJ-GJ/NutriSight:feature/rag-v0-4-agent-preview-20261128`  
> 시작 기준선: RAG v0.3 `5e8d7cf`  
> 팀 원본: `AI-SMTP/NutriSight:develop` — **수정하지 않음**  
> 기존 Draft PR #18: RAG v0.2 (`75f122c`) — **수정하지 않음**

## 1. 목적과 범위

SMTP 팀의 T5 Agent 이슈 #6에 정의된 *환자 범위 고정 도구*, `get_intake_summary`, `search_guidelines`, `draft_prescription` 및 SSE 이벤트를 **T5 파일이 올라오기 전에도** 시험하도록 독립 모듈을 제공한다.

참조 정본:
- `AI-SMTP/NutriSight/docs/system-architecture.md` §7–9 — 에이전트 도구·SSE·대화 엔드포인트 초안
- `docs/specs/backend-contracts.md` — 기존 네 개 포트 계약
- `backend/app/services/ports.py` — `PatientDataPort`, `EvidenceRef`, `RecommendationCard`
- `backend/app/recommender/retrieval_guard.py` — RAG v0.3 안전 검색·인용 확인
- https://github.com/AI-SMTP/NutriSight/issues/6 — T5 책임 범위

**의도적인 비범위:**
- 실제 `create_agent`, Claude/OpenAI LLM, 체크포인터 DB, SSE HTTP 라우트, 대화 이력 DB, 실제 추천 카드 쓰기, 의사 처방 확정
- 실제 환자 데이터, 의료진 대신 하는 영양 처방 및 자동 처방
- SMTP 팀 `develop` 파일 변경

## 2. 추가 소스

| 파일 | 역할 |
| --- | --- |
| `backend/app/agent_preview/bridge.py` | 선택 환자 ID를 고정한 도구, RAG 검색 상태·인용 검사·읽기 전용 초안 사전검증 |
| `backend/app/agent_preview/fake_agent.py` | 비LLM FakeAgent, 도구 호출→토큰→완료의 시험용 이벤트 |
| `backend/scripts/agent_preview_smoke.py` | 네트워크·비용 없이 모의 환자 실행 |
| `backend/tests/test_agent_preview.py` | 환자 격리, CKD 처방 질의 보류, 정상 질의, 인용 차단, SSE 이벤트, 무수정 테스트 |
| `backend/app/recommender/retrieval_guard.py` | CKD 질문 중 '몇 g/kg'·'얼마/적절' 표현의 보수적 차단 범위 확장 |

`agent_preview/`는 T5 소유 경로가 **아니며**, 팀의 Agent 실제 모듈에 미리 코드를 덮어쓰지 않는다.

## 3. 연결 계약

### 3.1 환자 범위 고정

```python
tools = bind_patient_tools(
    "NS01",
    patient_data=FakePatientData(),
    guideline_search=FakeGuidelineSearch(),
)
summary = await tools.get_intake_summary(days=7, on=SUMMARY_ON)
result = await tools.search_guidelines("고령자 영양 평가", limit=3)
```

- 환자 ID는 객체 생성 시 선택한다. 도구 호출 메서드에는 `patient_id` 인자를 주지 않는다.
- 이는 모델의 환자 선택 실수를 줄이는 장치이지 **인증·권한 관리가 아니다**.
- `get_intake_summary`는 시연 날짜 `on`을 명시해 재현성을 확보한다.

### 3.2 RAG 안전 검색

`safe_search_guidelines`의 상태:
- `found`: 검색 결과 후보 있음. 환자별 처방 승인 의미가 아님
- `no_evidence`: 빈 질의 또는 검색 결과 없음
- `unsupported_scope`: 감지된 CKD 처방 수치/약물 프로토콜 미지원 범위
- `search_error`: 검색 실패, 보류

후자의 세 상태는 `hits=()`, `requires_clinical_review=True`로 반환한다.

**주의:** 현재 위험 표현 탐지는 정규식 기반이므로 누락 가능성이 있다. T5는 검색 결과 유무와 상관없이 환자 맥락·미기록 끼니·기저질환·목표 누락을 확인하고 별도로 보류해야 한다. 'found'여도 의학적 적합성은 검증되지 않았다.

### 3.3 읽기 전용 처방 초안 사전검증

`draft_prescription_preview(items)`는 **저장 도구가 아니다.**
- active 카드가 없거나 빈 항목/인용이 있으면 `blocked`
- 모든 인용이 실제 색인에서 역추적되면 `requires_doctor_review`
- 근거 미검증/모의 ID가 있으면 `blocked`
- 어떤 경우에도 `PatientDataPort.update_recommendation`을 호출하지 않으며 `saved=False`

팀 T5가 `draft_prescription`을 만들 때 실제 쓰기 및 이벤트 발행은 **T5가 승인한 규격에서만** 추가한다. 인용 ID 존재는 임상적 정당성과 별개다.

### 3.4 이벤트 미리보기

`FakeAgentPreview.stream(question, on=...)`은 `tool_start`, `tool_end`, `token`, `done`, `error`를 출력하고, `PreviewEvent.to_sse()`는 `event: ...\ndata: ...\n\n` 프레임을 생성한다.

팀 명세의 `card_updated`는 **실제 변경이 없으므로 보내지 않는다.** HTTP 경로 `POST /api/threads/{id}/messages`, 체크포인터, 시스템 이벤트 발행은 구현하지 않았다.

## 4. 오프라인 실행

```bash
cd backend
uv sync --locked
uv run pytest tests/test_agent_preview.py tests/test_rag_v03_hardening.py -q
uv run ruff check app/agent_preview tests/test_agent_preview.py scripts/agent_preview_smoke.py
uv run python scripts/agent_preview_smoke.py --patient NS01
uv run python scripts/agent_preview_smoke.py --patient NS01 --question "CKD G3b 노인 단백질 섭취량 몇 g/kg/day로 하면 돼?"
```

- 실제 승인 PDF/XML 및 OpenAI 키 없이 `FakeGuidelineSearch`로 동작한다.
- 새로운 v0.4 테스트의 통과 여부는 별도 환경에서 실행 확인이 필요하다. **코드 커밋 자체는 테스트 PASS를 의미하지 않는다.**
- 실제 색인 검증은 기존 승인 원문 4종을 별도 준비하고 BM25/Chroma 테스트로 진행한다.

## 5. RAG 완료 전 추가 검증 게이트

- [ ] 신규 CKD 변형 질의 회귀 테스트 통과 및 과도 차단(false positive) 검사
- [ ] v0.3 추출기 v2.2 기반 공식 원문 4종 및 1,159청크 재감사
- [ ] OpenAI API 키/비용 승인 후 **Large Chroma 재색인** (기존 v2.1 색인과 혼용 금지)
- [ ] Large 검색 전체 평가셋(38문항) 재실행 및 NS09-B·CAL-07·HOLD-07 확인
- [ ] 최신 SMTP `develop`을 반영한 전체 회귀 테스트
- [ ] T5 담당자와 안전 보류, 환자 ID 고정, 인용 검증 호출 시점 및 카드 저장 정책 합의
- [ ] 실제 의사 승인 경로는 T5/백엔드에서만 구현

**PR 정책:** v0.2 PR #18 리뷰와 별도 관리. v0.4는 v0.3 검수·팀 연동 합의 후 후속 PR로 제출하며, 현 시점에서는 팀 `develop`에 병합·배포하지 않는다.
