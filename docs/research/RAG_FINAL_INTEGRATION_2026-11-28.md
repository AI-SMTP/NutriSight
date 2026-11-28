# NutriSight — RAG Final Integration A 통합 검증 보고서

> **목적:** `feature/rag-v0-4-agent-preview-20261128` 브랜치를 기준으로 RAG 전체 회귀·안전성 검증, 20문항/38문항 평가 데이터셋 재현 범위 확인, SMTP 최신 `develop` 호환성 점검, T5 Agent 연결 계약 고정 및 유료 OpenAI `text-embedding-3-large` v2.2 재색인·평가 승인 게이트를 단일 통합 보고서로 정리한다.  
> **현재 유료 단계 상태:** **`PENDING APPROVAL`** (형주 별도 승인 전까지 OpenAI API 호출 **0건** 유지)

---

## 1. 실행 환경 · 브랜치 · 기준 SHA

| 항목 | 내용 |
| --- | --- |
| **작업 저장소 / 브랜치** | `HJ-GJ/NutriSight` · `feature/rag-v0-4-agent-preview-20261128` |
| **검증 시작 HEAD** | `ecc509ae` (`ecc509a`) |
| **팀 원본 (읽기 전용 확인)** | `AI-SMTP/NutriSight` · `develop@9d56fbc` (PR #17 프론트 골격, PR #19 저울 평가 제외 반영) |
| **보존 기준선 (무수정)** | `integration/rag-t2-20261128` (`75f122c`, Draft PR #18) · `feature/rag-v0-3-hardening-20261128` (`5e8d7cf`) |
| **실행 일시** | 2026-11-28 05:02–05:07 UTC (2026-11-28 14:02–14:07 KST) |
| **OS / Python** | `Linux devbox 6.18.57 x86_64 GNU/Linux` · `CPython 3.12.16` |
| **패키지 동기화** | `uv sync --locked` (113개 패키지 일치) |
| **금회 OpenAI API 호출** | **0건** (`USD 0.00`) |

---

## 2. 수정 파일 및 수정 이유

| 파일 | 변경 내용 | 수정 이유 |
| --- | --- | --- |
| `backend/tests/test_rag_scope_smoke_18.py` | `ruff check --fix`로 import 블록 정렬(`I001`) 정리 | `ecc509a`에서 `uv run ruff check` 시 `I001` 오류 1건 발생 → 수정 후 `ruff check`·`ruff format --check` 통과 |
| `docs/research/RAG_FINAL_INTEGRATION_2026-11-28.md` | 신규 통합 보고서 작성 | 기존 보고서(`RAG_V0_3_*`, `RAG_V0_4_*`, `RAG_LARGE_API_SMOKE_TEST_*`)는 무수정 보존 |

*(팀 공용 계약 `guideline_types.py`, `ports.py`, `config.py`, `conftest.py`, `tests/contracts/*` 및 T2·T5 영역은 무수정)*

---

## 3. 실제 실행한 무료 검증 및 결과 (`PASS` / `FAIL` / `SKIP` / `NOT RUN`)

| 단계 | 실행 명령어 | 판정 | 세부 결과 (Pass / Fail / Skip) |
| --- | --- | :---: | --- |
| 의존성 | `cd backend && uv sync --locked` | **PASS** | 113 packages synced |
| 린트 (최초) | `uv run ruff check` (`ecc509a`) | **FAIL** | `tests/test_rag_scope_smoke_18.py` `I001` 1건 |
| 린트 (수정 후) | `uv run ruff check` | **PASS** | `All checks passed!` |
| 포맷 검사 | `uv run ruff format --check` | **PASS** | `80 files already formatted` |
| RAG·Agent 핵심 테스트 | `uv run pytest tests/test_rag_scope_smoke_18.py tests/test_rag_v03_hardening.py tests/test_agent_preview.py -q` | **PASS** | **32 passed**, 0 failed, 0 skipped (`63.14s`) |
| 전체 회귀 테스트 | `uv run pytest -q` | **PASS** | **655 passed**, 0 failed, 0 skipped (`106.87s`, 네트워크 0건) |
| 원문 4종 감사 | `uv run python scripts/index_guidelines.py --audit-only` | **PASS** | 4/4종 SHA-256 `approved_ready`, 누락 0건 |
| 저장소 공식 20문항 BM25 | `uv run python scripts/eval_rag.py --bm25-only` | **PASS** | Calibration Hit@3 `100.0%` / Holdout Hit@3 `100.0%`, 오류 0 |
| Work 38문항 BM25 (v2.2) | `evaluate-questions.py` (로컬 재현 패키지) | **PASS** | 1,159/1,159 전체 역추적 `100%`, 4개 분할 실측 완료 (5절) |
| Agent Preview CLI | `scripts/agent_preview_smoke.py` (`NS01`, `NS01` CKD, `NS02`) | **PASS** | 환자 조회, RAG 호출, CKD 보류(`unsupported_scope`), `Fake` 인용 차단(`citations_verified=false`), 환자 분리, SSE 규격, 카드 미변경 전부 확인 |
| Large v2.2 유료 재색인·평가 | OpenAI `text-embedding-3-large` 1,159청크 재색인 + 38문항 평가 | **PENDING APPROVAL (`NOT RUN`)** | 7절 승인 게이트 대기 (API 호출 0건) |
| Windows 기본 Python | Windows 네이티브 실행 (`app_lock.py` `fcntl`) | **NOT RUN** | Linux VM 환경 |
| 실제 T5 LLM Agent E2E | `create_agent` + 환자 API + 의사 승인 UI | **NOT RUN** | T5 팀 구현 대기 |

---

## 4. 검증된 문헌 · 청크 · 색인 버전

| `doc_id` | 파일 | SHA-256 (앞 12자리) | v2.1 청크 | v2.2 청크 | 상태 |
| --- | --- | --- | ---: | ---: | --- |
| `espen_geriatrics` | `espen-practical-guideline-geriatrics.pdf` | `b5456f29359f...` | 319 | 319 | `approved_ready` |
| `kjg_elderly_nutrition_2019` | `kjg-2019-73-4-196-elderly-nutrition.pdf` | `5b3c2a0d43d4...` | 22 | 22 | `approved_ready` |
| `glim_2025` | `glim-5-year-update-2025-jpen.xml` | `d80cc184b117...` | 63 | **80** (`63` 섹션 보존 + `17` 표) | `approved_ready` |
| `khna_pressure_injury` | `khna-pressure-injury-guideline.pdf` | `ad6a5b511a92...` | 738 | 738 | `approved_ready` |
| **합계** | **공식 4/4종** (`clnu.pdf`는 `pending` 유지) | — | **1,142** | **1,159** | **기존 `xml:s*#c*` 63개 ID 100% 보존** |

* **현재 로컬 활성 Chroma 색인:** `v20261127T182442Z_f2e0ab8e` (`extractor_version="v2.1"`, `text-embedding-3-large`, `3072`차원, `1,142`청크).
* **호환성 확인:** `v2.2` 코드가 기존 `v2.1` Chroma 색인의 기존 `EvidenceRef`를 문제없이 역추적하며(`5/5`), 신규 표 ID(`xml:tbl:jpen2756-tbl-0005#c1`)는 `v2.2` BM25(`1,159/1,159`)에서 역추적 가능하고 Chroma에는 유료 재색인 후 반영됨.

---

## 5. 20문항 · 38문항 재현 가능 범위 및 무료 BM25 성능 비교

### 5-1. 데이터셋 재현 가능성 조사 결과
* **저장소 공식 데이터셋 (`backend/scripts/eval_datasets.json`):** Calibration 10 + 기존 Holdout 10 = **20문항** (GitHub 내 완전 재현 가능).
* **Work 38문항 재현 패키지 (`NutriSight-실험재현.zip` → `evaluation-questions.json`):** 로컬 워크스페이스에 **확보 완료** (Calibration 10 + 기존 Holdout 10 + Independent 12 + Patient 6 = **38문항 전체 재현 가능**).
  * *독립성 구분:* Calibration·기존 Holdout(20문항)은 과거 쿼리 확장 개선에 참고된 분할이며, **Independent 12문항**이 별도 블라인드 검증셋임. 신규 18문항 안전성 회귀(`test_rag_scope_smoke_18.py`)는 규칙 회귀용이며 38문항 검색 평가와 별도로 구분함.

### 5-2. 무료 BM25 실측 결과 (v2.2 · 1,159청크, 문서 적중 vs 필수 근거 구절 충족률 분리)

| 분할 | 문항(양성/OOS) | 문서 Hit@1 | 문서 Hit@3 | 문서 Recall@3 | 문서 MRR | 필수 근거 구절 완전 충족 | OOS 거절률 (BM25 단독) |
| --- | :---: | ---: | ---: | ---: | ---: | :---: | ---: |
| `calibration` | 10 (7/3) | 71.4% | 100.0% | 100.0% | 0.833 | **3/7** (42.9%) | 0.0% |
| `holdout` | 10 (7/3) | 85.7% | 100.0% | 92.9% | 0.929 | **2/7** (28.6%) | 0.0% |
| `independent` | 12 (8/4) | 75.0% | 75.0% | 75.0% | 0.750 | **6/8** (75.0%) | 0.0% |
| `patient` | 6 (5/1) | 60.0% | 100.0% | 70.0% | 0.733 | **2/5** (40.0%) | 0.0% |

* **실패 사례 및 특이사항:**
  * BM25 단독은 `min_score=0.0` 기본값에서 OOS 거절률이 `0.0%`이며, `safe_search_guidelines()` 경유 시 CKD 위험 질의(`NS09-B`, `IND-NEG-01` 등) 및 약물 용량 질의(`IND-NEG-02`/`03`)는 `UNSUPPORTED_SCOPE`로 차단됨.
  * `CAL-07`(GLIM `≤50%` 1주 초과) Top 3에 신규 추출된 `('glim_2025', 'xml:tbl:jpen2756-tbl-0005#c1')`이 실제 진입함. 단, 기존 Work 평가 JSON의 예상 표 라벨 문자열이 `table:jpen2756-tbl-0005`로 적혀 있어 자동 채점기에서는 `xml:tbl:jpen2756-tbl-0005#c1`과의 표기 매핑 1줄 보정이 필요함.

---

## 6. SMTP 최신 `develop` (`9d56fbc`) 호환성 검증 (읽기 전용)

* `67a1a35..9d56fbc` 사이 추가된 팀 변경은 **PR #17(`frontend-shell-upload`: `config.py`, `main.py`, `conftest.py`, `export_openapi.py`, `test_frontend_static.py`)**과 **PR #19(저울 실측 평가 문서 정리)**임.
* **공통 계약·의존성 대조:**
  * `GuidelineSearch` (`backend/app/recommender/guideline_types.py`): **변경 0줄 (완전 호환)**
  * `PatientDataPort`, `EvidenceRef`, `RecommendationCard` (`backend/app/services/ports.py`): **변경 0줄 (완전 호환)**
  * `backend/app/wiring.py`, `backend/pyproject.toml`, `backend/uv.lock`: 팀 `develop` 측 변경 0줄 (우리 RAG 추가분과 충돌 없음)
  * `git merge-tree --write-tree HEAD upstream/develop` 읽기 전용 모의 병합 결과: **충돌 0건 (`PASS`)**
* **미실행 (`NOT RUN`):** 실제 `upstream/develop` 병합 후 통합 `pytest`는 지시서 보존 규칙상 팀/현재 브랜치에 임의 병합하지 않았으므로 `NOT RUN`.

---

## 7. 유료 API 실행 승인 게이트 (`PENDING APPROVAL`)

실제 OpenAI API 호출은 아직 **0건**이며, 아래 산출 근거를 바탕으로 형주의 별도 승인을 대기 중입니다.

| 항목 | 20문항 (저장소 공식) | 38문항 (Work 전체 재현 — 권장) |
| --- | --- | --- |
| **사용 모델** | `text-embedding-3-large` | `text-embedding-3-large` |
| **실행 시점 공식 요금 (2026-11 확인)** | USD 0.13 / 1M input tokens | USD 0.13 / 1M input tokens |
| **신규 1,159청크 재색인 예상 토큰 / 호출** | 약 `488,936` tokens / `19`회 (`batch=64`) | 약 `488,936` tokens / `19`회 (`batch=64`) |
| **평가 질문 예상 토큰 / 호출** | 약 `1,041` tokens / `20`회 | 약 `1,972` tokens / `38`회 |
| **추가 검색·계약 확인 예상 토큰 / 호출** | 약 `475` tokens / `5`회 | 약 `475` tokens / `5`회 |
| **예상 총 API 요청 횟수** | **44회** | **62회** |
| **예상 총 토큰 / 비용 (USD)** | 약 `490,452` tokens / **약 \$0.0638** | 약 `491,383` tokens / **약 \$0.0639** |
| **제안 총 비용 상한 / 초과 정책** | **\$0.15** (초과 예상 시 즉시 중단 후 재승인 요청) | **\$0.15** (초과 예상 시 즉시 중단 후 재승인 요청) |
| **중복 재색인 방지** | `index_guidelines.py` 단독 호출 생략, 단일 평가 실행에서 1회 색인 후 재사용 | 동일 (1회 색인 후 38문항 평가 재사용) |
| **실패 시 색인 복구** | `versions/<new_id>/` 분리 구축·검증 후에만 `active_pointer.json` 원자 교체 → 실패 시 기존 `v2.1` 활성 색인(`v20261127T182442Z_f2e0ab8e`) 무손상 유지 | 동일 |

---

## 8. T5 Agent 최종 인계 규격

T5 구현 시 아래 읽기·검증 인터페이스를 RAG 경계로 고정한다:
* `bind_patient_tools(patient_id, patient_data=..., guideline_search=...) -> ScopedPatientTools` (모델이 `patient_id`를 인자로 선택 불가)
* `tools.get_intake_summary(days=7, on=...)`: 바인딩된 환자 요약만 조회
* `tools.search_guidelines(query, limit=3) -> SafeRetrievalResult`:
  * `FOUND`: 검색 성공일 뿐 **임상 적합성·처방 승인 신호가 아님**
  * `NO_EVIDENCE` / `UNSUPPORTED_SCOPE` / `SEARCH_ERROR`: `hits=()`, `requires_clinical_review=True` → **자동 추천 보류 및 의료진 검토 전달**
* `verify_evidence_refs(refs, guideline_search) -> CitationAuditReport`:
  * 활성 색인 역조회 성공 시에만 `VERIFIED_OFFICIAL` (`can_display_as_official=True`)
  * `FakeGuidelineSearch` 또는 미존재 ID(`R20`, `R23`)는 공식 근거 표시 금지
* `tools.draft_prescription_preview(items) -> DraftPreviewResult`:
  * 현재 미리보기 단계는 **읽기 전용(`saved=False`)**이며, 실제 추천 저장·LLM 판단·의사 처방 확정은 T5 및 의료진 UI 후속 과제임.

---

## 9. 잔존 위험 및 후속 과제

1. **유료 v2.2 Large 색인·38문항 평가 (`PENDING APPROVAL`):** 형주 승인 시 즉시 1회 실행 후 본 보고서에 실측 수치 갱신.
2. **규칙 가드의 표현 한계:** `detect_unsupported_scope()`는 보수적 정규식 기반이므로 T5 LLM 에이전트 단의 임상 보류 정책과 이중 방어 필수.
3. **플랫폼 및 E2E 미검증 (`NOT RUN`):** T2 `app_lock.py`의 Windows 기본 Python `fcntl` 제약, 실제 T5 LLM Agent·환자별 E2E·의료진 승인 워크플로·임상 안전성 검증은 후속 과제.
