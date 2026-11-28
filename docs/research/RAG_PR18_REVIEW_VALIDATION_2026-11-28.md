# NutriSight RAG — PR #18 리뷰 반영 및 Stage A(Issue #20) 검증 보고서 (2026-11-28)

## 1. 기준선 및 원격 저장소 비교

| 항목 | 값 |
| --- | --- |
| 팀 공식 저장소 (`upstream`) | `AI-SMTP/NutriSight` — `develop@9d56fbc`, `main@402f738`, 신규 브랜치 `feature/patient-recommendation-api` |
| 개인 Fork (`origin`) | `HJ-GJ/NutriSight` — Draft PR #18 head `integration/rag-t2-20261128@75f122c` (PR 생성 시 base `97ed3cc`) |
| Stage A 작업 브랜치 | `fix/rag-issue20-fail-closed` (`75f122c` 분기, force push 없음) |
| PR #18 리뷰어 / 이슈 | `smalljiny` (2026-11-28 16:24 KST) — 병합 전 수정 권고 **#20**, 후속 이슈 **#21–#25** (전부 open) |
| 실행 환경 | Linux Ubuntu 24.04, Python 3.12.16, `uv sync --locked` (113 packages, `uv.lock` 무변경) |
| 유료 API 호출 | **0건 (`$0.00`)** |

---

## 2. Stage A (Issue #20) — 오류 재현(RED) → 수정 → 회귀 검증(GREEN)

### 2.1 현상 및 원인
- **현상**: `GUIDELINE_SEARCH=bm25`로 앱을 기동할 때 `docs/research/rag-sources/`에 승인 원문 PDF/XML이 없어도 오류 없이 **청크 0개 색인**으로 정상 기동하며, 이후 모든 검색이 빈 튜플 `()`만 반환.
- **원인**:
  1. `backend/app/recommender/rag_sources.py:490`: `review_status == "approved"` 아티팩트의 `hash_mismatch`·`invalid_format`만 `approved_failures`에 추가하고 `missing_file`은 누락.
  2. `backend/app/recommender/bm25_search.py:203`: `load_guideline_chunks`가 0청크를 반환해도 `Bm25GuidelineSearch.from_sources_dir`가 그대로 0청크 인스턴스를 생성.
  3. `backend/app/wiring.py:86`: BM25 초기화 실패를 팀 규약 예외 `ConfigError`로 변환하지 않음.
  4. `backend/tests/test_bm25_search.py:158`: 빈 `tmp_path`에서 `create_app(Settings(guideline_search="bm25"))` 성공을 정상 동작으로 고정.

### 2.2 RED 재현 증거 (`75f122c` 수정 전)
```text
REPRO_BM25_DIRECT: chunks= 0 search= ()
REPRO_CREATE_APP: started_without_error= True chunks= 0
```

### 2.3 수정 내용 (공용 계약·Fake 기본값 무변경)
1. `backend/app/recommender/rag_sources.py`: `review_status == "approved"`이고 `art_status in {"missing_file", "hash_mismatch", "invalid_format"}`이면 `approved_failures`에 추가해 `fail_on_approved_issue=True`일 때 `ValueError`로 fail-closed 차단 (`pending` 누락은 기존 정책대로 허용).
2. `backend/app/recommender/bm25_search.py`: `Bm25GuidelineSearch.from_sources_dir`에서 적재된 청크가 0개이면(예: 매니페스트에 승인 문헌이 0건) `ValueError` 발생.
3. `backend/app/wiring.py`: `_build_bm25_search`에서 `(ValueError, OSError)`를 포착해 팀 규약 `ConfigError("GUIDELINE_SEARCH=bm25 초기화 실패: ...")`로 변환.
4. `backend/tests/test_bm25_search.py`: 기존 역전 테스트 제거 및 fail-closed 회귀 테스트 7건 추가(전체 누락, 일부 누락, 0청크 승인 XML, pending 전용 매니페스트, 해시 불일치/형식 불일치, 유효 승인+pending 누락 정상 기동/검색/역조회/무관질의 `()`, Fake 기본 기동 불변).

### 2.4 GREEN 재현 및 회귀 검증 증거
```text
GREEN_BM25_DIRECT: ValueError 승인 문헌 무결성 검증 실패: espen_geriatrics_pdf: 원문 파일 누락: ...
GREEN_CREATE_APP: ConfigError GUIDELINE_SEARCH=bm25 초기화 실패: 승인 문헌 무결성 검증 실패: ...
FAKE_NORMAL: FakeGuidelineSearch
BM25_FAIL_EMPTY: ConfigError True
CHROMA_FAIL_NO_KEY: GuidelineSearchError True
```
- `uv sync --locked`: **PASS** (113 packages)
- `uv run ruff check .` / `uv run ruff format --check .`: **PASS** (0 errors, 72 files formatted)
- `uv run pytest -q` (`fix/rag-issue20-fail-closed`): **630 passed**, 0 failed, 0 skipped (50.12s; 기존 623 passed 대비 +7 net tests)
- `upstream/develop@9d56fbc` 로컬 임시 병합 시험: 충돌 **0건**(`668 passed`, P2 테스트 1건 추가 전 `893ea15` 기준; P2 추가는 `test_bm25_search.py` 테스트 격리만 보강)
- **Codex CLI (`gpt-6.2-sol`) 교차검수**: `PASS WITH MINOR NOTES` (P0/P1 결함 **0건**; P2 환경변수 격리 및 잘못된 매니페스트/`RAG_BM25_MIN_SCORE` `ConfigError` 변환 테스트 보완 반영 완료)

---

## 3. 이슈 #20–#25 전체 상태 및 승인 게이트

| 이슈 | 단계 | 상태 | 수정 파일 / 근거 | 잔여 위험 | 승인 필요 여부 |
| --- | --- | --- | --- | --- | --- |
| **#20** BM25 원문 누락 시 0청크 기동 | **Stage A** | **DONE** *(리뷰·PR 반영 대기)* | `rag_sources.py`, `bm25_search.py`, `wiring.py`, `test_bm25_search.py` (RED→GREEN, 629 passed) | PR #18 head(`integration/rag-t2-20261128`) 반영 방식 사용자 승인 필요 | **PR 반영 승인 필요** |
| **#21** `resolve_evidence` 및 검색 예외 계약 | Stage B | **BLOCKED** *(팀 계약 합의 대기)* | `guideline_types.py`, `FakeGuidelineSearch`, `rag-agent-handoff.md` | Fake에서 `resolve_evidence` 미지원, `OPENAI_API_KEY` 누락 시 `GuidelineSearchError` vs `ConfigError` 불일치 | **T5 담당 계약 합의 필수** |
| **#22** RAG 설정 `Settings` 단일화 · `var_dir` 통일 | Stage C | **BLOCKED** *(T4 #5 병합 후 권장)* | `config.py`, `wiring.py`, `index_guidelines.py`, `eval_rag.py` | `_read_rag_env` 3곳 복제, `backend/.env` 테스트 누출 가능 | **T4 병합 후 진행** |
| **#23** 권고 번호 `R<n>` 오귀속 검수 | Stage B | **NOT RUN** *(Stage B 예정)* | `rag_sources.py:329-344, 405-426` | 청크 끝부분 헤더로 인한 권고 번호 오귀속 가능성(실추천 전 필수 게이트) | **locator 변경 시 재색인 비용 승인** |
| **#24** 예외 처리·경로 검사·의존성 분리 | Stage C | **NOT RUN** *(Stage C 예정)* | `chroma_search.py`, `rag_sources.py`, `pyproject.toml`, `bm25_search.py` | 광범위 `except Exception: pass`, `relative_path` 경계 검사, API 예외 메시지 마스킹 | **의존성 분리 시 팀 합의** |
| **#25** Windows `app_lock` `fcntl` import | Stage C | **BLOCKED** *(OS 범위 팀 확정 대기)* | `backend/app/storage/app_lock.py` (develop 기존 이슈) | Windows 네이티브 Python 기동 불가 (Linux/WSL 정상) | **공동 백엔드 팀 결정 필요** |

---

## 4. 후속 단계(Stage B/C/D) 팀 계약 합의 요청 사항

1. **T5 담당자 합의 요청 (`#21`, `#6`)**:
   - **선택지 A (권장)**: `GuidelineSearch` Protocol에 `async def resolve_evidence(self, doc_id: str, section: str) -> GuidelineHit | None`을 추가하고 `FakeGuidelineSearch`도 `FIXED_PASSAGES` 기반으로 구현.
   - **선택지 B**: 별도 `EvidenceResolver` Protocol로 분리하고 미지원 구현을 타입으로 구분.
   - 공통: 검색 실행 오류 `GuidelineSearchError`를 `guideline_types.py`에 공식 정의하고, 기동 설정 오류는 `ConfigError`로 통일.
2. **T4 담당자 조율 요청 (`#22`, `#5`, pyright)**:
   - T4 병합 직후 `wiring.py` import·`uv.lock`·`chroma_search.py:413` `collection.add(embeddings=...)` 타입 오류를 최신 `develop` 기준으로 1회 정리.
3. **공동 백엔드 팀 결정 요청 (`#25`)**:
   - 파일럿 OS 범위를 Linux/WSL/macOS로 명시할지, Windows 네이티브(`filelock` 또는 `msvcrt.locking`)를 지원할지 확정.

---

## 5. PR #18 리뷰 코멘트 초안 (`smalljiny` 회신용)

> 진철 님, 꼼꼼한 검증과 후속 이슈 정리(#20–#25) 감사합니다!
>
> 머지 전 수정 권고해 주신 **#20 (BM25 원문 누락 시 0청크 기동)**을 `fix/rag-issue20-fail-closed` 브랜치에서 최소 범위로 수정·검증했습니다:
> - `rag_sources.py`: `review_status == "approved"` 아티팩트의 `missing_file`을 `approved_failures`에 포함해 `fail_on_approved_issue=True` 시 `ValueError`로 fail-closed 차단 (`pending` 누락은 기존 정책 유지)
> - `bm25_search.py`: `from_sources_dir`에서 적재 청크가 0개일 때 `ValueError` 발생
> - `wiring.py`: `_build_bm25_search`에서 `(ValueError, OSError)`를 `ConfigError`로 변환
> - `test_bm25_search.py`: 기존 빈 디렉터리 성공 테스트를 fail-closed 검증(전체/일부 누락, 0청크, pending 전용, 해시/형식 오류) 및 유효 fixture 정상 검색·역조회 테스트로 교체 (`GUIDELINE_SEARCH=fake` 기본 기동 불변)
> - 검증: `uv sync --locked`, `ruff check/format` PASS, `pytest -q` **629 passed** (0 failed, 0 skipped), 최신 `develop@9d56fbc` 로컬 병합 시험 충돌 없음 확인
>
> 확인해 주시면 해당 커밋을 PR #18 브랜치(`integration/rag-t2-20261128`)에 반영하겠습니다. 후속 이슈 #21(T5 계약 합의), #22(T4 병합 후 Settings 이관), #23(권고 번호 검수), #24(정리), #25(OS 범위)는 팀 합의에 맞춰 순차 진행하겠습니다.

---

## 6. 학습용 한국어 요약 (왜 발생했고 어떻게 재발 방지하는가)

- **왜 발생했나?**
  - `load_guideline_chunks`가 "해시가 틀리거나 형식이 깨진 파일"만 오류로 보고, "승인된 파일 자체가 아예 없는 경우(`missing_file`)"는 건너뛰도록 작성되어 있었습니다. 게다가 테스트(`test_bm25_search.py`)도 빈 디렉터리에서 앱이 정상 기동하는 것을 통과 조건으로 고정해 두어, 요구사항(fail-closed)과 반대되는 동작을 테스트가 보호하고 있었습니다.
- **왜 위험한가?**
  - 원문 PDF/XML은 `.gitignore` 대상이라 새 PC나 배포 환경에 복사하지 않으면 누락되기 쉽습니다. 이때 앱이 조용히 0청크 색인으로 켜지면 모든 임상 질의가 "근거 없음(`()`)"으로만 응답해 장애 원인을 알 수 없게 됩니다.
- **어떻게 재발 방지했나?**
  - **요구사항–실패 시나리오–테스트 1:1 연결**: "승인 원문 전체 누락 / 일부 누락 / 0청크 / pending 전용 / 해시·형식 오류" 5가지 실패 경로를 모두 `ConfigError`로 차단하고, "정상 색인에서 무관한 질의 → `()`"와 "구성 실패 → `ConfigError`"를 명확히 분리해 회귀 테스트로 고정했습니다.
