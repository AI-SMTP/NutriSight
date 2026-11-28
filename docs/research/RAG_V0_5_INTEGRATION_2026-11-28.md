# NutriSight RAG v0.5 통합 회귀 검증 보고서 (2026-11-28)

## 1. 통합 대상 및 브랜치 정보

| 항목 | 값 |
| --- | --- |
| 저장소 (개인 Fork) | `HJ-GJ/NutriSight` |
| **RAG v0.5 통합 브랜치** | `feature/rag-v0-5-integration-20261128` |
| 기반 브랜치 (검색 고도화) | `feature/rag-retrieval-quality-20261128` (`a8f832e37a801718c5d9f1aac30b0ca6addd690a`) — v0.3 안전·GLIM 표 + v0.4 Agent 미리보기 + Hybrid RRF + ONNX BGE Reranker 포함 |
| 통합된 수정 브랜치 (Issue #20) | `fix/rag-issue20-fail-closed` (`0b85c9f3e177223b46efc9beb7b051e13e9fdc30`) — BM25 승인 원문 누락·0청크 fail-closed(`ConfigError`) + Codex P2 테스트 격리 보강 |
| 병합 커밋 SHA | `b0e5907` (무충돌 자동 병합, 신규 기능 미추가) |
| 보존된 브랜치 / PR | `integration/rag-t2-20261128` (`75f122c`, Draft PR `AI-SMTP/NutriSight#18`), `AI-SMTP/NutriSight:develop` (`9d56fbc`), `main` (`402f738`) — 일체 미수정 |
| 공용 계약 / 기본값 | `guideline_types.py`, `tests/contracts/`, `config.py`, `GUIDELINE_SEARCH=fake` 유지 |
| 유료 API / GPU 사용 | **0건 (`$0.00`)** |

---

## 2. 통합된 작업 범위 (신규 기능 추가 없음)

1. **Issue #20 Fail-Closed 통합**:
   - `backend/app/recommender/rag_sources.py`: `review_status == "approved"` 아티팩트의 `missing_file`을 `approved_failures`에 포함해 `fail_on_approved_issue=True` 시 `ValueError`로 차단.
   - `backend/app/recommender/bm25_search.py`: `Bm25GuidelineSearch.from_sources_dir`에서 청크 0개 시 `ValueError` 발생.
   - `backend/app/wiring.py`: `_build_bm25_search`에서 `(ValueError, OSError)`를 `ConfigError`로 변환 (`hybrid` / `hybrid_rerank` 빌더도 `_build_bm25_search`를 호출하므로 동일하게 fail-closed 적용).
   - `backend/tests/test_bm25_search.py`: fail-closed 회귀 테스트 8건 및 환경변수 격리 강화 반영.
2. **검색 고도화 및 기존 v0.3/v0.4 기능 보존**:
   - `HybridGuidelineSearch` (BM25 + Dense + RRF + Dense-empty OOS 가드), `OnnxBgeReranker` / `RerankedGuidelineSearch` (`RERANK_UNAVAILABLE` 자동 fallback).
   - `safe_search_guidelines`, `verify_evidence_refs`, GLIM XML 표 파싱(`1,159`청크), `app/agent_preview/` 읽기 전용 미리보기.
3. **문서 동기화**:
   - `docs/research/RAG_PROGRESS_MASTER.md`, `docs/research/RAG_PR18_REVIEW_VALIDATION_2026-11-28.md`, `docs/research/RAG_RETRIEVAL_QUALITY_UPGRADE_2026-11-28.md`가 단일 v0.5 통합 브랜치에서 모두 정합.

---

## 3. 통합 회귀 테스트 및 교차검수 결과 (`Linux Ubuntu 24.04 / Python 3.12.16`)

| 검증 항목 | 실행 명령 | 결과 |
| --- | --- | --- |
| 의존성 잠금 확인 | `cd backend && uv sync --locked` | **PASS** (113 packages, `uv.lock` 무변경) |
| 정적 검사 (린트) | `uv run ruff check .` | **PASS** (0 errors) |
| 정적 검사 (포맷) | `uv run ruff format --check .` | **PASS** (84 files already formatted) |
| **전체 통합 회귀 테스트** | `uv run pytest -q` | **PASS — 705 passed** in 101.13s (0 failed, 0 skipped; 검색 고도화 698 + Issue #20 순증 7) |
| 승인 원문 SHA-256 감사 | `uv run python scripts/index_guidelines.py --audit-only` | **PASS** (`AUDIT_OK`, 4/4종 approved_ready) |
| 독립 Agent 미리보기 스모크 | `uv run python scripts/agent_preview_smoke.py --patient NS01` | **PASS** (`SMOKE_OK`, 읽기 전용 SSE, 카드 미변경) |
| **Codex CLI (`gpt-6.2-sol`) 병합 교차검수** | `run-codex.sh exec -m gpt-6.2-sol -s read-only` (`a8f832e..b0e5907`) | **PASS WITH MINOR NOTES** (P0/P1 결함 **0건**) |

### Codex CLI P2 참고 메모 (추후 Stage B/C 반영 후보)
- `hybrid` / `hybrid_rerank`가 `_build_bm25_search`를 호출해 실패할 때 오류 메시지 접두어가 `GUIDELINE_SEARCH=bm25 초기화 실패:`로 표시됨 (실제 동작은 정상적으로 `ConfigError` fail-closed 전파).
- `hybrid` / `hybrid_rerank` 상위 빌더에서 `ConfigError` 전파를 직접 확인하는 전용 테스트는 추후 설정 단일화(`#22`) 시 함께 보강 권장.

---

## 4. 미해결 및 승인 대기 사항
- 팀 저장소(`AI-SMTP/NutriSight`) `develop`/`main` 병합 및 기존 Draft PR `#18`(`integration/rag-t2-20261128`) 수정은 사용자·팀 승인 전까지 보류.
- 후속 팀 이슈 `#21`(T5 계약 합의), `#22`(T4 병합 후 `Settings` 이관), `#23`(권고 번호 검수), `#24`(예외/경로/의존성 정리), `#25`(Windows `fcntl` OS 범위 결정)은 기존 로드맵대로 별도 단계 진행.
