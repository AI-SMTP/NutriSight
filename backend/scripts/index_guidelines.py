"""공식 RAG 원문(PDF·XML)을 Chroma 코사인 색인으로 구축하는 독립 CLI 스크립트.

사용 예시:
  cd backend
  uv run python scripts/index_guidelines.py
  uv run python scripts/index_guidelines.py --model text-embedding-3-small --rebuild
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import dotenv_values

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import BACKEND_ENV_FILE  # noqa: E402
from app.recommender.chroma_search import (  # noqa: E402
    DEFAULT_EMBEDDING_MODEL,
    OpenAIEmbeddingBackend,
    index_guideline_sources,
)
from app.recommender.rag_sources import DEFAULT_CHROMA_DIR, DEFAULT_SOURCES_DIR  # noqa: E402


def _read_env(name: str, default: str = "") -> str:
    env_val = os.getenv(name)
    if env_val is not None and env_val.strip():
        return env_val.strip()
    if BACKEND_ENV_FILE.exists():
        file_vals = dotenv_values(BACKEND_ENV_FILE)
        val = file_vals.get(name)
        if val and val.strip():
            return val.strip()
    return default


def main() -> int:
    parser = argparse.ArgumentParser(description="NutriSight 공식 가이드라인 Chroma 색인 생성기")
    parser.add_argument("--sources-dir", default=str(DEFAULT_SOURCES_DIR))
    parser.add_argument("--persist-dir", default=str(DEFAULT_CHROMA_DIR))
    parser.add_argument(
        "--model",
        default=_read_env("RAG_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL),
        help="임베딩 모델 (기본: text-embedding-3-large)",
    )
    parser.add_argument("--chunk-size", type=int, default=900)
    parser.add_argument("--chunk-overlap", type=int, default=180)
    parser.add_argument("--rebuild", action="store_true", help="기존 색인을 무시하고 전체 재색인")
    args = parser.parse_args()

    api_key = _read_env("OPENAI_API_KEY")
    base_url = _read_env("OPENAI_BASE_URL") or None
    backend = OpenAIEmbeddingBackend(api_key=api_key, model=args.model, base_url=base_url)
    report = index_guideline_sources(
        sources_dir=args.sources_dir,
        persist_dir=args.persist_dir,
        embedding_model=args.model,
        embedding_backend=backend,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
        force_rebuild=args.rebuild,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
