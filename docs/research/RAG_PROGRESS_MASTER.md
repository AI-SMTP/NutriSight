# NutriSight RAG — 마스터 진행 보고서와 단계별 개발 로드맵

> **기준일:** 2026-11-28 KST · **소유 트랙:** RAG / 실제 추천 Agent 연동  
> **형주 Fork:** HJ-GJ/NutriSight — **단일 관리 PR [#27](https://github.com/AI-SMTP/NutriSight/pull/27)** (`feature/rag-v0-5-integration-20261128@7fee767`, 기존 Draft PR `#18`은 2026-11-28 종료 완료), 최신 동기화 검증 브랜치 `sync/rag-v0-5-1-develop-t4-20261128`  
> **팀 기준:** AI-SMTP/NutriSight `develop@e2f89b0` (PR `#26` T4 API/`pyright` + PR `#28` NS03 시연 전환 복원·영양 알고리즘 가이드 반영)  
> **현재 단계:** PR `#18` 종료 → **PR `#27` 단일 관리 체계 전환** → **v0.5.1 최종 통합 검증(`develop@e2f89b0`, `pyright 0 errors`, `1,406 passed` + T4 플래키 5회 비교) 완료** → 사용자 승인 후 PR `#27` head fast-forward 반영 대기  
> **주의:** 이 문서는 개발 상태를 기록하며 의료적 유효성 또는 임상 사용 승인을 의미하지 않습니다.

## 1. 보고 체계와 정본

이 파일은 **현재 상태·결정·다음 단계**를 관리하는 단일 마스터 보고서입니다. 날짜별 평가 수치와 한계는 [2026-11-28 독립 성능평가](RAG_EVALUATION_2026-11-28.md)에, 실제 API 스모크 결과는 [2026-11-28 Large API 스모크 보고서](RAG_LARGE_API_SMOKE_TEST_2026-11-28.md)에, 검색 고도화 A/B/C 평가는 [2026-11-28 검색 고도화 보고서](RAG_RETRIEVAL_QUALITY_UPGRADE_2026-11-28.md)에, PR #18 리뷰 반영 검증은 [2026-11-28 PR #18 리뷰 검증 보고서](RAG_PR18_REVIEW_VALIDATION_2026-11-28.md)에, v0.5/v0.5.1 T4·PR #28 통합 검증은 [v0.5 통합 보고서](RAG_V0_5_INTEGRATION_2026-11-28.md) 및 [v0.5.1 팀 통합 보고서](RAG_V0_5_1_TEAM_INTEGRATION_2026-11-28.md)에, 기존 3종 실험의 상세 수치는 [v0.2 초기 구현 기록](rag-implementation-notes.md)에 보존합니다. Agent와의 함수 계약은 [T5 인계서](rag-agent-handoff.md)를 사용합니다.

**원칙:** 이미 실행한 실험 결과는 덮어쓰지 않습니다. 각 단계의 **기준 SHA / 원문 판본 / 질의셋 / 실행 주체 / 실측·모의 구분 / 남은 위험 / 결정**을 함께 기록합니다. 새 테스트마다 이 파일의 상태만 갱신하고, 재현 가능한 실험 상세는 별도 날짜별 보고서로 추가합니다.

## 2. 지금 실제로 구현된 범위

| 영역 | 구현·코드 상태 | 검증 수준 및 남은 제약 |
| --- | --- | --- |
| 가이드라인 검색 계약 | `GuidelineSearch.search(query, limit)`, `GuidelineHit` 등 공통 계약 유지 | 팀 공통 계약 파일 자체는 변경하지 않음 (`#21` T5 계약 합의 대기) |
| 로컬 BM25 | 한글 조사·복합명사, 임상 단위 처리, 한영 질의 확장, 근거 역조회 | `#20` 반영: 승인 원문 누락·0청크 시 fail-closed(`ConfigError`) 전환 완료 |
| Chroma + OpenAI 임베딩 | `text-embedding-3-small` / `text-embedding-3-large`, 코사인 검색 | **파일럿 주력 후보로 Large 제안**(팀 최종 확정 전). 스모크(`d99cd7e`: 3072차원, 1,142청크, 역조회 3/3) 및 v2.2 1,159청크 검증 완료 |
| Hybrid Search + ONNX Reranker | BM25+Dense RRF(`hybrid`), `BAAI/bge-reranker-v2-m3` ONNX INT8(`hybrid_rerank`) | 38문항 오프라인 A/B/C: Exact Evidence@3 Large 40.7% → Hybrid 48.1% → BGE 59.3% (CPU 8.06초로 Reranker 선택형) |
| 출처 관리 | 출처 매니페스트, 승인 정책, SHA-256, PDF/XML(GLIM 표 17청크 포함) 파서 | 등록 5종 중 승인 4종(`1,159`청크); GLIM CLNU PDF는 pending. `#23` 권고 번호 오귀속 검수 예정 |
| 안전 검색·Agent Preview | `retrieval_guard.py`, `app/agent_preview/` 읽기 전용 미리보기 | CKD/약물 9/9 차단, 정상 9/9 비과차단, Fake `R20`/`R23` 공식 표시 차단, `NS01`/`NS02` 격리 검증 |
| T5 실제 생성 Agent | **미구현·미연결** | 환자별 추천 생성, 근거 충실성 및 처방 보류 점수 미측정 (`#6`, `#21`) |
| 팀 전체 서비스 통합 | **Draft PR [#27](https://github.com/AI-SMTP/NutriSight/pull/27) 단일 관리** (PR `#18` 종료); `develop@e2f89b0`(T4 `#26` + PR `#28`) 무충돌 동기화 완료 | `sync/rag-v0-5-1-develop-t4-20261128`: `ruff` PASS, `pyright 0 errors`, `1,406 passed`(180.06s) + T4 플래키 5회 비교(develop 2/5 vs RAG 3/5). 승인 후 PR `#27` fast-forward 반영 예정 |

### 데이터 흐름 및 책임 경계

1. **다른 팀원/백엔드:** 사진 → VLM 섭취율 → NutritionEngine 계산·경고 → 환자별 DB.
2. **우리 RAG:** 비식별 일반 임상 질의 → 승인된 의료 가이드라인 검색 → `GuidelineHit`와 원문 근거.
3. **추후 T5 Agent:** 환자 정보와 영양 결과 + 검색 근거를 함께 보고 **영양중재 초안**을 만들며 부족한 근거는 명시적으로 보류.
4. **의료진 UI:** 초안 확인·수정·모의 처방 확정. 확정 권한은 LLM에 주지 않음.

가상 환자 NS01~NS10의 상태와 식사 기록은 **서비스 DB 데이터**이며, 가이드라인을 저장하는 Chroma/BM25 코퍼스에 섞지 않습니다. 원문 PDF/XML, 환자 식별자, API 키는 공개 저장소에 커밋하지 않습니다.

## 3. 단계별 작업 이력

| 단계 | 코드·보고 기준 | 완료한 작업 | 결과·게이트 | 상태 |
| --- | --- | --- | --- | --- |
| S0 · 계약/설계 | 팀 T1 | `GuidelineSearch` 계약·Fake·연동 지점 파악 | 계약 유지 | **완료** |
| S1 · 검색기 구현 | `a64fefe` | BM25, Chroma, PDF/XML 적재, 쿼리 확장, 평가 초안 | 기능·계약 테스트 추가 | **완료** |
| S2 · RAG v0.2 안정화 | `74f061e` | 안전 재색인, 원문 해시·승인, 근거 ID/역조회, 재현 평가 | 당시 3종·1,077청크·192 passed 기록 | **완료 — 이전 기준** |
| S3 · 문헌/검색어 확장 | `8b48aab`, `b7801cf` | 치매·탈수 사전 보완, GLIM JPEN XML 승인 | 매니페스트 4개 승인 아티팩트 | **완료** |
| S4 · 독립 벤치마킹 | Work, 2026-11-27~28 | 4종·1,142청크·질의 38개, BM25/Small/Large 비교, Windows 테스트 | Work 기록상 195 passed; 실제 Agent 평가는 미실행 | **검색 검증 완료** |
| S5 · 발표용 팀 인계 | `75f122c`, PR [#18](https://github.com/AI-SMTP/NutriSight/pull/18) | T2 병합·스모크(`d99cd7e`)·Draft PR #18 제출·`smalljiny` 리뷰 수령 | `75f122c` 623 passed, `develop` 병합 시험 662 passed; **Stage A(Issue #20) 수정 브랜치(`fix/rag-issue20-fail-closed`) 검증 완료**, 후속 이슈 #21–#25 조율 대기 | **진행 중 (Stage A 완료)** |
| S6 · T5 실제 추천 Agent | 앞으로 / Issue #6, #21 | 환자별 도구, 근거 인용·역조회, CKD 안전 보류, 카드/API 연결 | 실제 환자 모의 시나리오 통합 통과 | **미구현** |
| S7 · 발표 이후 고도화 | 향후 | GLIM 표 파싱, 하이브리드·Reranker, 더 큰 블라인드 평가 | 새 데이터로 개선/퇴보 비교 | **보류** |

**주의:** S0 ~ S7은 **RAG 트랙의 진행 단계**이고, SMTP 팀 전체 T1 ~ T7과 다른 번호 체계입니다. 팀 T5는 실제 Agent 연동에 해당합니다.

## 4. 독립 검증에서 확인한 사실

- **문헌:** ESPEN PDF 319, KJG PDF 22, GLIM JPEN XML 63, KHNA PDF 738 = **1,142청크**(Work 실험 기준). GLIM Clinical Nutrition PDF는 미승인 상태. 공식 문헌 **4종**이지 PDF 4개 확보라는 뜻은 아님.
- **안정성:** Work에서 Windows Python 3.12.16, 전체 `pytest 195 passed` 및 Ruff 통과를 보고. Chroma 활성 색인 보호·원문 역추적 테스트 포함. 이는 `b7801cf` 기반 보고이며 팀 T2를 병합한 통합 테스트 결과는 아님.
- **독립 질문 12개:** 정확한 근거 전부 찾기(양성 8) + 범위 밖 거절(4): BM25 **6/12**, Small **8/12**, Large **7/12**. Small과 Large는 필수 근거 전부 충족 **각 5/8**로 동률이며 범위 밖 거절은 **Small 3/4, Large 2/4**. 이 종합 지표는 문서 검색 정확도 단일 지표가 아님.
- **Large 제안 근거:** 독립 양성 정답 **문서 Hit@3 Large 87.5% vs Small 75.0%**; Calibration 문서 Hit@1 **100.0% vs 57.1%**, 기존 Holdout 문서 Hit@1 **85.7% vs 71.4%**. 기존 Holdout의 **필수 근거 전부 충족 Large 3/7 vs Small 1/7**. 다만 Calibration·기존 Holdout은 새 독립 블라인드 질문이 아니며, 근거 충족 수준도 아직 낮고 팀 최종 확정 전 단계임.
- **기존 Holdout 양성 7개:** 정답 문서 Top 3 적중은 BM25 7/7, Small 6/7, Large 7/7. 반면 **모든 필수 근거 구절 충족**은 각각 2/7, 1/7, 3/7. **문서 적중 ≠ 정확한 근거 적중**.
- **비용(추정):** 신규 색인과 38질의, 계약 확인 호출을 포함해 Small 약 **$0.00969**, Large 약 **$0.06295**. 실청구서 금액 아님.
- **검색 속도:** Holdout P95 BM25 **8.6ms**, Small **175.8ms**, Large **183.6ms**. API 호출 시간/네트워크 변동의 영향을 받는 단일 환경 기록.

평가 기준·분모·제약·원문 판본과 자세한 수치는 [독립 성능평가 보고서](RAG_EVALUATION_2026-11-28.md)를 정본으로 사용합니다.

## 5. 발견한 문제와 책임 구분

| ID | 중요도 | 확인된 문제 | 책임/대응 | 현재 상태 |
| --- | --- | --- | --- | --- |
| RAG-01 | P0 · 제품 안전 | **NS09-B**(CKD G3b + 목표 누락 + 미기록을 가정한 별도 시험 질문)에서 BM25·Small·Large 모두 기본 설정으로 부적합 근거를 반환 | 검색 적합성 재검증 + **Agent가 처방 수치 자동 생성 금지/보류** | 검색 실패 재현, Agent 미구현 (Stage B/D) |
| RAG-02 | P0 · 시연 인용 | 기존 **Fake** 카드 ESPEN `R20`, `R23`가 Work의 현재 BM25 색인에서 **0/2 역조회** | 시연용 카드는 실제 유효 `EvidenceRef`로 교체하거나 명확히 모의 표시 | 미해결 (Issue [#21](https://github.com/AI-SMTP/NutriSight/issues/21)) |
| RAG-03 | P1 · 원문 파서 | GLIM JPEN XML의 표(table-wrap) 내용이 색인되지 않아 **≤50%** 경계 근거를 누락 | XML 표 파싱·판본 차이 검수, 재색인 후 회귀시험 | 향후 (Stage B/E) |
| RAG-04 | P1 · 평가 | 독립 평가 12문항, 근거 라벨 단일 검토자, 기존 Holdout 일부 질문이 검색어 개선에 영향 | 블라인드 데이터 확대·2인 이상 라벨 검토 | 발표 한계에 명시 |
| RAG-05 | P0 · 통합 | T2 병합(`cdd3d20`→`75f122c`) 후 PR #18 제출, `smalljiny` 리뷰에서 **#20(BM25 원문 누락 시 0청크 기동)** 머지 전 수정 권고 및 후속 이슈 #21–#25 등록 | `#20` fail-closed 수정(`fix/rag-issue20-fail-closed`), `develop@9d56fbc` 로컬 병합 시험 | **#20 수정·검증 완료** / #21–#25 후속 |
| RAG-06 | P1 · 설정 | 기본 `GUIDELINE_SEARCH=fake`; Chroma 기본 모델은 Large 제안. `#22`에서 `Settings` 단일화·`var_dir` 통일 필요 | T4(#5) 병합 뒤 `Settings` 이관 및 Large 팀 확정 여부 조율 | 스모크 완료(`d99cd7e`) / #22·팀 확정 대기 |

**정확한 NS09 구분:** 팀 `data/seed/demo_seed.json`의 **실제 NS09**는 단백질 목표 **50g (team_set)**을 보유합니다. **NS09-B**는 안전 시험을 위해 목표 정보가 없다고 가정한 **별도 변형 사례**입니다. 이 둘을 동일 데이터라고 설명하면 안 됩니다.

**의료 안전 주의:** RAG가 부적절한 검색 결과를 반환했다는 사실과 실제 Agent가 위험한 처방을 생성했다는 주장은 다릅니다. 후자는 아직 검증되지 않았습니다.

## 6. 기술 결정 기록 (Decision log)

| ID | 결정 | 이유 | 재검토 시점 |
| --- | --- | --- | --- |
| D-01 | 11/30 발표용 **RAG v0.2 기능 기준선 동결** (병합 전 #20 fail-closed 수정만 반영) | 구현 확장보다 팀 통합·재현성 우선 | 발표 이후 |
| D-02 | **`text-embedding-3-large`를 파일럿 주력 임베딩 모델 후보로 제안**(팀 확정 전); Small은 비교군, BM25는 오프라인 대안 | 정답 문서 검색에서 Large 우세(독립 Hit@3 **87.5% vs 75.0%**, 기존 Holdout 필수 근거 **3/7 vs 1/7**). **독립 12문항 합산은 Small 8/12 > Large 7/12**, 양성 근거 충족은 5/8 동률; **임상 안전 우위를 뜻하지 않음** | 팀 확정 회의 및 신규 블라인드 평가 시 재검토 |
| D-03 | 검색 결과 존재만으로 의료적 충분성·처방 가능성을 인정하지 않음 | NS09-B 거절 실패 | 실제 Agent 구현 전 |
| D-04 | `GUIDELINE_SEARCH=fake` 기본값 유지; 실검색 사용 시 명시적 설정 | 미설치 키/색인으로 다른 팀 테스트 훼손 방지 | 팀 PR 리뷰 시 |
| D-05 | 환자 자료는 DB, 일반 의료 문헌은 RAG에 분리 저장 | 역할·개인정보·평가 오염 방지 | 데이터 계약 변경 시 |
| D-06 | 신규 Hybrid/Reranker 팀 반영은 발표 이후 또는 팀 일정 승인 후 | 실측 실패 원인과 시스템 안정성을 먼저 확인 | 11/30 이후 |

## 7. 다음 단계와 완료 기준

### S5-A · 문서 및 리뷰 준비
- [x] 최신 기준선과 과거 실험을 별도 보고서로 분리
- [x] GLIM JPEN XML 승인 vs Clinical Nutrition PDF 미승인 구분
- [x] 실제 NS09와 NS09-B 안전 시나리오 구분
- [x] PR [#18](https://github.com/AI-SMTP/NutriSight/pull/18) 리뷰 및 후속 이슈 #20–#25 반영 상태 마스터 보고서 최신화

### S5-B · 팀 develop 동기화 및 Stage A (Issue #20)
- [x] 최신 팀 `develop@9d56fbc` 확인 및 Draft PR #18 (`75f122c`) 통합 테스트(623 passed) · `develop` 병합 시험 확인
- [x] `uv sync --locked`, Ruff, 전체 Pytest 및 T2 시드·계약 회귀검증
- [x] **Issue #20**: `GUIDELINE_SEARCH=bm25` 원문 누락·0청크·해시/형식 오류 시 fail-closed(`ConfigError`) 수정 및 RED→GREEN 회귀 테스트 추가 (`fix/rag-issue20-fail-closed`)
- [x] Large 스모크 색인(`d99cd7e`, 3072차원, 1,142청크, 역조회 3/3) 확인
- [ ] Issue [#25](https://github.com/AI-SMTP/NutriSight/issues/25): T2 `fcntl` 앱 잠금의 Windows 지원 범위 팀 확정 (develop 기존 이슈)

### S5-C · Draft PR #18 리뷰 반영 및 팀 조율
- [x] 팀 `AI-SMTP/NutriSight:develop` ← `HJ-GJ/NutriSight:integration/rag-t2-20261128` Draft PR [#18](https://github.com/AI-SMTP/NutriSight/pull/18) 생성 및 `smalljiny` 리뷰 수령
- [ ] Stage A(`fix/rag-issue20-fail-closed`) 검토 승인 후 PR #18 반영 및 코멘트 회신
- [ ] Stage B(`#21`, `#23`) · Stage C(`#22`, `#24`, `#25`, T4 충돌) 팀 담당자 합의 후 순차 착수
- [ ] **팀의 승인 전에는 원본 develop 병합·배포하지 않음**

### S6 · T5 Agent 통합과 안전 확인 (팀 Issue #6, #21)
- [ ] 환자 ID 도구 경계, 영양 계산 결과 연결, `search_guidelines` / `resolve_evidence` 계약 합의 및 연결
- [ ] 카드 인용 `EvidenceRef`가 실제 색인에 존재하는지 확인
- [ ] 검색 무관/빈 결과/오류·CKD·삼킴 문제·미기록 시 안전 보류 테스트
- [ ] NS03/NS04/NS05/NS07/NS09의 실데이터 기반 **가상** 통합 시나리오
- [ ] LLM 생성 답변의 주장별 근거·인용·의료진 승인 분리 검증

### S7 · 후속 성능 개선 (발표 이후 / 팀 승인 후)
- [ ] GLIM 표 구조 파싱·경계 조건 회귀 테스트
- [ ] Hybrid와 Reranker는 별도 실험 브랜치에서 1개 변경씩 측정
- [ ] 정답 구절 라벨 확대·교차검수 후 블라인드 Holdout 성능 비교
- [ ] 성능 상승·하락, P95, 비용, 과적합 여부를 함께 보고

## 8. 현재 보고의 증거·한계

- **코드 확인:** RAG v0.2 평가 기준 `b7801cf`, Draft PR #18 head `75f122c`(T2 병합 + 스모크 보고 `d99cd7e`), Stage A 수정 브랜치 `fix/rag-issue20-fail-closed`. GitHub에는 원문 PDF/XML·로컬 Chroma 색인·Work 평가 PDF/ZIP 원본을 저장하지 않음.
- **평가 근거:** Work 작성 「NutriSight-RAG-독립검증.pdf」 10쪽, 「NutriSight-11월30일-한장요약.pdf」 및 「NutriSight-실험재현.zip」(2026-11-27~28 실행). 이 보고서들은 별도로 전달된 자료이며 본 GitHub 트리에 포함되지 않음.
- **실행 검증 범위:** PR #18(`75f122c`) 623 passed, `smalljiny` `develop` 병합 시험 662 passed, Stage A(`fix/rag-issue20-fail-closed`) 전체 pytest 및 `develop@9d56fbc` 로컬 병합 시험 수행([PR #18 리뷰 검증 보고서](RAG_PR18_REVIEW_VALIDATION_2026-11-28.md) 참조).
- **미검증:** 임상적 안전성, 실제 처방/진단 정확도, Windows 네이티브 Python 앱 기동(`#25`), 실제 T5 Agent 연동(`#6`, `#21`) 및 모바일 UI 승인 흐름.
- **작성 정책:** 실패를 성공으로 바꾸지 말고, 데이터셋/모델/코드가 바뀌면 새로운 실행 기록으로만 결과를 갱신.

## 9. 변경 이력

| 일자 | 보고서 상태 | 핵심 변경 |
| --- | --- | --- |
| 2026-11-27 | v0.1→v0.2 | RAG 구현·안전 재색인·근거 추적·기초 평가 |
| 2026-11-27~28 | Work 평가 | GLIM JPEN 반영 4종·38질문·195테스트·실패 사례 |
| 2026-11-28 | 마스터 보고서 도입 | 구현 / 발견 문제 / 다음 게이트 분리, 이전 수치 보존 |
| 2026-11-28 | 통합·모델 결정 최신화 | 별도 브랜치 T2 병합 `cdd3d20` 확인, Large 주력 후보 정리 |
| 2026-11-28 | PR #18 리뷰 반영 (Stage A) | Draft PR #18(`75f122c`)·`smalljiny` 리뷰·이슈 #20–#25 반영, Large "팀 확정 전 제안" 정정, Issue #20 fail-closed 수정·회귀 검증 완료 |
