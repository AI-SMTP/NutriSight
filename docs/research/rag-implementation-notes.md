> **이력 보존 공지 (2026-11-28):** 아래 본문은 `74f061e`까지의 **과거 3종·1,077청크·192 passed** 실험 기록입니다. 당시 GLIM 미확보 상태를 최신 사실로 인용하지 마세요. `b7801cf`에서 GLIM 2025 **JPEN XML**이 승인되었고, Work 4종·1,142청크·38질의·195 passed 결과는 [마스터 진행 보고서](RAG_PROGRESS_MASTER.md) 및 [독립 성능평가 2026-11-28](RAG_EVALUATION_2026-11-28.md)에 별도로 정리했습니다. **기존 실험 원문은 재현성을 위해 보존합니다.**

# 가이드라인 검색(RAG) 트랙 구현 및 실험 기록 (v0.2 안정화)

**브랜치:** `feature/recommender-chroma-rag` (기준: `origin/develop` `5cbf0da`, Fork merge `e955445`)  
**상태:** P0 안정화 · P1 근거 추적/평가 재현성 · Agent 인계 문서 · 계약 검증 완료 (공용 계약 무수정)

---

## 1. PR #10 골격 대비 추가·고도화한 사항

팀 공용 계약 파일(`backend/app/recommender/guideline_types.py`, `backend/tests/contracts/guideline.py`, `backend/app/config.py`, `backend/tests/conftest.py`)과 기존 테스트는 **단 한 줄도 수정하지 않았습니다.**

| 파일 | 역할 및 v0.2 안정화 핵심 |
| --- | --- |
| `backend/app/recommender/source_manifest.json` | 공식 4종(5개 아티팩트: PDF 4 + GLIM JPEN XML 1) 명시적 승인 매니페스트. 전체 64자리 SHA-256, `review_status`(`approved`/`pending`), PDF·XML 출처 URL 분리 관리(자동 승인 금지) |
| `backend/app/recommender/rag_sources.py` | 매니페스트·`README.md`·로컬 파일 3자 감사(`audit_source_manifest`), 전체 64자리 SHA-256 검증, 고유 근거 식별자(`R<번호>` 검증 추출 또는 `p.<n>#c<k>`/`xml:s<n>#c<k>`), 발행 전 `(doc_id, section)` 중복 차단 |
| `backend/app/recommender/chroma_search.py` | Windows 안전 버전 분리 재색인(`versions/<id>/` + 무결성 검증 후 `active_pointer.json` 임시 파일 `os.replace()` 원자 교체), 무변경 시 0 API 호출 스킵, 실패 시 이전 정상 색인 보존, `resolve_evidence(doc_id, section)` 역추적 |
| `backend/app/recommender/bm25_search.py` | 순수 파이썬 BM25Okapi + NFKC 정규화 + 보수적 한국어 조사 제거(오분절 방지) + 복합명사 분해·결합 + 임상 단위(`g/kg`, `kcal/kg`, `50%`) 보존 + 매니페스트 승인 정책 및 `resolve_evidence` 지원 |
| `backend/app/recommender/query_expander.py` | 한→영 및 영→한 양방향 임상 용어 쿼리 확장 (중복 토큰 제거로 BM25 과증폭 방지) |
| `backend/app/wiring.py` | `GUIDELINE_SEARCHES`에 `"chroma"`, `"bm25"` lazy-import 등록 (기본값 `GUIDELINE_SEARCH=fake` 유지) |
| `backend/scripts/index_guidelines.py` | `--audit-only` 매니페스트 감사 및 버전 분리 Chroma 색인 생성 CLI (`RAG_SOURCES_DIR`·`RAG_CHROMA_DIR` 환경변수 정렬) |
| `backend/scripts/eval_datasets.json` · `backend/scripts/eval_rag.py` | Calibration(10건) / Independent Holdout(10건) 분리 데이터셋 + BM25 vs Small vs Large 재현 평가 스크립트 (임계값 스윕, P95 지연, 토큰·비용, 누락 문헌 명시) |
| `backend/tests/test_chroma_search.py` · `backend/tests/test_bm25_search.py` | `GuidelineSearchContract` 상속 + 재색인 실패 롤백 + 매니페스트 승인 차단 + 고유 근거 역추적 + BM25 한국어 토큰화 테스트 (총 30건, 외부 네트워크 호출 0건) |
| `docs/research/rag-agent-handoff.md` | T5 처방 추천 에이전트 담당자용 인터페이스·예외·토큰 예산·NS07/NS09 시나리오 인계서 |

---

## 2. 실제 공식 원문 기반 재현 평가 결과 (v0.2 라이브 API)

- **데이터 구분:** 로컬에 확보된 실제 공식 원문 PDF (**3/4종 승인·적재**, 총 1,077청크)
  - `espen_geriatrics` (`espen-practical-guideline-geriatrics.pdf`, SHA-256 `b5456f29...f5355c`) — **approved (318청크)**
  - `kjg_elderly_nutrition_2019` (`kjg-2019-73-4-196-elderly-nutrition.pdf`, SHA-256 `5b3c2a0d...1c86ef`) — **approved (22청크)**
  - `khna_pressure_injury` (`khna-pressure-injury-guideline.pdf`, SHA-256 `ad6a5b51...be2d838`) — **approved (737청크)**
  - `glim_2025` (PDF/XML 모두 로컬 미확보, `review_status=pending`) — **누락 (4종 전체 검증 아님을 명시)**

### A. BM25 vs `text-embedding-3-small` vs `text-embedding-3-large` (기준 임계값 `0.50` / BM25 `>0`)

| 검색기 | 데이터셋 | 평가 질의(누락 제외) | Hit@1 | Hit@3 | Recall@3 | MRR | OOS 거절률 | 평균(ms) | 중앙값(ms) | P95(ms) | 오류 | 토큰 / 추정비용(USD) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `bm25` | Calibration | 6 (+누락 1, OOS 3) | 66.7% | 100.0% | 100.0% | 0.806 | 0.0% | 2.6 | 2.8 | 4.4 | 0 | 0 / \$0 |
| `bm25` | Holdout | 6 (+누락 1, OOS 3) | 66.7% | 66.7% | 58.3% | 0.667 | 0.0% | 1.8 | 1.7 | 3.1 | 0 | 0 / \$0 |
| `text-embedding-3-small` | Calibration | 6 (+누락 1, OOS 3) | 66.7% | 66.7% | 66.7% | 0.667 | 100.0% | 214.5 | 155.5 | 707.3 | 0 | 1,388 / \$0.000028 (캐시 재사용) |
| `text-embedding-3-small` | Holdout | 6 (+누락 1, OOS 3) | 66.7% | 66.7% | 58.3% | 0.667 | 100.0% | 148.8 | 145.4 | 165.7 | 0 | 1,388 / \$0.000028 |
| `text-embedding-3-large` | Calibration | 6 (+누락 1, OOS 3) | **100.0%** | **100.0%** | **100.0%** | **1.000** | **100.0%** | 189.0 | 167.4 | 371.2 | 0 | 472,709 / \$0.061452 (최초 색인 포함) |
| `text-embedding-3-large` | Holdout | 6 (+누락 1, OOS 3) | 66.7% | 66.7% | 58.3% | 0.667 | **100.0%** | 160.0 | 160.8 | 168.4 | 0 | 472,709 / \$0.061452 |

- **공통 무결성 검증 (`bm25`, `small`, `large` 모두 통과):**
  - `limit=1 / 3 / 5` 결과 수 일치, 동일 질의 반복 재현성 `True`, 반환된 모든 `(doc_id, section)`에 대한 `resolve_evidence` 정확 역추적 `100%` 통과.

### B. 임계값 민감도 분석 (`0.40` / `0.45` / `0.50` / `0.55`)

- `text-embedding-3-large` 기준 `0.40`에서는 Calibration OOS 거절률이 `66.7%`로 떨어졌으나, **`0.45`–`0.55` 구간**에서는 Calibration·Holdout 모두 **OOS 거절률 100%**, `low_score_misses = 0`을 유지했습니다.
- Holdout에서 `HOLD-01`(치매·식욕저하)과 `HOLD-02`(탈수·수분)는 임계값 때문이 아니라, 한·영 사전에 없는 주제에서 국문 `kjg_elderly_nutrition_2019`의 수분·노인 영양 구절(`0.605`)이 영문 ESPEN보다 먼저 선택된 언어 편향으로 확인되었습니다.
- `bm25`는 `min_score=0.0`일 때 범위 외 질의에서도 1개 단어 우연 일치로 결과가 반환되므로(`OOS 0%`), BM25 운영 전환 시 `RAG_BM25_MIN_SCORE` 캘리브레이션이 필요합니다.

### C. 이전 v0.1 기록 보존 (Stage 2 LLM 생성·안전성 비교 — 가상 환자 5건)

| 코퍼스 | LLM 모델 | JSON/스키마 | 인용 정확도 | 안전 통과율 | 평균 지연 |
| --- | --- | ---: | ---: | ---: | ---: |
| 공식 PDF 3종 | `gpt-6-luna` | 100% / 100% | 100% | 100% (5/5) | 8.70초 |
| 공식 PDF 3종 | `gpt-5.6-luna` | 100% / 100% | 100% | 80% (4/5, `NS09` CKD 보류 위반) | 13.27초 |

---

## 3. 실행 및 재현 방법

```bash
cd backend
uv sync --locked
uv run ruff check && uv run ruff format --check
uv run pytest                                                    # 192 passed (네트워크 0건)
uv run python scripts/index_guidelines.py --audit-only           # 원문 매니페스트 감사
uv run python scripts/index_guidelines.py                        # 버전 분리 안전 색인 생성
uv run python scripts/eval_rag.py --models text-embedding-3-small text-embedding-3-large
```
