# 가이드라인 검색(RAG) 트랙 구현 및 실험 기록

**브랜치:** `feature/recommender-chroma-rag` (기준: `origin/develop` `741482e`, PR #10)  
**상태:** 계약 구현·테스트·앱 배선 완료 (팀 공용 계약 파일 무수정)

## 1. PR #10 골격 대비 추가한 사항

PR #10(`backend-skeleton-contracts`)의 공용 계약 파일(`backend/app/recommender/guideline_types.py`, `backend/tests/contracts/guideline.py`, `backend/app/config.py`, `backend/tests/conftest.py`)은 **단 한 줄도 수정하지 않고**, 아래 RAG 구현·색인 도구·계약 테스트를 추가했습니다.

| 추가 파일 / 변경 | 역할 |
| --- | --- |
| `backend/app/recommender/rag_sources.py` | `docs/research/rag-sources/README.md` 공식 4종(ESPEN, KJG 2019, GLIM 2025, 대한간호협회 욕창) 메타데이터·PDF/XML 추출·문단 경계 보존 청킹(900자/오버랩 180자)·SHA-256 캐시 체크 |
| `backend/app/recommender/query_expander.py` | 한국어 임상 질의 → 영문 핵심 용어 병기 쿼리 확장 (`expand_bilingual_query`) |
| `backend/app/recommender/chroma_search.py` | OpenAI 임베딩 + Chroma 코사인 벡터 `ChromaGuidelineSearch` (`GuidelineSearch` 구현, `asyncio.to_thread` 비동기 격리, `min_relevance_score=0.50`, 명시적 `GuidelineSearchError` 분리) |
| `backend/app/recommender/bm25_search.py` | 외부 API 키 없이 동작하는 순수 파이썬 BM25Okapi `Bm25GuidelineSearch` (`GuidelineSearch` 구현, 오프라인/장애 시 즉시 전환 대안) |
| `backend/scripts/index_guidelines.py` | `docs/research/rag-sources/` 원문을 `backend/var/chroma_guidelines/`에 영구 색인하는 독립 CLI |
| `backend/app/wiring.py` | `GUIDELINE_SEARCHES`에 `"chroma"`, `"bm25"` 2종 lazy-import 팩토리 등록 (기본값 `GUIDELINE_SEARCH=fake` 유지) |
| `backend/tests/test_chroma_search.py` | `GuidelineSearchContract` 상속 계약 테스트 + 임계값·캐시·오류·배선 테스트 (외부 API 모의) |
| `backend/tests/test_bm25_search.py` | `GuidelineSearchContract` 상속 계약 테스트 + 순위·교차언어 확장·배선 테스트 |
| `backend/pyproject.toml` · `uv.lock` | `chromadb`, `openai`, `pypdf` 3개 최소 의존성 추가 (LangChain 비의존으로 T5 의존성 충돌 방지) |
| `backend/var/.gitignore` | 로컬 Chroma 색인·런타임 파일 Git 제외 |

## 2. 왜 BM25 제안안 + Chroma 임베딩을 둘 다 구현했는가 (실측 근거)

팀 공식 원문 4종은 **영문 2종(ESPEN, GLIM) + 국문 2종(KJG 2019, 대한간호협회 욕창)** 혼합 코퍼스입니다.
실제 다운로드한 공식 PDF 3종(ESPEN 318청크 + KJG 22청크 + 욕창 737청크 = **총 1,077청크**)을 대상으로 OpenAI API 라이브 평가를 수행한 결과:

### Stage 1. 임베딩 검색·임계값·한영 쿼리 확장 실측 비교 (공식 PDF 1,077청크)

| 설정 | 임베딩 모델 | Hit@1 | Hit@3 | MRR | 교차언어(한→영) Hit@3 | 범위 외 거절률 | Score Gap |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 기본 (`min=0.25`, 원본 쿼리) | `text-embedding-3-small` | 50.0% | 62.5% | 0.562 | 33.3% | 33.3% | +0.181 |
| 기본 (`min=0.25`, 원본 쿼리) | `text-embedding-3-large` | 75.0% | 100.0% | 0.875 | 100.0% | 33.3% | +0.319 |
| 임계값 `0.50` 적용 | `text-embedding-3-small` | 50.0% | 62.5% | 0.562 | 33.3% | **100.0%** | +0.181 |
| 임계값 `0.50` 적용 | `text-embedding-3-large` | 75.0% | 100.0% | 0.875 | 100.0% | **100.0%** | +0.319 |
| **`min=0.50` + 한·영 쿼리 확장** | `text-embedding-3-small` | **75.0%** | **87.5%** | **0.812** | **66.7%** | **100.0%** | +0.219 |
| **`min=0.50` + 한·영 쿼리 확장** | **`text-embedding-3-large`** | **100.0%** | **100.0%** | **1.000** | **100.0%** | **100.0%** | **+0.362** |

### Stage 2. 동일 Top-3 근거 기반 LLM 생성·안전성 비교 (가상 환자 5개 시나리오)

| 코퍼스 | LLM 모델 | JSON/스키마 | 인용 정확도 | 안전 통과율 | 평균 지연 |
| --- | --- | ---: | ---: | ---: | ---: |
| 공식 PDF 3종 | **`gpt-6-luna`** | 100% / 100% | 100% | **100% (5/5)** | **8.70초** |
| 공식 PDF 3종 | `gpt-5.6-luna` | 100% / 100% | 100% | 80% (4/5, `NS09` CKD 보류 위반) | 13.27초 |

- 위 실측을 바탕으로 `ChromaGuidelineSearch` 기본값을 **`text-embedding-3-large` + `min_relevance_score=0.50` + 한·영 쿼리 확장**으로 설정했고, 오프라인·무키 전환용으로 `Bm25GuidelineSearch`도 함께 등록했습니다.

## 3. 로컬 색인 및 전환 실행 방법

```bash
cd backend
uv sync --locked

# 1) backend/.env에 OPENAI_API_KEY 설정 후 색인 생성 (docs/research/rag-sources/ 원문 기준)
uv run python scripts/index_guidelines.py

# 2) backend/.env에서 구현 선택
# GUIDELINE_SEARCH=chroma   # 메인 (OpenAI 임베딩 + Chroma)
# GUIDELINE_SEARCH=bm25     # 오프라인 무키 BM25 대안
# GUIDELINE_SEARCH=fake     # 기본값 (외부 API 불필요)
```

## 4. 에이전트 담당과 맞출 권장 파라미터

- 청크 크기: `900자` (오버랩 `180자`), 기본 `limit=5` (에이전트 프롬프트에서는 `limit=3` 호출 권장, 약 2,700자 내외).
