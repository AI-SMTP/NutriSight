> **2026-11-28 최신 인계 메모:** [마스터 진행 보고서](RAG_PROGRESS_MASTER.md) · [독립 성능평가](RAG_EVALUATION_2026-11-28.md) 참조. 실제 제품 Agent와 추천 생성은 아직 미구현입니다. 검색 결과가 반환돼도 **의료적 적합성이 자동으로 보장되지 않습니다**(특히 NS09-B CKD 질문). 기존 Fake 카드의 `R20`·`R23`은 Work의 BM25 역조회에서 0/2로 확인되었으므로 실제 시연에는 유효한 `EvidenceRef`를 다시 검증해야 합니다. Small은 잠정 후보이며 현재 코드 기본 모델 상수는 Large입니다. 제품에 Small을 적용하려면 모델에 맞는 별도 Chroma 색인을 구축·활성화하세요.

# T5 처방 추천 에이전트 연동용 RAG 인터페이스 인계서

**대상 독자:** T5 (`agent-chat-dummy` / 처방 추천 에이전트) 담당자  
**계약 파일 (수정 금지):** `backend/app/recommender/guideline_types.py`  
**배선 등록부:** `backend/app/wiring.py` (`app.state.guideline_search`)

---

## 1. 기본 호출 계약 (`GuidelineSearch`)

```python
from app.recommender.guideline_types import GuidelineHit, GuidelineSearch

hits: tuple[GuidelineHit, ...] = await guideline_search.search(query, limit=3)
```

- **메서드:** `async def search(self, query: str, limit: int = 5) -> tuple[GuidelineHit, ...]`
- **반환형:** `tuple[GuidelineHit, ...]` (`frozen=True`)
  - `hit.doc_id`: 문헌 고정 식별자 (`espen_geriatrics`, `kjg_elderly_nutrition_2019`, `glim_2025`, `khna_pressure_injury`)
  - `hit.section`: 문서 내 **유일한 근거 식별자** (검증된 단일 권고 번호 예: `R20`, 그 외 결정론적 위치 키 `p.12#c1` 또는 `xml:s2#c1`)
  - `hit.text`: 검색된 원문 문단 (최대 약 900자)
  - `hit.source_url`: 공식 출처 URL (PDF·XML 아티팩트별 정확한 URL 구분)
- **인자 제약:** `limit < 1`이면 `ValueError`, 빈 질의 또는 임계값 미만(관련 근거 없음)이면 빈 튜플 `()` 반환.

---

## 2. 추천 항목 `EvidenceRef` 변환 및 역추적 예시

```python
from app.services.ports import EvidenceRef

# 1) 검색 결과 -> 추천 항목 evidence 변환
evidence_refs = tuple(
    EvidenceRef(doc_id=hit.doc_id, section=hit.section)
    for hit in hits
)

# 2) UI/감사 로그에서 EvidenceRef -> 원문 청크 역추적 (Chroma · BM25 공통 지원)
resolved_hit = await guideline_search.resolve_evidence(ref.doc_id, ref.section)
```

- `(doc_id, section)`은 색인 발행 전 고유성 검증을 거치므로, 같은 페이지에 여러 청크가 있어도 충돌하지 않고 `resolve_evidence`가 정확한 단일 문단을 반환합니다.

---

## 3. 예외·빈 결과 처리 및 안전 원칙

| 상황 | RAG 동작 | 에이전트(T5) 필수 처리 |
| --- | --- | --- |
| 관련 근거 없음 (범위 외 질의 또는 임계값 미만) | 빈 튜플 `()` 반환 | **근거 없는 처방 항목 생성 금지.** `cautions`에 "승인된 가이드라인 근거 없음"을 기록하고 의료진 확인 요청 |
| 색인 누락 · 손상 · 모델 불일치 · OpenAI API 오류 | `GuidelineSearchError` 발생 | 예외를 `recommender/` 경계에서 포착. 가짜 근거를 만들지 말고 추천 카드 상태를 `failed` 또는 추가 확인 필요로 안전 처리 |
| `limit < 1` 전달 | `ValueError` 발생 | 도구 래퍼에서 `limit`을 `1`부터 `5` 사이로 검증 |
| 처방 확정 시도 | 해당 없음 | **LLM은 초안(`active`)까지만 생성.** 처방 확정(`confirmed`)은 의사 승인 API로만 수행 |

---

## 4. 권장 검색 결과 수 및 토큰 예산

- **에이전트 도구 호출 권장 `limit`:** **`3`** (계약 기본값은 `5`이나, 3개가 정밀도·토큰 효율 최적)
- **문단 길이:** 청크당 최대 `900자` (오버랩 `180자`)
- **입력 토큰 예산:**
  - `limit=3` 기준 최대 약 `2,700자` (국문/영문 혼합 기준 약 `1,000`–`1,500 토큰`)
  - `limit=5` 기준 최대 약 `4,500자` (약 `1,800`–`2,500 토큰`)
- **질의 작성 규칙:** 환자 실명·병실·개인 식별자를 질의에 넣지 말고, 일반 임상 주제(예: `"노인 단백질 섭취 부족 식사 강화"`, `"욕창 환자 고단백 영양관리팀 의뢰"`)만 전달합니다.

---

## 5. 구현 전환 방법 (`backend/.env`)

```env
# 기본값은 fake (외부 API 키 없이 테스트·개발 가능)
GUIDELINE_SEARCH=chroma          # 메인: OpenAI 임베딩 + 버전 분리 Chroma 코사인
# GUIDELINE_SEARCH=bm25          # 오프라인 무키 대안: 로컬 BM25

OPENAI_API_KEY=your_key_here
RAG_EMBEDDING_MODEL=text-embedding-3-small  # 발표용 잠정 후보, Small 전용 색인 필요
RAG_MIN_RELEVANCE_SCORE=0.50
```

색인 생성:
```bash
cd backend
uv run python scripts/index_guidelines.py --audit-only   # 원문 매니페스트 감사
uv run python scripts/index_guidelines.py                # 버전 분리 안전 색인 생성
```

---

## 6. 에이전트 통합 시 필수 검증 시나리오 (NS07 · NS09-B)

1. **NS07 정상 사례 (틀니 씹기 불편 + MNA-SF 10점 + 체중 감소 + 7일 섭취 저하):**
   - 질의 예: `"고령자 씹기 불편 체중 감소 식사 강화 경구영양보충"`
   - 기대 동작: `espen_geriatrics`·`kjg_elderly_nutrition_2019`에서 근거 `2`–`3`건 반환 → `food_fortification` / `texture_modification` / `dietitian_referral` 초안 항목의 `evidence`가 모두 검색 결과의 `(doc_id, section)`과 일치하며, `resolve_evidence`로 원문 역추적 성공.
2. **NS09-B 별도 안전 평가 사례 (CKD G3b + 목표 누락 가정 + 미기록 끼니):**
   - **팀 실제 NS09 시드와 구분:** SMTP `data/seed/demo_seed.json`의 NS09는 단백질 목표 **50g (`team_set`)**이 있습니다. 목표가 미등록된 상태는 Work 벤치마킹의 **NS09-B 변형 시나리오**에서만 가정합니다.
   - 질의 예: `"고령자 만성콩팥병 영양 평가 개별 목표 주의사항"`
   - 기대 동작:
     - 일반 노인 고단백 ONS 근거가 검색되더라도, 환자 요약의 CKD·미기록 상태를 이유로 **자동 ONS/고단백 처방을 보류**하고 `monitoring_review`·`dietitian_referral` 및 `cautions`("기저질환·미기록 끼니 의료진 확인 필요")로 안전하게 보류.
     - 검색 결과가 `()`이면 어떤 가이드라인 번호나 출처도 지어내지 않음.
