"""공식 RAG 원문(PDF·XML) 매니페스트 감사 및 Windows 안전 버전 분리 Chroma 색인 CLI.

사용 예시:
  cd backend
  uv run python scripts/index_guidelines.py --audit-only
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
from app.recommender.rag_sources import (  # noqa: E402
    DEFAULT_CHROMA_DIR,
    DEFAULT_MANIFEST_PATH,
    DEFAULT_SOURCES_DIR,
    audit_source_manifest,
)


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
    parser.add_argument(
        "--sources-dir",
        default=_read_env("RAG_SOURCES_DIR", str(DEFAULT_SOURCES_DIR)),
    )
    parser.add_argument(
        "--persist-dir",
        default=_read_env("RAG_CHROMA_DIR", str(DEFAULT_CHROMA_DIR)),
    )
    parser.add_argument(
        "--manifest-path",
        default=_read_env("RAG_MANIFEST_PATH", str(DEFAULT_MANIFEST_PATH)),
    )
    parser.add_argument(
        "--model",
        default=_read_env("RAG_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL),
        help="임베딩 모델 (기본: text-embedding-3-large)",
    )
    parser.add_argument("--chunk-size", type=int, default=900)
    parser.add_argument("--chunk-overlap", type=int, default=180)
    parser.add_argument("--rebuild", action="store_true", help="기존 색인을 무시하고 새 버전 구축")
    parser.add_argument(
        "--audit-only", action="store_true", help="색인 없이 매니페스트·원문 감사 결과만 출력"
    )
    args = parser.parse_args()

    if args.audit_only:
        audit = audit_source_manifest(args.sources_dir, manifest_path=args.manifest_path)
        print(json.dumps(audit, ensure_ascii=False, indent=2))
        return 0

    api_key = _read_env("OPENAI_API_KEY")
    base_url = _read_env("OPENAI_BASE_URL") or None
    backend = OpenAIEmbeddingBackend(api_key=api_key, model=args.model, base_url=base_url)
    report = index_guideline_sources(
        sources_dir=args.sources_dir,
        persist_dir=args.persist_dir,
        manifest_path=args.manifest_path,
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
