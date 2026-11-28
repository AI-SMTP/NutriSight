# NutriSight RAG v0.5.1 — 팀 통합(T4 `develop@99d388e`) 검증 보고서 (2026-11-28)

## 1. 기준 및 최종 SHA

| 항목 | 브랜치 | 기준 SHA | 최종 검증 SHA | 비고 |
| --- | --- | --- | --- | --- |
| 팀 공식 `develop` (T4 `#26` 병합) | `AI-SMTP/NutriSight:develop` | `99d388e12b97c1a742ca7767e7ef299b4a240167` | (미수정) | `AppRuntime`, `SqlitePatientData`, `RECOMMENDATION_GENERATORS`, `pyright` 도입 |
| 기존 Draft PR `#18` head | `HJ-GJ:integration/rag-t2-20261128` | `75f122c71e3a65208c0215e8f9aacd2b8a030d9d` | (승인 전 미수정) | `develop@99d388e` 대비 `CONFLICTING` |
| 기존 Draft PR `#27` head | `HJ-GJ:feature/rag-v0-5-integration-20261128` | `7fee767ec4c6f60e2b17e66e5e1a8619127e6c7b` | (승인 전 미수정) | `develop@99d388e` 대비 `CONFLICTING` |
| **PR `#18`용 T4 동기화 브랜치** | `HJ-GJ:sync/rag-pr18-develop-t4-20261128` | `0b85c9f` (`fix/rag-issue20-fail-closed`) + `99d388e` | **`cd52c69b61301b13ce18274f186859c15274a0a5`** | Issue `#20` + T4 호환 최소 변경만 포함 |
| **v0.5.1(PR `#27`용) T4 동기화 브랜치** | `HJ-GJ:sync/rag-v0-5-1-develop-t4-20261128` | `7fee767` (v0.5) + `99d388e` | `00743df` + 본 보고서 커밋 | v0.5 전체 기능 + T4 호환 + Pyright 0 errors + Hybrid/Reranker 초기화 테스트 |

---

## 2. 충돌 원인 및 해결 방법

| 대상 파일 | 충돌 / 오류 원인 | 해결 방법 |
| --- | --- | --- |
| `backend/app/wiring.py` | T4(`#26`)가 `from app.config import ConfigError, Settings, storage_paths` 및 `AppRuntime`/`SqlitePatientData`/`RECOMMENDATION_GENERATORS` 추가; RAG는 `BACKEND_ENV_FILE`, `dotenv_values` 및 `GUIDELINE_SEARCHES` 등록 추가 | 양쪽 import를 단일 줄로 통합(`BACKEND_ENV_FILE, ConfigError, Settings, storage_paths`), `PATIENT_DATA_PORTS`의 `(Settings, AppRuntime)` 시그니처와 `GUIDELINE_SEARCHES`의 `(Settings)` 시그니처·`fake` 기본값을 모두 원형 보존 |
| `backend/uv.lock` | T4가 `pyright>=1.1.414` 추가, RAG가 `chromadb`/`openai`/`pypdf` 추가 | `upstream/develop` 기준에서 양쪽 `pyproject.toml`을 합친 뒤 `uv lock` · `uv sync --locked`로 정식 재생성 (118 packages, 임의 ours/theirs 미사용) |
| `backend/app/recommender/chroma_search.py:413` | `collection.add(embeddings=vectors)`에 `list[list[float]]` 전달 시 `chromadb`의 `PyEmbedding` (`Sequence[float]`) 불변(invariant) `list` 타입 불일치로 Pyright 오류 1건 | `# type: ignore`/`cast` 없이 `embeddings_payload: list[Sequence[float]] = [list(v) for v in vectors]`로 공변 타입 정합 |
| `backend/app/recommender/{hybrid_search,reranker,retrieval_guard}.py` (v0.5.1) | `callable(getattr(..., "resolve_evidence", None))`가 Pyright에서 `(...) -> object`로 좁혀져 `"object" is not awaitable` 오류 7건 발생 | `inspect.iscoroutinefunction(...)`으로 교체해 런타임 안전성과 Pyright `Awaitable` 타입 추론을 동시에 충족 (0 errors) |
| `backend/tests/test_hybrid_rerank.py` (v0.5.1) | Hybrid / Hybrid+Reranker 초기화 실패 시 `ConfigError` 전파 전용 테스트 부재 | `test_wiring_hybrid_and_rerank_fail_closed_when_approved_sources_missing` 추가 (`hybrid`, `hybrid_rerank` 2개 모드 검증) |

---

## 3. 필수 검증 실행 결과 (`Linux Ubuntu 24.04 / Python 3.12.16`, 유료 API 0건)

| 검증 항목 | PR `#18`용 (`sync/rag-pr18-develop-t4-20261128` @ `cd52c69`) | v0.5.1용 (`sync/rag-v0-5-1-develop-t4-20261128`) |
| --- | --- | --- |
| `uv sync --locked` | **PASS** (118 packages) | **PASS** (118 packages) |
| `uv run ruff check .` | **PASS** (0 errors) | **PASS** (0 errors) |
| `uv run ruff format --check .` | **PASS** (137 files) | **PASS** (149 files) |
| `uv run pyright` | **PASS — 0 errors** *(기존 T2/T4 `seed_file.py:79` warning 1건만 존재)* | **PASS — 0 errors** *(기존 `seed_file.py:79` warning 1건만 존재)* |
| `uv run pytest` (전체 스위트) | **1,329 passed** (128.53s) + **1 passed** (0.39s, 단독) = **1,330/1,330** | **1,406 passed** (200.40s) + **1 passed** (단독 확인) = **1,407/1,407** *(아래 T4 플래키 참고)* |
| `index_guidelines.py --audit-only` | (동일 4/4종 코퍼스) | **PASS** (`AUDIT_OK`) |
| `agent_preview_smoke.py --patient NS01` | 해당 없음 (v0.2 범위) | **PASS** (`SMOKE_OK`) |
| Codex CLI (`gpt-6.2-sol`) 교차검수 | Issue `#20` 검수 완료 (`PASS WITH MINOR NOTES`, P0/P1 0건) | v0.5.1 T4 통합 diff 검수 완료 (**`PASS WITH MINOR NOTES`**, P0/P1 **0건**) |

### 관찰된 기존 T4 간헐적 플래키 테스트 (미수정·정직 보고)
- 대상: `tests/api/test_recommendation_writes.py::test_shutdown_waits_running_patch_before_releasing_lock` (T4 PR `#26` 원본 테스트, RAG 변경과 무관)
- 현상: 2 vCPU Linux VM에서 전체 스위트 연속 실행 시 간헐적으로 `stopping.result(timeout=TIMEOUT)`에서 `TimeoutError`가 발생하며 실패 teardown의 `ThreadPoolExecutor.__exit__`가 대기 상태로 머무름. 단독 3회 반복 측정 시 2회 0.3초 통과 / 1회 타임아웃 확인.
- 조치: 팀원 소유 T4 테스트를 임의 수정하지 않고 원형 보존하며, 전체 스위트(`1,329` / `1,406 passed`)와 단독 재실행 결과를 분리 기록함.

---

## 4. 기존 기능 보존 및 PR별 반영 계획

### 기존 기능 보존 확인
- **REQ-01 (Fake 기본값)**: `Settings().guideline_search == "fake"` 유지, 원문·API 키 없이 정상 기동 검증.
- **REQ-02 (BM25 / Chroma / Hybrid / Reranker)**: 모든 검색기 계약·단위·회귀 테스트 통과.
- **REQ-03 (Issue `#20` fail-closed)**: `bm25`, `hybrid`, `hybrid_rerank` 모두 승인 원문 누락 시 `ConfigError` 차단 검증.
- **REQ-04 / REQ-05 (T4 환자·추천 API 및 공통 계약)**: `AppRuntime`, `SqlitePatientData`, `RECOMMENDATION_GENERATORS`, 공통 계약 파일(`guideline_types.py`, `config.py`, `tests/contracts/`) 100% 보존.

### PR별 반영 계획 (형주/GP 승인 후 실행)
1. **PR `#18` (`integration/rag-t2-20261128`) 반영 옵션**: 최소 변경(Issue `#20` + T4 호환 + Pyright 0 errors)만 담은 `sync/rag-pr18-develop-t4-20261128`(`cd52c69`)를 PR `#18` head로 fast-forward/병합.
2. **PR `#27` (`feature/rag-v0-5-integration-20261128`) 반영 옵션**: v0.5 전체 + T4 호환 + Pyright 0 errors + Hybrid/Reranker 초기화 테스트 + 마스터 보고서 최신화를 담은 `sync/rag-v0-5-1-develop-t4-20261128`를 PR `#27` head로 반영.
   - *(권고: 팀 리뷰 중복을 줄이기 위해 PR `#18`과 PR `#27` 중 어떤 PR을 1차 머지 대상으로 삼을지 팀 합의 후 해당 PR head만 갱신)*

---

## 5. 남은 위험 및 승인 필요 사항
- **PR head 갱신 / 팀 `develop` 병합**: 사용자 및 팀 승인 전까지 기존 PR `#18`, `#27` head 및 `AI-SMTP/NutriSight:develop` 미변경 유지.
- **T4 플래키 테스트**: `test_shutdown_waits_running_patch_before_releasing_lock`의 2 vCPU 환경 간헐 타임아웃은 T4 담당자와 공유 필요.
- **Codex P2 참고**: `inspect.iscoroutinefunction`은 일반 `async def`·`partial`·`AsyncMock`을 지원하지만 `async __call__` 객체는 제외함(현재 코드베이스 모든 구현은 `async def` 메서드); 향후 `#21`에서 `resolve_evidence`가 공통 Protocol에 정식 편입되면 `getattr` 동적 탐색 자체를 제거 예정.
- **후속 팀 이슈 (`#21`–`#25`)**: `#21`(T5 계약 합의), `#22`(`Settings` 단일화 — T4 병합 완료로 착수 가능), `#23`(권고 번호 검수), `#24`(정리), `#25`(Windows `fcntl` OS 범위 결정).
