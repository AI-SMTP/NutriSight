# NutriSight RAG v0.3 — 고도화(P0·P1·P2) 진행 보고서

> **목적:** 검증된 v0.2 기준선(`integration/rag-t2-20261128`, `75f122c`)을 변경하지 않고, 별도 브랜치에서 기존 벤치마크·통합 검증에서 확인된 P0(`NS09-B` 범위 밖/근거 부족), P1(GLIM XML 표 `≤50%` 누락), P2(`Fake` `R20`/`R23` vs 실제 `EvidenceRef` 인용 무결성) 3대 과제를 개선하고 재현·회귀 테스트로 검증한다.

---

## 1. v0.2 기준선과 새 브랜치 상태

| 구분 | 저장소 / 브랜치 | 커밋 SHA | 상태 |
| --- | --- | --- | --- |
| **보존된 v0.2 통합 기준선** | `HJ-GJ/NutriSight` · `integration/rag-t2-20261128` | `75f122c71e3a65208c0215e8f9aacd2b8a030d9d` (`75f122c`) | **무수정 보존** (SMTP 팀 리뷰 기준선) |
| **v0.3 작업 브랜치** | `HJ-GJ/NutriSight` · `feature/rag-v0-3-hardening-20261128` | `75f122c`에서 분기 | 본 보고서 및 P0–P2 개선 커밋 반영 |
| **팀 원본 (Upstream)** | `AI-SMTP/NutriSight` · `develop` | `67a1a35` | **미수정 · PR 미생성** |
| **실행 환경** | `Linux devbox 6.18.57 x86_64` · `CPython 3.12.16` | — | OpenAI 라이브 API 추가 호출 **0건** |

---

## 2. 기존 미해결 문제의 재현 결과 (수정 전 기준)

로컬 승인 원문 4종(`espen`, `kjg`, `glim_2025` XML, `khna`)과 `Bm25GuidelineSearch`로 v0.2(`75f122c`) 동작을 재현한 결과:

1. **P0 (`NS09-B` 재현):**
   * 질문: `"미기록 끼니가 있고 단백질 목표가 미등록인 노인 만성콩팥병 G3b 환자의 단백질 처방 수치"`
   * 재현 결과: v0.2 `Bm25GuidelineSearch`가 `khna_pressure_injury` `p.86#c3`(score `18.95`), `espen_geriatrics` `p.4#c1`(중증 질환 시 최대 2.0 g/kg 고단백 권고, score `16.38`) 등 일반 노인/욕창 고단백 문단을 반환함. (기존 Work 벤치마크의 Small `0.5223` · Large `0.5383` 실패와 동일 패턴)
2. **P1 (GLIM JPEN XML `≤50%` 누락 재현):**
   * `glim-5-year-update-2025-jpen.xml` 내 `<table-wrap>` 요소 5개(`jpen2756-tbl-0001`부터 `0005`까지)가 존재하며, **`jpen2756-tbl-0005` (Table 5)**의 `<td>`에 `"≤50% of ERs for >1 week, or any reduction for >2 weeks..."`가 위치함을 확인.
   * v0.2 파서는 `<sec>` 하위 `<p>`만 읽어 `glim_2025` 63청크만 생성했고, Table 1–5 전체가 색인에서 누락됨.
3. **P2 (Fake 인용 ID 불일치 재현):**
   * `FakeGuidelineSearch.FIXED_PASSAGES`의 `("espen_geriatrics", "R20")`, `("espen_geriatrics", "R23")`, `("kjg_elderly_nutrition_2019", "단백질 섭취")`를 실제 4종 승인 색인(`resolve_evidence`)으로 조회한 결과 **0/3 일치**(`False`).
   * 실제 ESPEN PDF에서는 `(R20, Grade B, ...)`가 `p.10#c2`, `(R23, Grade GPP, ...)`가 `p.10#c11`로 색인되어 있으며, 기존 `_VERIFIED_REC_PATTERNS` 기준 `R` 섹션 ID는 `R34` 1건뿐임.

---

## 3. 문제별 원인 분석

| 과제 | 근본 원인 | 계층별 책임 구분 |
| --- | --- | --- |
| **P0 (`NS09-B`)** | ① 검색 단계: 승인 문헌 4종에 없는 CKD 병기별 단백질 처방 수치·약물 용량 질의라도 `"노인"`, `"단백질"`, `"영양불량"` 등 고빈도 도메인 용어가 겹쳐 유사도/BM25 임계값을 넘음. ② 정책 단계: 검색 결과 유무와 무관하게 환자 기저질환·미기록 끼니를 보고 처방을 보류하는 최종 판단은 T5 에이전트 책임임. | **검색 계층:** 미지원 처방 수치/약물 프로토콜 요청·빈 결과·검색 오류를 `RetrievalStatus`로 구조화해 `hits=()` + `requires_clinical_review=True`로 안전 전달(임상 확정·자동 처방 금지). **T5 에이전트:** 환자 상태(CKD, 목표 미등록 등) 기반 최종 보류 강제. |
| **P1 (GLIM 표)** | `rag_sources.py`의 `_extract_xml_sections_from_bytes()`가 `<sec>` 직계 자식 `<p>`만 수집하고 JATS/PMC 표준 `<table-wrap>`(`<th>`/`<td>`/`<table-wrap-foot>`)를 무시함. | `rag_sources.py`에서 기존 `<sec>` 추출(`xml:s<n>#c<k>`)은 무수정 보존하고, `<table-wrap>`을 별도 네임스페이스 `xml:tbl:<table_id>#c<k>`로 추가해 하위 호환성과 표 커버리지를 동시에 확보. |
| **P2 (인용 무결성)** | `FakeGuidelineSearch` 및 `FakePatientData`의 모의 ID(`R20`, `R23`, `단백질 섭취`)와 실제 색인의 결정론적 위치 키(`p.10#c2`, `p.10#c11`)가 구분 없이 동일한 `EvidenceRef` 타입으로 유통됨. | 공용 계약(`guideline_types.py`, `ports.py`, `fake_*.py`)을 깨지 않고, 추천 항목 저장·표시 전 활성 색인 역조회(`resolve_evidence`)로 공식 검증 여부를 판별하는 `verify_evidence_refs()` 게이트 제공. |

---

## 4. 수정 파일 및 설계 이유

팀 공용 계약 파일(`guideline_types.py`, `tests/contracts/`, `config.py`, `conftest.py`, `fake_*.py`)과 T2 저장소 코드는 **단 한 줄도 수정하지 않았습니다.**

| 파일 | 변경 구분 | 설계 이유 및 핵심 내용 |
| --- | --- | --- |
| `backend/app/recommender/rag_sources.py` | 수정 (P1) | `EXTRACTOR_VERSION = "v2.2"` 갱신, `_extract_xml_tables_from_bytes()` 추가, `load_guideline_chunks()` XML 분기에서 기존 `xml:s*#c*` 63청크를 100% 보존한 채 `<table-wrap>`을 `xml:tbl:<table_id>#c<k>`로 추가 |
| `backend/app/recommender/retrieval_guard.py` | 신규 (P0·P2) | ① `safe_search_guidelines()` (`RetrievalStatus`: `FOUND`/`NO_EVIDENCE`/`UNSUPPORTED_SCOPE`/`SEARCH_ERROR`, `SafeRetrievalResult`) — 미지원 CKD 병기별 처방 수치·약물 용량 질의 차단, 오류·빈 결과 시 `requires_clinical_review=True` 반환, `NS09-A`/정상 질의 비간섭. ② `verify_evidence_refs()` (`CitationStatus`: `VERIFIED_OFFICIAL`/`UNVERIFIED_OR_MOCK`/`INDEX_UNAVAILABLE`) — `Fake`·미검증 ID의 공식 근거 표시 차단 |
| `backend/tests/test_rag_v03_hardening.py` | 신규 (P0–P2) | P0(`NS09-B`, `IND-NEG-01`/`02`, `NS09-A`, `NS07-A`, 빈 결과·오류), P1(합성 XML 표 추출·기존 ID 보존 + 로컬 GLIM XML 63섹션·Table 5 실검증), P2(`Fake` `R20`/`R23` 차단 vs 실제 ID 통과) 테스트 6건 |
| `docs/research/RAG_V0_3_HARDENING_PROGRESS.md` | 신규 | v0.3 고도화 진행 보고서 |

---

## 5. 테스트 · 회귀 결과

| 검증 항목 | 판정 | 실측 결과 |
| --- | --- | --- |
| `uv run ruff check` | **PASS** | `All checks passed!` |
| `uv run ruff format --check` | **PASS** | `74 files already formatted` |
| `uv run pytest` (전체) | **PASS** | **629 passed in 100.27s** (v0.2 통합 623건 + v0.3 신규 6건, 네트워크 0건) |
| 4종 원문 로컬 파싱 & BM25 대조 | **PASS** | 총 청크 `1,142 → 1,159` (`glim_2025`: 기존 63섹션 보존 + 신규 17표 청크) |
| OpenAI `text-embedding-3-large` v2.2 재색인 및 라이브 재평가 | **NOT RUN** | 지시서 원칙상 사전 승인 없는 추가 API 호출 금지 (`EXTRACTOR_VERSION=v2.2` 반영으로 재색인 시 자동 감지됨) |
| Windows 기본 Python 실행 | **NOT RUN** | Linux VM 환경 (T2 `app_lock.py`의 `fcntl` 제약 유지) |

---

## 6. 기존 성능과의 비교 (로컬 4종 BM25 기준)

| 항목 | v0.2 (`75f122c`, `v2.1`) | v0.3 (`v2.2` + `retrieval_guard`) | 변화 |
| --- | --- | --- | --- |
| 4종 총 청크 수 | 1,142 (`glim_2025`: 63) | **1,159** (`glim_2025`: 63 섹션 + **17 표**) | 기존 `xml:s*#c*` 63개 ID 100% 보존 + Table 1–5 추가 |
| `CAL-07` (GLIM `≤50%` 1주 초과) | `xml:s19#c2`만 검색 (Table 5 누락) | Top 3에 **`xml:tbl:jpen2756-tbl-0005#c1`** 포함 | 누락됐던 Table 5 `≤50%` 경계 근거 확보 |
| `NS09-B` (CKD G3b 단백질 처방 수치) | 일반 고단백 문단 반환 (거절 실패) | **`UNSUPPORTED_SCOPE`**, `hits=()`, `requires_clinical_review=True` | 부적합 고단백 근거 반환 차단 |
| `IND-NEG-01` / `02` / `03` (CKD 처방량·항생제·와파린) | 일반 문단 반환 | **`UNSUPPORTED_SCOPE`**, `hits=()` | Near-OOS 처방/약물 프로토콜 차단 |
| `NS09-A` (CKD 일반 주의사항) / `NS07-A` / `HOLD-07` | 정상 검색 | **`FOUND`** (정상 검색 유지) | 정상 질의 회귀 없음 |
| `Fake` 카드 `R20`/`R23`/`단백질 섭취` 공식 표시 | 구분 장치 없음 (`0/3` 역추적 실패) | `verify_evidence_refs`에서 **`0/3` `UNVERIFIED_OR_MOCK` 차단** | 모의·미검증 인용의 공식 근거 노출 방지 |

*(주의: 위 표는 로컬 BM25 및 규칙 가드 기준 비교이며, `text-embedding-3-large` 라이브 38문항 재평가는 아직 실행하지 않았습니다.)*

---

## 7. T5 팀 협의 필요 사항 (인터페이스 변경 분리)

1. **안전 검색 래퍼 채택 여부 (`safe_search_guidelines`):**
   * 기존 `GuidelineSearch.search(query, limit=3)`를 그대로 써도 되지만, T5 도구(`search_guidelines`)가 `safe_search_guidelines(app.state.guideline_search, query, limit=3)`를 호출하면 `UNSUPPORTED_SCOPE`·`NO_EVIDENCE`·`SEARCH_ERROR` 시 일관된 `abstain_reason`과 `requires_clinical_review=True`를 바로 받아 처리할 수 있음.
2. **추천 카드 저장/표시 전 인용 무결성 게이트 (`verify_evidence_refs`):**
   * `RecommendationCard` 저장·응답 시 `verify_evidence_refs`가 `can_display_as_official=False`이면 UI에 `"모의/미검증 인용"` 배지를 표시하거나 카드 생성을 보류할지 T4/T5/프론트엔드와 합의 필요.
3. **v2.2 Chroma 색인 재생성 시점:**
   * `EXTRACTOR_VERSION`이 `v2.1 → v2.2`로 바뀌었으므로, 팀 `develop`에 v0.3가 반영되면 `uv run python scripts/index_guidelines.py`를 1회 실행해 GLIM 표 17청크가 포함된 Large 색인(1,159청크, 추정 비용 약 USD 0.063)을 생성해야 함.

---

## 8. v0.3 완료 가능 여부와 남은 위험

* **현재 상태:** P0·P1·P2 코드 구현, 단위·통합 회귀 테스트 **629 passed**, 기존 v0.2 기준선(`integration/rag-t2-20261128`) 무수정 보존 완료.
* **남은 위험:**
  1. `detect_unsupported_scope()`는 보수적 규칙 기반이므로 새로운 표현의 Near-OOS 처방 수치 질의가 들어오면 통과할 수 있음 → **최종 임상 안전 보류는 반드시 T5 에이전트 프롬프트·환자 요약 검증과 이중으로 방어해야 함**.
  2. `text-embedding-3-large` 기준 `v2.2`(1,159청크) 라이브 재색인 및 `CAL-07`/`HOLD-07` 실측 점수는 아직 `NOT RUN` (형주 승인 시 1회 실행 가능).
  3. T2의 `app_lock.py` Windows `fcntl` 제약 및 T5 미구현 상태는 동일하게 잔존.
