"""설정 이름으로 다섯 계약의 구현을 만드는 등록부.

계약마다 `이름 → 생성 함수(Settings)` 등록부가 있고, `Settings`의 해당 값으로 구현을 고른다.
`PATIENT_DATA_PORTS`만 생성 함수가 `(Settings, AppRuntime)`을 받는다. `create_app`이 만든 런타임
(버스·태스크·쓰기 실행기·시계)을 포트와 추천 의존성이 함께 쓰게 하기 위해서다(스펙 3.8 등록 경로).

병행 트랙이 실제 구현을 추가하는 방법:

1. 이 모듈에 `def _build_xxx(settings: Settings) -> <계약>` 생성 함수를 만들고, 구현 모듈은
   함수 안에서 import한다. 그 이름이 선택됐을 때만 SDK·색인을 읽게 해, 다른 구현으로 띄우거나
   테스트를 수집할 때 무거운 의존성이 로드되거나 미설치로 import가 깨지지 않게 한다.

       def _build_vlm_estimator(settings: Settings) -> IntakeEstimator:
           from app.intake.vlm import VlmEstimator  # 선택됐을 때만 로드

           return VlmEstimator(...)

2. 아래 해당 등록부에 이름으로 추가한다. 예: `"vlm": _build_vlm_estimator`
3. 환경 변수(또는 `backend/.env`)로 고른다. 예: `INTAKE_ADAPTER=vlm`

기본 Fake는 외부 의존성이 없어 모듈 상단에서 import한다. 기본 환자 데이터 포트 `sqlite`도
같은 규칙으로 함수 안에서 import한다.

| 등록부 | 설정(환경 변수) | `app.state` 속성 |
| --- | --- | --- |
| `INTAKE_ESTIMATORS` | `INTAKE_ADAPTER` | `intake_estimator` |
| `NUTRITION_ENGINES` | `NUTRITION_ENGINE` | `nutrition_engine` |
| `GUIDELINE_SEARCHES` | `GUIDELINE_SEARCH` | `guideline_search` |
| `PATIENT_DATA_PORTS` | `PATIENT_DATA` | `patient_data` |
| `RECOMMENDATION_GENERATORS` | `RECOMMENDER` | `recommendation_generator` |

테스트는 `monkeypatch.setitem(wiring.<등록부>, "alt", factory)`로 등록해 자동 복원한다.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from dotenv import dotenv_values

from app.config import BACKEND_ENV_FILE, ConfigError, Settings, storage_paths
from app.intake.fake import FakeEstimator
from app.intake.types import IntakeEstimator
from app.nutrition.fake import FakeNutritionEngine
from app.nutrition.types import NutritionEngine
from app.recommender.fake_generator import FakeRecommendationGenerator
from app.recommender.fake_guideline import FakeGuidelineSearch
from app.recommender.generator_types import RecommendationGenerator
from app.recommender.guideline_types import GuidelineSearch
from app.services.fake_patient_data import FakePatientData
from app.services.ports import PatientDataPort
from app.services.runtime import AppRuntime


def _read_rag_env(name: str, default: str = "") -> str:
    """환경 변수 우선, 없으면 `backend/.env`에서 RAG 전용 설정값을 읽는다."""
    env_val = os.getenv(name)
    if env_val is not None and env_val.strip():
        return env_val.strip()
    if BACKEND_ENV_FILE.exists():
        val = dotenv_values(BACKEND_ENV_FILE).get(name)
        if val and val.strip():
            return val.strip()
    return default


def _build_chroma_search(_settings: Settings) -> GuidelineSearch:
    """`GUIDELINE_SEARCH=chroma` 선택 시에만 Chroma·OpenAI SDK와 색인을 지연 로드한다."""
    from app.recommender.chroma_search import (
        DEFAULT_EMBEDDING_MODEL,
        DEFAULT_MIN_RELEVANCE_SCORE,
        ChromaGuidelineSearch,
        OpenAIEmbeddingBackend,
    )
    from app.recommender.rag_sources import DEFAULT_CHROMA_DIR

    model = _read_rag_env("RAG_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)
    persist_dir = _read_rag_env("RAG_CHROMA_DIR", str(DEFAULT_CHROMA_DIR))
    min_score = float(_read_rag_env("RAG_MIN_RELEVANCE_SCORE", str(DEFAULT_MIN_RELEVANCE_SCORE)))
    api_key = _read_rag_env("OPENAI_API_KEY")
    base_url = _read_rag_env("OPENAI_BASE_URL") or None
    backend = OpenAIEmbeddingBackend(api_key=api_key, model=model, base_url=base_url)
    return ChromaGuidelineSearch(
        persist_dir=persist_dir,
        embedding_backend=backend,
        embedding_model=model,
        min_relevance_score=min_score,
    )


def _build_bm25_search(_settings: Settings) -> GuidelineSearch:
    """`GUIDELINE_SEARCH=bm25` 선택 시에만 승인 원문에서 로컬 BM25 색인을 구성한다."""
    from app.recommender.bm25_search import Bm25GuidelineSearch
    from app.recommender.rag_sources import DEFAULT_MANIFEST_PATH, DEFAULT_SOURCES_DIR

    sources_dir = _read_rag_env("RAG_SOURCES_DIR", str(DEFAULT_SOURCES_DIR))
    manifest_path = _read_rag_env("RAG_MANIFEST_PATH", str(DEFAULT_MANIFEST_PATH))
    try:
        min_score = float(_read_rag_env("RAG_BM25_MIN_SCORE", "0.0"))
        return Bm25GuidelineSearch.from_sources_dir(
            sources_dir,
            manifest_path=manifest_path,
            min_score=min_score,
        )
    except (ValueError, OSError) as exc:
        raise ConfigError(f"GUIDELINE_SEARCH=bm25 초기화 실패: {exc}") from exc


def _build_hybrid_search(settings: Settings) -> GuidelineSearch:
    """`GUIDELINE_SEARCH=hybrid` 선택 시에만 BM25 + Chroma RRF 하이브리드 검색기를 지연 로드한다."""
    from app.recommender.hybrid_search import (
        DEFAULT_CANDIDATE_K,
        DEFAULT_RRF_K,
        HybridGuidelineSearch,
    )

    candidate_k = int(_read_rag_env("RAG_HYBRID_CANDIDATE_K", str(DEFAULT_CANDIDATE_K)))
    rrf_k = int(_read_rag_env("RAG_HYBRID_RRF_K", str(DEFAULT_RRF_K)))
    return HybridGuidelineSearch(
        bm25_search=_build_bm25_search(settings),
        dense_search=_build_chroma_search(settings),
        candidate_k=candidate_k,
        rrf_k=rrf_k,
    )


def _build_hybrid_rerank_search(settings: Settings) -> GuidelineSearch:
    """`GUIDELINE_SEARCH=hybrid_rerank` 선택 시 하이브리드 + 로컬 ONNX BGE Reranker를 구성한다."""
    from app.recommender.reranker import (
        DEFAULT_BGE_ONNX_DIR,
        DEFAULT_MAX_TOKENS,
        DEFAULT_RERANK_CANDIDATES,
        OnnxBgeReranker,
        RerankedGuidelineSearch,
    )

    model_dir = _read_rag_env("RAG_RERANK_MODEL_DIR", str(DEFAULT_BGE_ONNX_DIR))
    max_tokens = int(_read_rag_env("RAG_RERANK_MAX_TOKENS", str(DEFAULT_MAX_TOKENS)))
    top_n = int(_read_rag_env("RAG_RERANK_TOP_N", str(DEFAULT_RERANK_CANDIDATES)))
    reranker = OnnxBgeReranker(model_dir=model_dir, max_tokens=max_tokens)
    return RerankedGuidelineSearch(
        base_search=_build_hybrid_search(settings),
        reranker=reranker,
        rerank_top_n=top_n,
    )


INTAKE_ESTIMATORS: dict[str, Callable[[Settings], IntakeEstimator]] = {
    "fake": lambda settings: FakeEstimator(delay_s=settings.fake_intake_delay_s),
}
NUTRITION_ENGINES: dict[str, Callable[[Settings], NutritionEngine]] = {
    "fake": lambda settings: FakeNutritionEngine(),
}
GUIDELINE_SEARCHES: dict[str, Callable[[Settings], GuidelineSearch]] = {
    "fake": lambda settings: FakeGuidelineSearch(),
    "chroma": _build_chroma_search,
    "bm25": _build_bm25_search,
    "hybrid": _build_hybrid_search,
    "hybrid_rerank": _build_hybrid_rerank_search,
}


def _build_sqlite_patient_data(settings: Settings, runtime: AppRuntime) -> PatientDataPort:
    """업무 DB(`app.db`)를 쓰는 포트. 런타임의 쓰기 실행기·시계를 함께 쓴다.

    판단 알고리즘은 `NUTRITION_ENGINE` 설정으로 따로 만든다. 포트와 `app.state.nutrition_engine`은
    인스턴스를 공유하지 않으므로 판단 알고리즘 구현은 상태가 없어야 한다.
    """
    from app.services.sqlite_patient_data import SqlitePatientData

    return SqlitePatientData(
        storage_paths(settings).app_db, runtime, build_nutrition_engine(settings)
    )


PATIENT_DATA_PORTS: dict[str, Callable[[Settings, AppRuntime], PatientDataPort]] = {
    "sqlite": _build_sqlite_patient_data,
    "fake": lambda settings, runtime: FakePatientData(),
}
RECOMMENDATION_GENERATORS: dict[str, Callable[[Settings], RecommendationGenerator]] = {
    "fake": lambda settings: FakeRecommendationGenerator(),
}


@dataclass(frozen=True)
class Components:
    """앱 시작 시 만든 다섯 계약의 구현."""

    intake_estimator: IntakeEstimator
    nutrition_engine: NutritionEngine
    guideline_search: GuidelineSearch
    patient_data: PatientDataPort
    recommendation_generator: RecommendationGenerator


def _lookup[F](registry: Mapping[str, F], setting_name: str, settings: Settings) -> F:
    """등록부에서 설정값 이름의 생성 함수를 찾는다. 없으면 `ConfigError`."""
    name = getattr(settings, setting_name)
    factory = registry.get(name)
    if factory is None:
        registered = ", ".join(sorted(registry))
        raise ConfigError(
            f"{setting_name}={name!r}은 등록되지 않은 구현 이름이다 (등록된 이름: {registered})"
        )
    return factory


def _build[T](
    registry: Mapping[str, Callable[[Settings], T]], setting_name: str, settings: Settings
) -> T:
    """등록부에서 설정값 이름의 생성 함수를 찾아 구현을 만든다."""
    return _lookup(registry, setting_name, settings)(settings)


def build_nutrition_engine(settings: Settings) -> NutritionEngine:
    """`NUTRITION_ENGINE` 설정의 판단 알고리즘을 만든다. 시드 적재도 같은 규칙을 쓴다."""
    return _build(NUTRITION_ENGINES, "nutrition_engine", settings)


def build_components(settings: Settings, runtime: AppRuntime) -> Components:
    """설정값으로 다섯 구현을 만든다. 등록되지 않은 이름이면 `ConfigError`를 던진다.

    환자 데이터 포트에는 `runtime`을 넘긴다. 구현을 만들 때 DB 파일을 열지 않는다.
    """
    port_factory = _lookup(PATIENT_DATA_PORTS, "patient_data", settings)
    return Components(
        intake_estimator=_build(INTAKE_ESTIMATORS, "intake_adapter", settings),
        nutrition_engine=build_nutrition_engine(settings),
        guideline_search=_build(GUIDELINE_SEARCHES, "guideline_search", settings),
        patient_data=port_factory(settings, runtime),
        recommendation_generator=_build(RECOMMENDATION_GENERATORS, "recommender", settings),
    )
