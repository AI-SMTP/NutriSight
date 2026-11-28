# NutriSight — RAG Retrieval Quality Upgrade 결과 보고서 (2026-11-28)

## 1. 기준선 및 작업 범위

| 항목 | 내용 |
| --- | --- |
| 대상 저장소 | `HJ-GJ/NutriSight` (개인 포크) |
| 작업 브랜치 | `feature/rag-retrieval-quality-20261128` |
| 기준 커밋 (v0.4 Large v2.2 기준선) | `e44aa6a85a9c04fe3aa1b0795d150ff79425ec03` (`feature/rag-v0-4-agent-preview-20261128`) |
| 보존된 기존 브랜치 / PR | `integration/rag-t2-20261128` (`75f122c`, Draft PR `AI-SMTP/NutriSight#18`), `feature/rag-v0-3-hardening-20261128` (`5e8d7cf`), `AI-SMTP/NutriSight:develop` (`9d56fbc`) — 일체 미수정 |
| 공용 계약 변경 여부 | 미변경 (`guideline_types.py`, `tests/contracts/`, `config.py`, `conftest.py`, `GUIDELINE_SEARCH` 기본값 `"fake"` 유지) |
| 승인 원문 코퍼스 | 4/4종 SHA-256 검증 완료 (`1,159`청크: ESPEN 319, KJG 22, GLIM 2025 80[본문 63 + 표 17], KHNA 738) |
| 실행 환경 | Linux Ubuntu 24.04, 2 vCPU (Intel Xeon @ 2.30 GHz), 7.8 GiB RAM, NVIDIA GPU 없음 |
| 유료 API / GPU 사용 | **0건 (`$0.00`)** — 모든 신규 개발·테스트·A/B/C 평가는 무비용 로컬/캐시 조건으로 수행 |

---

## 2. 구현 변경 사항

1. **Hybrid Search (`backend/app/recommender/hybrid_search.py`)**
   - `HybridGuidelineSearch`: `GuidelineSearch` 계약 준수, 1단계 후보 생성(BM25 Top `candidate_k=10` + Dense Top `candidate_k=10`) → `(doc_id, section)` 중복 제거 → RRF 결합(`score = sum(weight / (k + rank))`, 기본 `k=60`, 동점 시 `(doc_id, section)` 결정적 정렬) → 상위 `limit` 반환.
   - **Dense-empty OOS 가드 (`require_dense_hit_when_ok=True`)**: Dense 검색이 정상 동작(`HybridStatus.OK`)했으나 임계값(`0.50`) 통과 결과가 0건인 경우(범위 밖 질의), BM25의 약한 어휘 잡음이 OOS 차단을 우회하지 않도록 빈 결과를 반환.
   - **Dense 장애 분리 (`DEGRADED_BM25_FALLBACK`)**: Dense 예외 발생 시 로그 경고와 명시적 상태(`HybridStatus.DEGRADED_BM25_FALLBACK`, `dense_error`)를 기록해 정상 `hybrid` 지표와 저하 실행이 섞이지 않게 차단.
   - `resolve_evidence(doc_id, section, version_id=...)` 위임으로 인용 역추적 계약 보존.

2. **Reranker 인터페이스 및 로컬 CPU 어댑터 (`backend/app/recommender/reranker.py`)**
   - `HitReranker` Protocol, `RerankStatus` (`OK`, `RERANK_UNAVAILABLE`), `RerankResult` 정의.
   - `OnnxBgeReranker`: 백엔드 기존 의존성(`onnxruntime==1.32.0`, `tokenizers==0.23.3`, `numpy==2.5.5`)만으로 동작하는 `BAAI/bge-reranker-v2-m3` ONNX INT8 CPU 어댑터 (`pyproject.toml` / `uv.lock` 무변경, PyTorch 불필요).
   - `RerankedGuidelineSearch`: 1단계 후보를 재정렬하되 `(doc_id, section, text, source_url)` 불변성을 교차 검증해 가짜 인용 삽입을 원천 차단하고, 모델 누락·추론 오류 시 `RERANK_UNAVAILABLE`와 함께 1단계 검증 순위로 안전하게 fallback.
   - 최대 토큰(`max_tokens=512`) 초과 절단 발생 시 `truncated_count` 집계 및 경고 로그 기록.

3. **지연 등록 (`backend/app/wiring.py`)**
   - `GUIDELINE_SEARCHES`에 `"hybrid"`, `"hybrid_rerank"` 지연 팩토리 등록 (`GUIDELINE_SEARCH` 기본값 `"fake"` 불변).

4. **평가 스크립트 및 회귀 테스트**
   - `backend/scripts/eval_retrieval_upgrade.py`: 38문항 A/B/C 비교, `Document Hit@3` / `Candidate Evidence Recall@10` / `Exact Evidence@3` 분리 집계, GLIM Table 5 라벨 정합성 매핑 보정 전/후 병기, 문항별 추적 로그 출력.
   - `backend/tests/test_hybrid_rerank.py`: 43건 신규 회귀 테스트(`GuidelineSearchContract` 하위 클래스 2종, RRF 수학/동점/중복제거, Dense 장애·OOS 가드, Reranker `RERANK_UNAVAILABLE`·가짜 인용 차단, CKD 위험 9/9 차단, 정상 9/9 비과차단, Fake `R20`/`R23` 차단, `NS01`/`NS02` 격리 및 카드 미변경, GLIM Table 5 매핑).

---

## 3. Reranker 후보 검토 결과

| 후보 모델 | 라이선스 | 실행 가능성 (본 VM: 2 vCPU, GPU 없음) | 실측 결과 / 비고 |
| --- | --- | --- | --- |
| **1순위: `BAAI/bge-reranker-v2-m3`** (ONNX INT8: `Saegus/bge-reranker-v2-m3-onnx-int8`) | Apache 2.0 | **PASS (로컬 CPU 실행 검증 완료)** — `model_int8.onnx` 544 MB + `tokenizer.json` 17 MB (`backend/var/models/`, gitignored), 기존 `onnxruntime` 사용 | 38문항 전체 실행 완료 (`errors=0`, `rerank_unavailable=0`). 품질 대폭 향상(`11/27 → 16/27`), 단 2 vCPU 기준 지연 높음(Top-6 평균 `8.06초`, Top-10 단일 질의 `17.6초`) |
| **2순위(선택): `nvidia/llama-nemotron-rerank-1b-v2`** | OpenMDW-1.1 + Llama 3.2 Community | **NOT RUN** — 공식 참조 환경이 NVIDIA GPU(H100/A100/L40s/L4/A10G) TensorRT / vLLM>=0.14 / NIM(`build.nvidia.com`) 또는 PyTorch `transformers>=4.47`(`trust_remote_code=True`, `cuda:0`) | 본 VM에 NVIDIA GPU 및 PyTorch가 없으며, NVIDIA 유료 API / GPU 대여 미승인 상태이므로 실행하지 않음 (필수 인계 조건 아님) |

---

## 4. 38문항 A / B / C / D 성능 비교

> **측정 조건 명시**: 유료 OpenAI API 무호출 게이트를 준수하기 위해, Dense 후보는 **기존 v2.2 Large 평가 캐시(`text-embedding-3-large-v22.json`, `threshold=0.50`, Top-5 저장분)**를 사용했고, BM25(Top-10)와 BGE ONNX Reranker(RRF Top-6 → Top-3)는 로컬 실시간 추론으로 실행했습니다. 진정한 `Live Dense Top-10 + BM25 Top-10` 측정은 Section 8의 비용 승인 게이트 이후 선택 실행할 수 있습니다.

### 4.1 전체 집계 (38문항: 정상 27 + OOS 11)

| 지표 | A. Large v2.2 (기준선, 캐시 Top-5) | B. Hybrid (BM25 Top-10 + Large + RRF) | C. Hybrid + BGE ONNX (Top-6) | D. Hybrid + NVIDIA Reranker |
| --- | --- | --- | --- | --- |
| **Document Hit@1** | 23/27 (85.2%) | 23/27 (85.2%) | 22/27 (81.5%) | NOT RUN |
| **Document Hit@3** | 25/27 (92.6%) | 24/27 (88.9%) | **25/27 (92.6%)** | NOT RUN |
| **Document Recall@3** | 0.8519 | 0.8148 | **0.8519** | NOT RUN |
| **Document MRR** | 0.8827 | 0.8704 | 0.8519 | NOT RUN |
| **Candidate Evidence Recall@10 (그룹)** | 57.5% (Dense Top-5) | **75.0%** (+17.5%p) | **75.0%** (+17.5%p) | NOT RUN |
| **Candidate Evidence@10 (전 그룹 충족)** | 12/27 (44.4%) | **18/27 (66.7%)** (+6문항) | **18/27 (66.7%)** (+6문항) | NOT RUN |
| **Exact Evidence@3 (보정 전 원라벨)** | 10/27 (37.0%) | 13/27 (48.1%) (+3) | **15/27 (55.6%)** (+5) | NOT RUN |
| **Exact Evidence@3 (GLIM Table 5 보정 후)** | 11/27 (40.7%) | **13/27 (48.1%)** (+2, +7.4%p) | **16/27 (59.3%)** (+5, +18.5%p) | NOT RUN |
| **Top-3 필수 근거 그룹 커버율** | 21/40 (52.5%) | 24/40 (60.0%) | **26/40 (65.0%)** | NOT RUN |
| **Raw OOS 차단율 (검색기 단독)** | 8/11 (72.7%) | 8/11 (72.7%) | 8/11 (72.7%) | NOT RUN |
| **Safe OOS 차단율 (`safe_search_guidelines`)** | **11/11 (100.0%)** | **11/11 (100.0%)** | **11/11 (100.0%)** | NOT RUN |
| **정상 질의 과차단 수** | **0/27** | **0/27** | **0/27** | NOT RUN |
| **지연 (mean / median / P95, ms)** | 213.2 / 198.2 / 290.3 | **223.5 / 208.0 / 295.4** (+10.3ms) | 8,057.7 / 8,712.2 / 13,854.4 | NOT RUN |
| **오류 / Rerank Fallback / 절단 수** | 0 / - / - | 0 / - / - | 0 / 0 / 16쌍(max 512) | NOT RUN |
| **추가 API / GPU 비용** | `$0` (기존 색인) | **`$0`** | **`$0`** (로컬 CPU) | 유료/GPU 필요 |

### 4.2 Split별 Exact Evidence@3 (GLIM Table 5 라벨 보정 후)

| Split (정상 문항 수) | A. Large v2.2 | B. Hybrid RRF | C. Hybrid + BGE ONNX |
| --- | --- | --- | --- |
| Calibration (7) | 2/7 (28.6%) *(보정 전 1/7)* | 2/7 (28.6%) | **4/7 (57.1%)** |
| Holdout (7) | 3/7 (42.9%) | 2/7 (28.6%) | **3/7 (42.9%)** |
| Independent (8) | 5/8 (62.5%) | **7/8 (87.5%)** | **7/8 (87.5%)** |
| Patient (5) | 1/5 (20.0%) | **2/5 (40.0%)** | **2/5 (40.0%)** |
| **합계 (27)** | **11/27 (40.7%)** | **13/27 (48.1%)** | **16/27 (59.3%)** |

> **GLIM Table 5 라벨 정합성 보정 효과**: `CAL-07` 정답 라벨 `("glim_2025", "table:jpen2756-tbl-0005")`에 대해 v2.2 XML 표 청크 `xml:tbl:jpen2756-tbl-0005#c*`를 별도 매핑 규칙으로 연결한 결과, 기존 데이터셋이나 v2.2 보고서를 덮어쓰지 않고도 A(`10→11/27`)와 C(`15→16/27`)의 실제 표 근거 적중이 정확히 반영되었습니다. (`≤50%` 기호 보존 확인 완료.)

---

## 5. 대표 실패 케이스 5건 원인 분석

| 문항 ID | 질의 요약 | 1단계 후보 (BM25 / Dense) | RRF / BGE Reranker 결과 | 원인 분류 |
| --- | --- | --- | --- | --- |
| `CAL-01` | ONS 400 kcal·단백질 30 g·최소 1개월 지속 평가 (3개 그룹) | `p.12#c1`, `p.11#c6`는 확보했으나 1그룹(`p.10#c1`/`c2`)이 BM25 Top-10·Dense Top-5 모두 미진입 | RRF/BGE 모두 2/3 그룹만 충족 (`p.12#c1`, `p.11#c6` 상위) | **1단계 후보 누락** (다중 근거 분산 + Dense Top-5 한계) |
| `CAL-06` | 영문 욕창 예방·고단백 ONS·다학제 팀 (3개 그룹) | BM25·Dense 모두 `khna p.17#c1`, `p.83#c1` 확보 (`A=1, B=1`) | BGE가 영문 `espen p.15#c12`, `p.16#c5`를 한국어 `khna p.17#c1`보다 높게 채점 (`C=0`) | **Reranker 언어 일치 편향** (영문 질의 → 영문 청크 선호) |
| `HOLD-01` | 치매·인지저하 고령 환자 식욕 저하·영양 중재 | `espen p.7#c5..p.8#c5`가 BM25 Top-10·Dense Top-5 모두 미진입 | 한국어 `kjg p.3#c4`, `p.4#c5`가 상위 점유 | **1단계 후보 누락** (한→영 치매/인지저하 어휘·의미 갭) |
| `HOLD-04` | 욕창예방·상처 치유 영양사정 및 에너지·단백질·수분 모니터링 | 2그룹(`khna p.83#c2`)이 RRF 7–10위 구간에 존재 (`B10=1`) | `rerank_top_n=6` 컷오프로 BGE 미전달 + `p.86#c3` 512토큰 절단 발생 | **Reranker 컷오프(Top-6) 및 입력 절단** |
| `NS07-A` | 고령자 씹기 불편·체중 감소·식사 강화·ONS | 한국어 `kjg`/`khna`가 상위 점유해 영문 `espen p.10#c7/#c8` 미진입 | RRF/BGE 모두 `kjg` 청크 위주 반환 | **1단계 후보 누락** (`씹기 불편`↔`chewing problems` 교차언어 갭) |

---

## 6. 안전성 및 회귀 검증 결과

| 검증 항목 | 명령 / 기준 | 결과 |
| --- | --- | --- |
| 의존성 잠금 확인 | `cd backend && uv sync --locked` | **PASS** (113 packages, `uv.lock` 무변경) |
| 린트 / 포맷 | `uv run ruff check` / `uv run ruff format --check` | **PASS** (0 errors, 84 files formatted) |
| 전체 자동화 테스트 | `uv run pytest -q` | **PASS** (**698 passed**, 0 failed, 0 skipped — 기존 655건 보존 + 신규 43건) |
| 승인 원문 무결성 | `uv run python scripts/index_guidelines.py --audit-only` | **PASS** (4/4종 approved_ready, SHA-256 일치) |
| 독립 Agent 미리보기 | `uv run python scripts/agent_preview_smoke.py --patient NS01` | **PASS** (읽기 전용 SSE 출력, 카드 미변경) |
| CKD·약물 위험 질의 차단 | `test_hybrid_rerank_blocks_all_9_unsafe_ckd_drug_queries` | **PASS (9/9 차단, 검색기 호출 전 차단)** |
| 정상 질의 과차단 방지 | `test_hybrid_rerank_does_not_overblock_9_normal_queries` | **PASS (9/9 정상 통과, 과차단 0건)** |
| 가짜 인용 차단 | `verify_evidence_refs` (`R20`, `R23`) + `_FabricatingReranker` | **PASS (공식 표시 차단 및 1단계 안전 fallback)** |
| 환자 격리 | `NS01` / `NS02` `FakeAgentPreview.stream` | **PASS (환자 데이터 비혼선, 추천 카드 불변)** |

---

## 7. 최종 채택 권고 및 T5 인계 사항

### 최종 채택 판단
1. **CPU-only 실시간 서비스(T5 SSE 기본 연결) — `B. Hybrid (BM25 + Large v2.2 + RRF + Dense-empty OOS 가드)` 채택 권장**
   - `Exact Evidence@3`: `11/27 (40.7%) → 13/27 (48.1%)` (`+7.4%p`), `Candidate Evidence@10`: `12/27 (44.4%) → 18/27 (66.7%)` (`+22.2%p`).
   - 추가 지연은 평균 `+10.3ms`(`213.2ms → 223.5ms`), 추가 API 비용은 `$0`, OOS 안전성 회귀 0건(`Safe OOS 11/11`).
2. **GPU 또는 전용 Rerank 서버(TEI/ONNX 고속 CPU) 확보 시 — `C. Hybrid + BGE ONNX Reranker` 활성화 권장**
   - `Exact Evidence@3`: `11/27 (40.7%) → 16/27 (59.3%)` (`+18.5%p`, Document Hit@3 `92.6%` 유지)로 품질 향상 폭이 가장 큼.
   - 단, 현재 2 vCPU CPU-only 환경에서는 평균 `8.06초` / P95 `13.85초` 지연이 발생해 실시간 T5 SSE 기본값으로는 부적합하므로 `GUIDELINE_SEARCH=hybrid_rerank` 옵션으로 제공하고, 모델 미배치·장애 시 `RERANK_UNAVAILABLE`로 `B` 순위에 자동 fallback하도록 구현 완료.
3. **안전 롤백 경로**: 문제 발생 시 환경 변수 `GUIDELINE_SEARCH=chroma`(기존 Large v2.2 단독) 또는 `GUIDELINE_SEARCH=fake`로 즉시 복귀 가능.

### T5 인계 설정 요약
- 기존 `GuidelineSearch` 계약(`search(query, limit)`) 및 `safe_search_guidelines` / `verify_evidence_refs` 호출 방식 변경 없음.
- 권장 환경 변수:
  - CPU-only 운영: `GUIDELINE_SEARCH=hybrid`, `RAG_CHROMA_DIR=<v2.2 Large 색인 경로>`, `RAG_EMBEDDING_MODEL=text-embedding-3-large`
  - Reranker 활성 시(GPU/고속 CPU): `GUIDELINE_SEARCH=hybrid_rerank`, `RAG_RERANK_MODEL_DIR=<BGE ONNX 디렉터리>`, `RAG_RERANK_TOP_N=10` (또는 지연 절충 시 `6`)
  - 기본 테스트/개발: `GUIDELINE_SEARCH=fake` 유지.

---

## 8. 유료 API 승인 게이트 (선택 후속: Live Dense Top-10 정밀 재측정)

현재 A/B/C 평가는 기존 v2.2 Large 캐시(Top-5)를 사용해 비용 `$0`으로 완료했습니다. 만약 **진정한 `Live Dense Top-10 + BM25 Top-10` RRF 및 BGE Reranker Top-10** 실측을 원하실 경우 아래 조건으로 별도 승인이 필요합니다:

- **사용 모델**: `text-embedding-3-large` (기존 v2.2 색인 `backend/var/eval_chroma_final/text-embedding-3-large` 1,159청크 그대로 재사용 — **재색인 불필요**)
- **예상 호출 수**: 질의 임베딩 **38회** (단건 질의 38문항)
- **예상 토큰 수**: 약 **1,972 토큰**
- **예상 비용**: 약 **`$0.00026` USD** (`$0.13 / 1M tokens` 기준)
- **제안 비용 상한**: `$0.05` USD
- **실패 복구 방안**: 읽기 전용 질의 호출이므로 기존 v2.2 색인 및 `active_pointer.json`은 일체 변경되지 않으며, API 실패 시 즉시 중단 후 임시 키를 삭제합니다.
