# NutriSight — RAG Final Integration A 통합 검증 보고서

> **목적:** `feature/rag-v0-4-agent-preview-20261128` 브랜치를 기준으로 RAG 전체 회귀·안전성 검증, `text-embedding-3-large` v2.2(1,159청크) 유료 재색인 및 38문항 성능평가, SMTP 최신 `develop` 호환성 점검, T5 Agent 연결 계약 고정을 단일 통합 보고서로 완결한다.  
> **유료 검증 상태:** **형주 승인 후 실행 완료 (`PASS`)** — 실제 호출 `63`회, 총 `487,772` tokens, 추정 비용 **\$0.063410** (제안 상한 \$0.15 이내)

---

## 1. 실행 환경 · 브랜치 · 기준 SHA

| 항목 | 내용 |
| --- | --- |
| **작업 저장소 / 브랜치** | `HJ-GJ/NutriSight` · `feature/rag-v0-4-agent-preview-20261128` |
| **검증 시작 HEAD** | `ecc509ae` (`ecc509a`) → 무료 보고서 `5ea6aeb` → 본 실측 반영 커밋 |
| **팀 원본 (읽기 전용 확인)** | `AI-SMTP/NutriSight` · `develop@9d56fbc` (PR #17 프론트 골격, PR #19 저울 평가 제외 반영) |
| **보존 기준선 (무수정)** | `integration/rag-t2-20261128` (`75f122c`, Draft PR #18) · `feature/rag-v0-3-hardening-20261128` (`5e8d7cf`) |
| **실행 일시** | 무료 검증: 2026-11-28 05:02–05:07 UTC / 유료 검증: 2026-11-28 06:06–06:09 UTC (KST 14:02–15:09) |
| **OS / Python** | `Linux devbox 6.18.57 x86_64 GNU/Linux` · `CPython 3.12.16` |
| **패키지 동기화** | `uv sync --locked` (113개 패키지 일치) |

---

## 2. 수정 파일 및 수정 이유

| 파일 | 변경 내용 | 수정 이유 |
| --- | --- | --- |
| `backend/tests/test_rag_scope_smoke_18.py` | `ruff check --fix`로 import 블록 정렬(`I001`) 정리 | `ecc509a`에서 `uv run ruff check` 시 `I001` 오류 1건 발생 → 수정 후 `ruff check`·`ruff format --check` 통과 |
| `docs/research/RAG_FINAL_INTEGRATION_2026-11-28.md` | 통합 검증 보고서 작성 및 Large v2.2 38문항 실측 반영 | 기존 검증 보고서(`RAG_V0_3_*`, `RAG_V0_4_*`, `RAG_LARGE_API_SMOKE_TEST_*`)는 무수정 보존 |

*(팀 공용 계약 `guideline_types.py`, `ports.py`, `config.py`, `conftest.py`, `tests/contracts/*` 및 T2·T5 영역은 무수정)*

---

## 3. 실제 실행한 테스트 및 검증 결과 (`PASS` / `FAIL` / `SKIP` / `NOT RUN`)

| 단계 | 실행 명령어 | 판정 | 세부 결과 (Pass / Fail / Skip) |
| --- | --- | :---: | --- |
| 의존성 | `cd backend && uv sync --locked` | **PASS** | 113 packages synced |
| 린트 (최초 → 수정 후) | `uv run ruff check` | **PASS** | `I001` 1건 수정 후 `All checks passed!` |
| 포맷 검사 | `uv run ruff format --check` | **PASS** | `80 files already formatted` |
| RAG·Agent 핵심 테스트 | `uv run pytest tests/test_rag_scope_smoke_18.py tests/test_rag_v03_hardening.py tests/test_agent_preview.py -q` | **PASS** | **32 passed**, 0 failed, 0 skipped (`63.14s`) |
| 전체 회귀 테스트 | `uv run pytest -q` | **PASS** | **655 passed**, 0 failed, 0 skipped (`106.87s`, 네트워크 0건) |
| 원문 4종 감사 | `uv run python scripts/index_guidelines.py --audit-only` | **PASS** | 4/4종 SHA-256 `approved_ready`, 누락 0건 |
| 저장소 20문항 BM25 | `uv run python scripts/eval_rag.py --bm25-only` | **PASS** | Calibration Hit@3 `100.0%` / Holdout Hit@3 `100.0%`, 오류 0 |
| Work 38문항 BM25 (v2.2) | `evaluate-questions.py --model bm25` | **PASS** | 1,159/1,159 전체 역추적 `100%`, 4개 분할 실측 완료 |
| Agent Preview CLI | `scripts/agent_preview_smoke.py` (`NS01`, `NS01` CKD, `NS02`) | **PASS** | 환자 조회, RAG 호출, CKD 보류(`unsupported_scope`), `Fake` 인용 차단(`citations_verified=false`), 환자 분리, SSE 규격, 카드 미변경 전부 확인 |
| **Large v2.2 유료 재색인·38문항 평가** | `evaluate-questions.py --model text-embedding-3-large --index var/eval_chroma_final` | **PASS** | **1,159청크 1회 색인 + 38문항 실측 + 162/162 역추적 + 기존 v2.1 색인 보존**, 오류 0, 비용 **\$0.063410** |
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

* **신규 v2.2 Large 색인 (별도 경로 `var/eval_chroma_final/text-embedding-3-large`):** `v20261128T060809Z_f51d456b` (`text-embedding-3-large`, `3072`차원, `1,159`청크, `activated_at: 2026-11-28T06:08:35Z`).
* **기존 v2.1 활성 색인 (`var/chroma_guidelines`) 보존 확인:** `v20261127T182442Z_f2e0ab8e` (`1,142`청크) 무손상 유지.

---

## 5. 20문항 · 38문항 재현 범위 및 v2.2 실측 성능

### 5-1. 데이터셋 재현 가능성
* **저장소 20문항 (`backend/scripts/eval_datasets.json`):** Calibration 10 + 기존 Holdout 10 (완전 재현 가능).
* **Work 38문항 (`NutriSight-실험재현.zip` → `evaluation-questions.json`):** Calibration 10 + 기존 Holdout 10 + Independent 12 + Patient 6 (**38문항 전체 확보 및 실측 완료**).
  * *독립성 구분:* Calibration·기존 Holdout은 과거 쿼리 확장 개선에 참고된 분할이며, **Independent 12문항**이 별도 블라인드 평가셋임. 신규 18문항 안전성 회귀(`test_rag_scope_smoke_18.py`)는 규칙 회귀용이며 38문항 검색 평가와 분리함.

### 5-2. `text-embedding-3-large` v2.2 (1,159청크, 임계값 `0.50`) 실측 결과

| 분할 | 문항 (양성/OOS) | 문서 Hit@1 | 문서 Hit@3 | 문서 Recall@3 | 문서 MRR | 필수 근거 구절 충족 | Raw OOS 거절률 | `safe_search` 결합 OOS 거절률 | 평균 / 중앙값 / P95 (ms) | 오류 |
| --- | :---: | ---: | ---: | ---: | ---: | :---: | ---: | ---: | :---: | ---: |
| `calibration` | 10 (7/3) | 100.0% | 100.0% | 100.0% | 1.000 | **1/7** | 100.0% (3/3) | **100.0% (3/3)** | 233.6 / 201.3 / 488.0 | 0 |
| `holdout` | 10 (7/3) | 85.7% | 100.0% | 92.9% | 0.929 | **3/7** | 100.0% (3/3) | **100.0% (3/3)** | 208.0 / 198.0 / 268.0 | 0 |
| `independent` | 12 (8/4) | 75.0% | 87.5% | 87.5% | 0.792 | **5/8** | 50.0% (2/4) | **100.0% (4/4)** | 203.3 / 194.8 / 256.0 | 0 |
| `patient` | 6 (5/1) | 80.0% | 80.0% | 50.0% | 0.800 | **1/5** | 0.0% (0/1) | **100.0% (1/1)** | 207.6 / 198.3 / 251.2 | 0 |

* **BM25 v2.2 대조 (38문항, 1,159/1,159 역추적):** Calibration 문서 Hit@3 `100.0%` (구절 `3/7`), Holdout Hit@3 `100.0%` (구절 `2/7`), Independent Hit@3 `75.0%` (구절 `6/8`), Patient Hit@3 `100.0%` (구절 `2/5`), Raw OOS 거절률 `0.0%`.
* **핵심 변화 및 검증 항목 확인:**
  * **GLIM Table 5 (`≤50%` 조건) — `CAL-07`:** v2.2 Large Top 3에 **`('glim_2025', 'xml:tbl:jpen2756-tbl-0005#c2', 0.6406)`**이 직접 진입함 (1위 `xml:s19#c3` `0.7277`, 2위 `xml:s19#c2` `0.6931`, 3위 Table 5 `0.6406`). *(단, 과거 Work JSON의 기대 라벨 문자열이 `table:jpen2756-tbl-0005`로 표기돼 있어 자동 채점기 `clause_all` 집계에서는 `xml:tbl:jpen2756-tbl-0005#c*`와 문자열 매핑 차이만 존재)*
  * **`HOLD-07`:** Top 3 전부 `glim_2025` (`xml:s23#c4` `0.7665`, `xml:s5#c5` `0.7342`, `xml:s16#c3` `0.7312`).
  * **`NS09-B` 및 Near-OOS (`IND-NEG-01`/`02`/`03`):** Raw Large 단독에서는 `NS09-B`(`0.5383`), `IND-NEG-01`(`0.5427`), `IND-NEG-02`(`0.5509`)가 임계값 `0.50`을 넘겼으나, **`safe_search_guidelines()` 가드 결합 시 4건 모두 `UNSUPPORTED_SCOPE`로 차단** (`IND-NEG-04`는 유사도 `0.2154` 거절 → **OOS 거절률 100%**, 정상 `NS09-A`·`CAL-07`·`HOLD-07` 과차단 **0건**).
  * **`EvidenceRef` 역추적 및 계약 확인:** `corpus_exact_reverse` **162 / 162 (`100%`)**, `limit=1/3/5` 건수 일치, 동일 질의 반복 재현성 `True`.
  * **이전 v2.1 대비 회귀 여부:** 4개 분할 모든 문서·구절 지표에서 **성능 저하 0건** 유지 + GLIM Table 5 검색 진입 + 가드 결합 OOS 100% 개선.

---

## 6. 유료 호출 승인 여부 및 실제 비용 기록

* **승인 여부:** **승인 완료** (형주 승인 및 구글 드라이브 1회성 키 제공 → 실행 직후 로컬 임시 키 파일 즉시 삭제)
* **사용 모델 / 공식 단가:** `text-embedding-3-large` / USD 0.13 per 1M input tokens
* **실제 사용량 및 비용 (중복 재색인 0건):**

| 단계 | API 호출 수 | 입력 토큰 | 오류 수 | 추정 비용 (USD) | 비고 |
| --- | ---: | ---: | ---: | ---: | --- |
| v2.2 1,159청크 신규 색인 (1회) | 20 | 485,325 | 0 | \$0.063092 | `76.0s`, `v20261128T060809Z_f51d456b` |
| 38문항 평가 질의 (10+10+12+6) | 38 | 1,972 | 0 | \$0.000256 | 4개 분할 전체 |
| 계약·재현성 확인 (`limit=1/3/5`) | 5 | 475 | 0 | \$0.000062 | `repeated_equal=True` |
| **합계** | **63회** | **487,772** | **0** | **\$0.063410** | 제안 상한 **\$0.15** 대비 42.3% |

---

## 7. SMTP 최신 `develop` (`9d56fbc`) 호환성 검증 (읽기 전용)

* `67a1a35..9d56fbc` 신규 팀 변경: PR #17(`frontend-shell-upload`) + PR #19(저울 실측 평가 문서 제외).
* **공통 계약·의존성 대조:** `GuidelineSearch`, `PatientDataPort`, `EvidenceRef`, `RecommendationCard`, `wiring.py`, `pyproject.toml`, `uv.lock` 변경 충돌 **0건**.
* `git merge-tree --write-tree HEAD upstream/develop` 읽기 전용 모의 병합 결과: **충돌 0건 (`PASS`)**.
* 실제 `upstream/develop` 병합 후 통합 `pytest`는 보존 규칙상 `NOT RUN`.

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

1. **RAG 자체 완료 기준 달성:** 전체 회귀 `655 passed`, 공식 4/4종 SHA-256 일치, 안전 검색·인용 검증, `text-embedding-3-large` v2.2(1,159청크) 38문항 실측 및 162/162 역추적, T5 연결 계약 정리 완료.
2. **규칙 가드의 표현 한계:** `detect_unsupported_scope()`는 보수적 정규식 기반이므로 T5 LLM 에이전트 단의 임상 보류 정책과 이중 방어 필수.
3. **별도 후속 과제 (`NOT RUN`):** T5 실제 LLM Agent 통합, 환자별 추천 생성 E2E, 의료진 승인 워크플로, Windows 기본 Python(`app_lock.py` `fcntl`) 호환 협의, 실제 의료 환경 임상 안전성 검증.
