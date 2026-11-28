# NutriSight RAG v0.4 — 최종 통합 검증 보고서 (Agent Preview & RAG v0.3/v0.4)

> **목적:** T5 실제 LLM 에이전트가 미구현된 상태에서 `feature/rag-v0-4-agent-preview-20261128` 브랜치의 독립 Agent Preview(`app/agent_preview/`, `scripts/agent_preview_smoke.py`)와 RAG v0.3/v0.4 고도화 모듈(안전 검색 계약·GLIM XML 표 추출·인용 무결성)이 충돌 없이 정상 동작하는지 검증하고 결과를 기록한다.  
> **제약 준수:** 기존 v0.2 Draft PR #18(`integration/rag-t2-20261128`), 팀 `AI-SMTP/NutriSight` `develop`/`main`은 수정·병합하지 않았으며, 유료 OpenAI API 호출 및 Chroma 유료 재색인은 수행하지 않았다.

---

## 1. 검증 대상 및 실행 환경

| 항목 | 내용 |
| --- | --- |
| **저장소 / 브랜치** | `HJ-GJ/NutriSight` · `feature/rag-v0-4-agent-preview-20261128` |
| **검증 시작 원격 HEAD** | `9ee1588874d4fbb8dbe424202d8e530f72787342` (`9ee1588`) |
| **수정 반영 커밋** | `11fac93acc214847b9bd9c88cd59c81d10eab03b` (`11fac93`, 포맷 수정 + CKD 범위 보강) |
| **보존 기준선 (무수정)** | `integration/rag-t2-20261128` (`75f122c`) · 팀 `develop` (`67a1a35`) |
| **실행 일시** | 2026-11-28 02:30–02:35 UTC (2026-11-28 11:30–11:35 KST) |
| **OS / Python** | `Linux devbox 6.18.57 x86_64 GNU/Linux` · `CPython 3.12.16` |
| **의존성 동기화** | `uv sync --locked` (113개 패키지, `uv.lock` 일치) |
| **OpenAI API 호출** | **0건** (네트워크 호출 0건) |

---

## 2. 발견된 오류 · 원인 분석 및 수정 내역

| # | 발견 단계 | 오류 내용 및 원인 | 수정 파일 | 재실행 판정 |
| --- | --- | --- | --- | :---: |
| 1 | 1단계 (`ruff format --check`) | `9ee1588` 기준 v0.4 신규 파일 3개가 프로젝트 `ruff format` 규칙(line-length 100)에 맞지 않아 `3 files would be reformatted`로 실패 | `backend/app/agent_preview/fake_agent.py`, `backend/scripts/agent_preview_smoke.py`, `backend/tests/test_agent_preview.py` | **PASS** (`79 files already formatted`) |
| 2 | 3단계 (CKD 위험 변형 점검) | CKD 위험 질의 9개 중 영문(`CKD stage 3b elderly protein target g/kg prescription dose`)과 한국어 수량 질의(`만성콩팥병 환자에게 고단백 ONS 하루 몇 병 처방해도 될까?`) 2건이 기존 정규식에 매칭되지 않아 통과(`PASSED`)함 | `backend/app/recommender/retrieval_guard.py`, `backend/tests/test_agent_preview.py` | **PASS** (CKD 위험 **9/9 차단**, 정상 **0/9 과차단**) |

---

## 3. 실행 명령어 및 테스트 결과 (`PASS` / `FAIL` / `SKIP` / `NOT RUN`)

| 단계 | 실행 명령어 | 판정 | 세부 결과 (Pass / Fail / Skip) |
| --- | --- | :---: | --- |
| 의존성 | `cd backend && uv sync --locked` | **PASS** | 113 packages verified |
| 린트 | `uv run ruff check` | **PASS** | `All checks passed!` |
| 포맷 (최초) | `uv run ruff format --check` (`9ee1588`) | **FAIL** | 3 files unformatted (수정 대상) |
| 포맷 (수정 후) | `uv run ruff format --check` (`11fac93`) | **PASS** | `79 files already formatted` |
| 신규/v0.3 테스트 | `uv run pytest tests/test_rag_v03_hardening.py tests/test_agent_preview.py -q` | **PASS** | **14 passed**, 0 failed, 0 skipped (`41.04s`) |
| 전체 회귀 테스트 | `uv run pytest -q` | **PASS** | **637 passed**, 0 failed, 0 skipped (`81.53s`) |
| Agent 시연 CLI | `uv run python scripts/agent_preview_smoke.py --patient NS01` (+ 위험 질의 · `NS02`) | **PASS** | 7개 검증 항목 전부 통과 (4절 참조) |
| 원문 4종 감사 | `uv run python scripts/index_guidelines.py --audit-only` | **PASS** | 4/4종 SHA-256 `approved_ready`, 누락 0건 |
| GLIM 표·역추적·CKD | 로컬 4종 BM25 & v2.1 Chroma 호환성 스크립트 | **PASS** | 1,159청크, `v2.1` 5/5 · `v2.2` 6/6 역추적, CKD 9/9 차단 |
| 유료 v2.2 재색인 | OpenAI `text-embedding-3-large` 1,159청크 재색인·라이브 평가 | **NOT RUN** | 사전 승인 대기 (예상 비용 약 `USD 0.063`) |
| Windows 기본 Python | Windows 네이티브 Python 실행 (`app_lock.py` `fcntl`) | **NOT RUN** | Linux VM 환경 (플랫폼 제약 유지) |
| 실제 T5 LLM Agent | LangChain `create_agent` + 실제 환자 API/SSE E2E | **NOT RUN** | T5 팀 구현 대기 |

---

## 4. 독립 Agent 시연 (`scripts/agent_preview_smoke.py`) 검증 상세

| 검증 항목 | 실행 시나리오 | 실제 출력 요약 | 판정 |
| --- | --- | --- | :---: |
| 환자 데이터 조회 | `--patient NS01` | `tool_end(get_intake_summary)`: `patient_id="NS01"`, `recorded_days=4`, `daily_rows=6`, `alert="caution"` | **PASS** |
| RAG 검색 도구 호출 | `--patient NS01` (기본 질의) | `tool_start` → `tool_end(search_guidelines)`: `status="found"`, `hit_count=3` | **PASS** |
| Fake 인용 공식 표시 차단 | `--patient NS01` (`FakeGuidelineSearch`) | `citations_verified=false`, 토큰: `"관련 문헌 후보가 있으나 공식 인용이 검증되지 않았습니다. 인용을 공식 근거로 표시하지 말고 의료진 확인을 요청하세요."` | **PASS** |
| 위험 질문 안전 보류 | `--patient NS01 --question "만성콩팥병 G3b 노인 단백질 처방 수치 얼마야?"` | `status="unsupported_scope"`, `hit_count=0`, `citations_verified=false`, `requires_clinical_review=true`, 보류 메시지 출력 | **PASS** |
| 환자 간 데이터 분리 | `--patient NS02` | `patient_id="NS02"`, `recorded_days=0`, `daily_rows=0`, `alert="none"` (`NS01` 데이터 혼입 없음) | **PASS** |
| SSE 이벤트 형태 | 전체 시나리오 | 모든 프레임이 `event: <name>\ndata: <json>\n\n` 규격 준수 (`tool_start`→`tool_end`→`tool_start`→`tool_end`→`token`→`done`) | **PASS** |
| 추천 카드 미변경 | 전체 시나리오 + `test_agent_preview.py` | `card_updated` 이벤트 0건, `done.status="read_only_preview"`, `draft_prescription_preview` 시 `saved=False` 및 원본 카드 불변 | **PASS** |

---

## 5. RAG 4종 원문 · 청크 · `EvidenceRef` · 호환성 검증

1. **공식 문헌 4종 SHA-256 감사 (`approved_ready` 4/4종):**
   * `espen_geriatrics` (PDF): `319`청크 (`b5456f29359f...`)
   * `kjg_elderly_nutrition_2019` (PDF): `22`청크 (`5b3c2a0d43d4...`)
   * `glim_2025` (JPEN XML): `80`청크 = 기존 섹션 `63`청크 (`xml:s*#c*`) 보존 + 신규 표 `17`청크 (`xml:tbl:jpen2756-tbl-0001`–`0005`) (`d80cc184b117...`)
   * `khna_pressure_injury` (PDF): `738`청크 (`ad6a5b511a92...`)
   * **총계:** **1,159청크** (GLIM Clinical Nutrition PDF는 `pending` 유지)
2. **v2.2 코드 ↔ 기존 v2.1 Chroma 색인 호환성 (API 호출 0건):**
   * 기존 활성 색인 `v20261127T182442Z_f2e0ab8e` (`extractor_version="v2.1"`, `1,142`청크, `text-embedding-3-large`, `3072`차원)에서 기존 `EvidenceRef` 5/5 역추적 정상 작동.
   * 신규 GLIM 표 ID(`xml:tbl:jpen2756-tbl-0005#c1`)는 v2.1 Chroma 색인에는 아직 없어 `0/1`(예상 동작), v2.2 BM25에서는 기존 5건 + 표 1건 **6/6** 역추적 성공.
   * `EXTRACTOR_VERSION="v2.2"` 변경으로 향후 유료 재색인 승인 시 `index_guidelines.py`가 버전 분리 안전 재색인을 자동 수행할 수 있음.
3. **CKD 위험 질문 9종 vs 정상 질문 9종 대조:**
   * CKD 위험 질문(한·영 혼합, 병기별 처방 수치, `g/kg/day`, 고단백 ONS 병 수 처방 등): **9/9 차단 (`UNSUPPORTED_SCOPE`)**
   * 정상 임상 질문(`NS09-A` CKD 일반 주의사항, `NS07-A`, `CAL-01`/`02`/`05`/`07`, `HOLD-01`/`02`/`03` 등): **0/9 과차단 (`OK`)**

---

## 6. 남은 위험 및 T5 담당자 협의 사항

### 남은 위험
1. **규칙 기반 범위 가드의 한계:** `detect_unsupported_scope()`는 보수적 정규식 기반이므로 사전에 없는 우회 표현은 검색기를 통과할 수 있음 → 실제 T5 LLM 에이전트 단의 임상 보류 정책과 이중 방어 필수.
2. **Chroma 색인 버전 차이 (`v2.1` vs `v2.2`):** 현재 로컬 Chroma 색인은 `v2.1`(1,142청크)이므로, Chroma 벡터 검색에서 GLIM 표 17청크(`≤50%` 포함)를 활용하려면 형주 승인 후 유료 재색인 1회(약 `USD 0.063`) 필요.
3. **미검증 영역 (`NOT RUN`):** Windows 기본 Python(`app_lock.py` `fcntl` 제약) 및 실제 T5 LLM 에이전트 E2E 흐름.

### T5 담당자 협의 사항
1. `ScopedPatientTools` 패턴(환자 ID를 도구 생성 시 고정 바인딩)과 `safe_search_guidelines()` / `verify_evidence_refs()` 래퍼를 T5 실제 도구 생성기에 채택할지 여부.
2. `citations_verified=false` 또는 `UNSUPPORTED_SCOPE` 반환 시 UI/에이전트 안내 문구 및 카드 상태(`failed` vs 보류 배지) 규약.
3. 시연 전 `FakePatientData`·`FakeGuidelineSearch`의 모의 인용(`R20`, `R23`)을 실제 색인 `EvidenceRef`로 교체하거나 모의 배지로 명시 구분할지 결정.
