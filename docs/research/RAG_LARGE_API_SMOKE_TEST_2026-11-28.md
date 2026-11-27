# NutriSight RAG v0.2 — OpenAI API 실검색 검증 보고서

> **목적:** SMTP T2 × RAG v0.2 통합 브랜치에서 실제 `OPENAI_API_KEY`와 `text-embedding-3-large` 모델을 사용해 공식 4종 문헌 색인 연결, 단일 질문 실검색 및 `EvidenceRef` 역추적 동작을 확인한다.  
> **범위 제한:** 본 보고서는 **단일 질문 API 실연결 스모크 테스트**이며, 전체 검색 성능 재평가(38문항)나 실제 LLM 처방 안전성·임상 유효성 검증은 포함하지 않는다.

---

## 1. 검증 개요

| 항목 | 내용 |
| --- | --- |
| **저장소 / 브랜치** | `HJ-GJ/NutriSight` · `integration/rag-t2-20261128` |
| **검증 기준 커밋** | `d99cd7e5689b487b9bfeef4fb24e2df078296bd5` (`d99cd7e`, 통합 기준 `cdd3d20`) |
| **팀 원본 기준** | `AI-SMTP/NutriSight` · `develop@67a1a35` |
| **실행 일시** | 2026-11-27 18:24–18:25 UTC (2026-11-28 03:24–03:25 KST) |
| **OS / Python** | `Linux devbox 6.18.57 x86_64 GNU/Linux` · `CPython 3.12.16` |
| **의존성 상태** | `uv sync --locked` (113개 패키지 확인 완료) |

---

## 2. 실행 환경 및 원문·색인 상태

### 2-1. 모델 및 설정
* **검색기:** `ChromaGuidelineSearch` (`GUIDELINE_SEARCH=chroma`)
* **임베딩 모델:** `text-embedding-3-large` (`vector_dim=3072`)
* **관련성 임계값:** `min_relevance_score=0.50` (`limit=3`)
* **API 키 사용:** 1회성 `OPENAI_API_KEY`를 메모리 환경변수로만 전달해 사용 (`.env` 미생성, 콘솔/보고서/Git 미기록, 실행 직후 로컬 임시 파일 삭제 완료)

### 2-2. 공식 문헌 4종 확보 및 SHA-256 감사 (`scripts/index_guidelines.py --audit-only`)
* `manifest_sha256`: `92dbd8a3835c2620d2ae0cbb5d7542289772e685580c033d3fb30a9d3ea3457e`
* `readme_checked`: `true` (`readme_missing_from_manifest: []`)
* `missing_or_unapproved_doc_ids`: `[]` (**4/4종 전부 승인·해시 검증 완료**)

| `doc_id` | 아티팩트 | 형식 | 청크 수 | SHA-256 (앞 12자리) | 감사 상태 |
| --- | --- | --- | ---: | --- | --- |
| `espen_geriatrics` | `espen-practical-guideline-geriatrics.pdf` | PDF | 319 | `b5456f29359f...` | `approved_ready` |
| `kjg_elderly_nutrition_2019` | `kjg-2019-73-4-196-elderly-nutrition.pdf` | PDF | 22 | `5b3c2a0d43d4...` | `approved_ready` |
| `glim_2025` | `glim-5-year-update-2025-jpen.xml` | XML | 63 | `d80cc184b117...` | `approved_ready` |
| `khna_pressure_injury` | `khna-pressure-injury-guideline.pdf` | PDF | 738 | `ad6a5b511a92...` | `approved_ready` |
| *(미승인 대기)* | `glim-5-year-update-2025-clnu.pdf` | PDF | 0 | — | `missing_file` (`pending` 유지) |

### 2-3. 활성 Chroma 색인 상태
* 검증 시작 시 클라우드 환경(`backend/var/chroma_guidelines`)에 기존 색인이 없어, 사용자 사전 승인에 따라 4종 원문 기반 신규 Large 색인을 1회 구축한 뒤 스모크 테스트를 수행함.
* **활성 버전 ID:** `v20261127T182442Z_f2e0ab8e` (`status: verified`)
* **컬렉션명:** `nutrisight_guideline_chunks`
* **임베딩 모델 / 차원:** `text-embedding-3-large` / `3072`
* **총 적재 청크 수:** **1,142청크** (`chunk_size=900`, `chunk_overlap=180`, `extractor_version=v2.1`, `section_id_version=v2.0`)
* **적재 완료 문헌 ID:** `["espen_geriatrics", "glim_2025", "khna_pressure_injury", "kjg_elderly_nutrition_2019"]`

---

## 3. API 실검색 결과

* **시험 질문:**
  > 고령자 영양실조 위험 환자의 경구영양보충 및 식사 강화에 관한 가이드라인 권고는 무엇인가?
* **앱 배선 기동 확인:** `create_app(Settings(_env_file=None, guideline_search="chroma", ...))` → `ChromaGuidelineSearch` 정상 연결 (**PASS**)
* **실검색 API 호출:** 성공 (`query_errors=0`)
* **질의 API 사용량 및 응답시간:**
  * 질의 임베딩 호출 횟수: **1회**
  * 입력 토큰(`prompt_tokens` / `total_tokens`): **69 tokens**
  * 질의 추정 비용: 약 **USD 0.000009** (`$0.13 / 1M tokens` 단가 기준)
  * 검색 응답시간(`search_with_scores`): **1,217.9 ms** *(콜드 Chroma 컬렉션 오픈 + OpenAI API 왕복 포함)*
  * *(참고: 직전 신규 4종 색인 구축 단계는 `1,142`청크 기준 정상 완료되었으나 래퍼 출력 키 오류로 색인 단계 토큰 트래커 로그가 출력되지 않아 `NOT RECORDED`로 구분함; 동일 코퍼스 기준 참고치는 약 481,805 tokens / 약 USD 0.0626 수준)*

### 검색 결과 Top 3 (`limit=3`, 임계값 `0.50`)

| 순위 | `doc_id` | `section` | 코사인 유사도 | 원문 발췌 요약 |
| ---: | --- | --- | ---: | --- |
| 1 | `espen_geriatrics` | `p.10#c11` | **0.7460** | `3.2.3.4.1. Indication — 26) Older persons with malnutrition or at risk of malnutrition with chronic conditions shall be offered ONS when dietary counseling and food fortification are not sufficient to increase dietary intake and reach nutritional goals. (R23, Grade GPP, strong consensus 100%)` |
| 2 | `espen_geriatrics` | `p.10#c12` | **0.7059** | R23 Commentary: ONS와 일반 식사 강화·영양 상담 전략의 체중·에너지·단백질·삶의 질 개선 비교 |
| 3 | `espen_geriatrics` | `p.11#c7` | **0.6825** | Fig. 5 (Oral nutritional supplements): 합병증·재입원 위험 감소, 악력·섭취량 증가 요약 |

---

## 4. 근거 역추적 결과 (`resolve_evidence(doc_id, section)`)

| 순위 | `doc_id` | `section` | `source_url` | 역추적(`resolved == hit`) |
| ---: | --- | --- | --- | :---: |
| 1 | `espen_geriatrics` | `p.10#c11` | `https://www.espen.org/files/ESPEN-Guidelines/ESPEN%5Fpractical%5Fguideline%5FClinical%5Fnutrition%5Fand%5Fhydration%5Fin%5Fgeriatrics.pdf` | **일치 (`True`)** |
| 2 | `espen_geriatrics` | `p.10#c12` | `https://www.espen.org/files/ESPEN-Guidelines/ESPEN%5Fpractical%5Fguideline%5FClinical%5Fnutrition%5Fand%5Fhydration%5Fin%5Fgeriatrics.pdf` | **일치 (`True`)** |
| 3 | `espen_geriatrics` | `p.11#c7` | `https://www.espen.org/files/ESPEN-Guidelines/ESPEN%5Fpractical%5Fguideline%5FClinical%5Fnutrition%5Fand%5Fhydration%5Fin%5Fgeriatrics.pdf` | **일치 (`True`)** |

---

## 5. 종합 판정

| 점검 항목 | 판정 | 근거 |
| --- | --- | --- |
| **API 연결** | **PASS** | `OpenAIEmbeddingBackend` 실제 API 호출 `1회` 성공 (`error_count=0`, `69` tokens) |
| **모델 일치** | **PASS** | 색인 메타(`text-embedding-3-large`, `3072`차원)와 질의 모델 일치 |
| **색인 정상 작동** | **PASS** | 4종 1,142청크 `v20261127T182442Z_f2e0ab8e` 검증 및 로드 성공 |
| **검색 결과 반환** | **PASS** | `limit=3` 요청에 유효 `GuidelineHit` 3건 반환 (`score >= 0.6825`) |
| **EvidenceRef 무결성** | **PASS** | Top 3 전부 `(doc_id, section, text, source_url)` 역추적 3/3 정확 일치 |
| **검색 결과의 질문 적합성** | **PASS** | Rank 1에 ESPEN R23(경구영양보충·식사 강화 적응증 원문) 직접 적중 |
| *(기존 통합 회귀 참고)* | **PASS** | `cdd3d20` 기준 Ruff PASS · Pytest **623 passed** (T2 590 + RAG 33) · 시드/리셋 PASS |
| *(범위 외 / 미실행)* | **NOT RUN** | 전체 38문항 재벤치마크, Windows 기본 Python 실행(`fcntl` 제약), T5 LLM 처방 안전성 검증 |

---

## 6. 발견된 문제

1. **초기 색인 실행 시 검증 래퍼 키 참조 오류 (`KeyError: 'chunk_count'`)**
   * **내용:** 1회용 실행 래퍼 스크립트에서 `index_guideline_sources()` 반환 딕셔너리의 `"indexed_chunks"` 대신 `"chunk_count"`를 참조해 색인 완료 직후 출력이 중단됨.
   * **실제 영향:** 색인 구축·무결성 검증·`active_pointer.json` 원자 교체는 정상 완료되었으며 제품 코드에는 영향 없음. 다만 해당 1차 실행의 색인 단계 토큰 트래커 수치 출력만 누락되어 `NOT RECORDED`로 표기함.
2. **기존 통합 보고서상 미해결 제약 유지**
   * **Windows 기본 Python 비호환:** T2의 `backend/app/storage/app_lock.py`가 `fcntl`을 사용해 Windows 기본 Python에서는 import 제약이 남음(Linux/WSL2에서는 `PASS`).
   * **단일 질의 범위 한계:** 본 스모크는 정상 양성 질의 1건에 대한 연결 검증이며, 이전 독립 벤치마크에서 확인된 Near-OOS(`NS09-B`) 거절 실패는 T5 에이전트 단의 보류 로직으로 해결해야 함.

---

## 7. Draft PR 제출 판단

* **제출 가능 여부:** **제출 가능 (`PASS` on Linux)**
  * T2 저장소 통합 회귀 **623 passed** (`cdd3d20`), 공식 4/4종 원문 SHA-256 일치, `text-embedding-3-large` 실검색 및 `EvidenceRef` 역추적 3/3 일치까지 확인 완료.
* **남은 위험 및 팀 확인 필요 사항:**
  1. `backend/app/storage/app_lock.py`의 Windows 기본 Python(`fcntl`) 호환 여부를 T2 작성자/팀과 공유·확인 필요
  2. T5(`#6`) 구현 시 `NS09` CKD 등 임상 보류 규칙을 에이전트 단에서 강제하고, `Fake` 카드 `R20`/`R23` 대신 실제 검색 결과의 `EvidenceRef`를 사용하도록 합의 필요 (이슈 `#14`)
  3. 본 보고서 커밋(`integration/rag-t2-20261128`) 반영 후 **사용자 최종 승인 시** `AI-SMTP/NutriSight:develop` 대상 **Draft PR** 생성 진행
