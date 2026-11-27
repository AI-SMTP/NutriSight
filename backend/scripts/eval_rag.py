"""NutriSight RAG 재현 가능 독립 평가 스크립트 (BM25 vs Small vs Large, Calibration vs Holdout).

일반 pytest에서는 절대 호출하지 않으며, 실제 OpenAI API를 사용한 정량 평가를 기록한다.
- 사용 문서·전체 64자리 SHA-256·누락 문서(예: GLIM 미확보 시 3/4 명시) 기록
- Calibration / Independent Holdout 데이터셋 분리 평가 및 임계값 민감도(0.40–0.55)
- Hit@1/3, Recall@3, MRR, OOS 거절률, 평균·중앙값·P95 지연, 오류 수, 토큰·추정 비용 기록
- limit=1/3/5 및 동일 질의 재현성 검증 포함

사용 예시:
  cd backend
  uv run python scripts/eval_rag.py --models text-embedding-3-small text-embedding-3-large
  uv run python scripts/eval_rag.py --bm25-only
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dotenv import dotenv_values

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import BACKEND_ENV_FILE  # noqa: E402
from app.recommender.bm25_search import Bm25GuidelineSearch  # noqa: E402
from app.recommender.chroma_search import (  # noqa: E402
    ChromaGuidelineSearch,
    EmbeddingUsageTracker,
    OpenAIEmbeddingBackend,
    index_guideline_sources,
)
from app.recommender.rag_sources import (  # noqa: E402
    DEFAULT_MANIFEST_PATH,
    DEFAULT_SOURCES_DIR,
    audit_source_manifest,
)

DEFAULT_DATASET_PATH = Path(__file__).resolve().parent / "eval_datasets.json"
DEFAULT_REPORT_DIR = BACKEND_DIR / "var" / "eval_reports"
DEFAULT_EVAL_CHROMA_ROOT = BACKEND_DIR / "var" / "eval_chroma"

# 1M 토큰당 추정 단가 (USD, 참고치 — OpenAI 표준 Embeddings 요금 기준)
_PRICE_PER_1M_TOKENS: dict[str, float] = {
    "text-embedding-3-small": 0.02,
    "text-embedding-3-large": 0.13,
}


def _read_env(name: str, default: str = "") -> str:
    env_val = os.getenv(name)
    if env_val is not None and env_val.strip():
        return env_val.strip()
    if BACKEND_ENV_FILE.exists():
        val = dotenv_values(BACKEND_ENV_FILE).get(name)
        if val and val.strip():
            return val.strip()
    root_env = BACKEND_DIR.parent / ".env"
    if root_env.exists():
        val = dotenv_values(root_env).get(name)
        if val and val.strip():
            return val.strip()
    return default


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(round((pct / 100.0) * (len(ordered) - 1)))))
    return round(ordered[idx], 1)


def _compute_metrics_for_threshold(
    raw_records: list[dict[str, Any]],
    *,
    loaded_doc_ids: set[str],
    threshold: float,
) -> dict[str, Any]:
    pos_hit1 = 0
    pos_hit3 = 0
    pos_recall3_sum = 0.0
    pos_mrr_sum = 0.0
    pos_count = 0
    missing_doc_queries = 0
    oos_rejected = 0
    oos_count = 0
    low_score_misses = 0
    latencies: list[float] = []

    for rec in raw_records:
        latencies.append(rec["latency_ms"])
        filtered = [h for h in rec["raw_hits"] if h["score"] >= threshold]
        expected: list[str] = rec["expected_doc_ids"]

        if rec["is_out_of_scope"]:
            oos_count += 1
            if not filtered:
                oos_rejected += 1
            continue

        # 정답 문서 중 하나라도 로드된 문서가 없으면 '정답 누락 질문'으로 분리 집계
        available_expected = [d for d in expected if d in loaded_doc_ids]
        if not available_expected:
            missing_doc_queries += 1
            continue

        pos_count += 1
        top_docs = [h["doc_id"] for h in filtered[:3]]
        hit1 = bool(top_docs) and top_docs[0] in available_expected
        rr = 0.0
        for rank, did in enumerate(top_docs, start=1):
            if did in available_expected:
                rr = 1.0 / rank
                break
        hit3 = rr > 0.0
        # Recall@3: 기대 문서 집합 중 Top-3에서 찾은 비율
        found_expected = len(set(top_docs) & set(available_expected))
        recall3 = found_expected / len(set(available_expected))

        if hit1:
            pos_hit1 += 1
        if hit3:
            pos_hit3 += 1
        else:
            raw_top_docs = [h["doc_id"] for h in rec["raw_hits"][:3]]
            if any(d in available_expected for d in raw_top_docs):
                low_score_misses += 1
        pos_recall3_sum += recall3
        pos_mrr_sum += rr

    return {
        "threshold": threshold,
        "positive_evaluated": pos_count,
        "missing_doc_skipped": missing_doc_queries,
        "oos_evaluated": oos_count,
        "hit_at_1": round(pos_hit1 / max(pos_count, 1), 4),
        "hit_at_3": round(pos_hit3 / max(pos_count, 1), 4),
        "recall_at_3": round(pos_recall3_sum / max(pos_count, 1), 4),
        "mrr": round(pos_mrr_sum / max(pos_count, 1), 4),
        "oos_rejection_rate": round(oos_rejected / max(oos_count, 1), 4),
        "low_score_misses": low_score_misses,
        "latency_mean_ms": round(statistics.mean(latencies), 1) if latencies else 0.0,
        "latency_median_ms": round(statistics.median(latencies), 1) if latencies else 0.0,
        "latency_p95_ms": _percentile(latencies, 95.0),
    }


async def _run_queries_chroma(
    searcher: ChromaGuidelineSearch,
    queries: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    records: list[dict[str, Any]] = []
    errors = 0
    for q in queries:
        t0 = time.perf_counter()
        try:
            scored, _ = await searcher.search_with_scores(
                q["query"], limit=5, apply_threshold=False
            )
            latency_ms = round((time.perf_counter() - t0) * 1000.0, 1)
            raw_hits = [
                {
                    "doc_id": h.doc_id,
                    "section": h.section,
                    "score": score,
                    "excerpt": h.text[:160],
                }
                for h, score, _ in scored
            ]
        except Exception as exc:
            errors += 1
            latency_ms = round((time.perf_counter() - t0) * 1000.0, 1)
            raw_hits = []
            records.append({**q, "latency_ms": latency_ms, "raw_hits": raw_hits, "error": str(exc)})
            continue
        records.append({**q, "latency_ms": latency_ms, "raw_hits": raw_hits, "error": ""})
    return records, errors


async def _run_queries_bm25(
    searcher: Bm25GuidelineSearch,
    queries: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    records: list[dict[str, Any]] = []
    errors = 0
    for q in queries:
        t0 = time.perf_counter()
        try:
            scored = await searcher.search_with_scores(q["query"], limit=5)
            latency_ms = round((time.perf_counter() - t0) * 1000.0, 1)
            raw_hits = [
                {
                    "doc_id": h.doc_id,
                    "section": h.section,
                    "score": score,
                    "excerpt": h.text[:160],
                }
                for h, score in scored
            ]
        except Exception as exc:
            errors += 1
            latency_ms = round((time.perf_counter() - t0) * 1000.0, 1)
            records.append({**q, "latency_ms": latency_ms, "raw_hits": [], "error": str(exc)})
            continue
        records.append({**q, "latency_ms": latency_ms, "raw_hits": raw_hits, "error": ""})
    return records, errors


async def _check_limits_and_reproducibility(searcher: Any, sample_query: str) -> dict[str, Any]:
    r1 = await searcher.search(sample_query, limit=1)
    r3_a = await searcher.search(sample_query, limit=3)
    r3_b = await searcher.search(sample_query, limit=3)
    r5 = await searcher.search(sample_query, limit=5)
    reverse_ok = True
    for hit in r3_a:
        resolved = await searcher.resolve_evidence(hit.doc_id, hit.section)
        if resolved != hit:
            reverse_ok = False
    return {
        "limit_1_count": len(r1),
        "limit_3_count": len(r3_a),
        "limit_5_count": len(r5),
        "reproducible_identical": r3_a == r3_b,
        "reverse_lookup_all_exact": reverse_ok,
    }


async def run_evaluation(args: argparse.Namespace) -> dict[str, Any]:
    dataset = json.loads(Path(args.dataset).read_text(encoding="utf-8"))
    cal_queries = dataset["calibration_queries"]
    hold_queries = dataset["holdout_queries"]

    audit = audit_source_manifest(args.sources_dir, manifest_path=args.manifest_path)
    loaded_doc_ids = set(audit["approved_ready_doc_ids"])

    results: dict[str, Any] = {
        "executed_at_utc": datetime.now(UTC).isoformat(),
        "data_origin": "real_official_local_sources",
        "manifest_audit": audit,
        "corpus_completeness_note": (
            f"승인·적재된 공식 문헌 {len(loaded_doc_ids)}/{audit['total_manifest_docs']}종 "
            f"(누락/미승인: {audit['missing_or_unapproved_doc_ids']})"
        ),
        "evaluators": {},
    }

    # 1) BM25 평가 (외부 API 없음)
    bm25 = Bm25GuidelineSearch.from_sources_dir(
        args.sources_dir, manifest_path=args.manifest_path, enable_bilingual_expand=True
    )
    bm25_cal, bm25_cal_err = await _run_queries_bm25(bm25, cal_queries)
    bm25_hold, bm25_hold_err = await _run_queries_bm25(bm25, hold_queries)
    bm25_checks = await _check_limits_and_reproducibility(bm25, cal_queries[0]["query"])
    results["evaluators"]["bm25"] = {
        "type": "bm25",
        "bilingual_expand": True,
        "api_calls": 0,
        "prompt_tokens": 0,
        "estimated_cost_usd": 0.0,
        "error_count": bm25_cal_err + bm25_hold_err,
        "calibration": _compute_metrics_for_threshold(
            bm25_cal, loaded_doc_ids=loaded_doc_ids, threshold=0.0001
        ),
        "holdout": _compute_metrics_for_threshold(
            bm25_hold, loaded_doc_ids=loaded_doc_ids, threshold=0.0001
        ),
        "checks": bm25_checks,
        "calibration_details": bm25_cal,
        "holdout_details": bm25_hold,
    }

    # 2) OpenAI Embeddings + Chroma 평가
    if not args.bm25_only:
        api_key = _read_env("OPENAI_API_KEY")
        base_url = _read_env("OPENAI_BASE_URL") or None
        thresholds = [0.40, 0.45, 0.50, 0.55]

        for model_name in args.models:
            tracker = EmbeddingUsageTracker()
            backend = OpenAIEmbeddingBackend(
                api_key=api_key,
                model=model_name,
                base_url=base_url,
                usage_tracker=tracker,
            )
            persist_dir = Path(args.chroma_root) / model_name.replace("/", "_")
            idx_report = index_guideline_sources(
                sources_dir=args.sources_dir,
                persist_dir=persist_dir,
                manifest_path=args.manifest_path,
                embedding_model=model_name,
                embedding_backend=backend,
                force_rebuild=args.rebuild,
            )
            searcher = ChromaGuidelineSearch(
                persist_dir=persist_dir,
                embedding_backend=backend,
                embedding_model=model_name,
                min_relevance_score=0.50,
                enable_bilingual_expand=True,
            )
            cal_recs, cal_err = await _run_queries_chroma(searcher, cal_queries)
            hold_recs, hold_err = await _run_queries_chroma(searcher, hold_queries)
            checks = await _check_limits_and_reproducibility(searcher, cal_queries[0]["query"])

            price_rate = _PRICE_PER_1M_TOKENS.get(model_name, 0.0)
            est_cost = round((tracker.prompt_tokens / 1_000_000.0) * price_rate, 6)

            results["evaluators"][model_name] = {
                "type": "chroma_openai",
                "embedding_model": model_name,
                "active_version": idx_report["active_version"],
                "indexed_chunks": idx_report["indexed_chunks"],
                "bilingual_expand": True,
                "api_calls": tracker.call_count,
                "prompt_tokens": tracker.prompt_tokens,
                "estimated_cost_usd": est_cost,
                "error_count": cal_err + hold_err + tracker.error_count,
                "calibration_sweep": [
                    _compute_metrics_for_threshold(
                        cal_recs, loaded_doc_ids=loaded_doc_ids, threshold=th
                    )
                    for th in thresholds
                ],
                "holdout_sweep": [
                    _compute_metrics_for_threshold(
                        hold_recs, loaded_doc_ids=loaded_doc_ids, threshold=th
                    )
                    for th in thresholds
                ],
                "checks": checks,
                "calibration_details": cal_recs,
                "holdout_details": hold_recs,
            }

    out_dir = Path(args.report_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    json_path = out_dir / f"rag_eval_v02_{ts}.json"
    md_path = out_dir / f"rag_eval_v02_{ts}.md"
    json_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    header = (
        "| 검색기 | 데이터셋 | Hit@1 | Hit@3 | Recall@3 | MRR | OOS 거절률 "
        "| 평균(ms) | 중앙값(ms) | P95(ms) | 오류 | 토큰/비용(USD) |"
    )
    sep = "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |"
    md_lines = [
        "# NutriSight RAG v0.2 재현 평가 리포트",
        "",
        f"- **실행 시각(UTC)**: {results['executed_at_utc']}",
        f"- **데이터 구분**: 실제 공식 원문 로컬 파일 (`{args.sources_dir}`)",
        f"- **문헌 확보 상태**: {results['corpus_completeness_note']}",
        "",
        "## 요약 비교 (기준 임계값 `0.50` / BM25 `>0`)",
        "",
        header,
        sep,
    ]
    for name, ev in results["evaluators"].items():
        if ev["type"] == "bm25":
            for split in ("calibration", "holdout"):
                m = ev[split]
                row = (
                    f"| `bm25` | {split} | {m['hit_at_1'] * 100:.1f}% "
                    f"| {m['hit_at_3'] * 100:.1f}% | {m['recall_at_3'] * 100:.1f}% "
                    f"| {m['mrr']:.3f} | {m['oos_rejection_rate'] * 100:.1f}% "
                    f"| {m['latency_mean_ms']:.1f} | {m['latency_median_ms']:.1f} "
                    f"| {m['latency_p95_ms']:.1f} | {ev['error_count']} | 0 / $0 |"
                )
                md_lines.append(row)
        else:
            for split, key in (
                ("calibration", "calibration_sweep"),
                ("holdout", "holdout_sweep"),
            ):
                m = next(x for x in ev[key] if x["threshold"] == 0.50)
                row = (
                    f"| `{name}` | {split} | {m['hit_at_1'] * 100:.1f}% "
                    f"| {m['hit_at_3'] * 100:.1f}% | {m['recall_at_3'] * 100:.1f}% "
                    f"| {m['mrr']:.3f} | {m['oos_rejection_rate'] * 100:.1f}% "
                    f"| {m['latency_mean_ms']:.1f} | {m['latency_median_ms']:.1f} "
                    f"| {m['latency_p95_ms']:.1f} | {ev['error_count']} "
                    f"| {ev['prompt_tokens']} / ${ev['estimated_cost_usd']:.6f} |"
                )
                md_lines.append(row)

    md_text = "\n".join(md_lines)
    md_path.write_text(md_text, encoding="utf-8")
    print(md_text)
    print(f"\n[SAVED] JSON: {json_path}")
    print(f"[SAVED] Markdown: {md_path}")
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="NutriSight v0.2 Reproducible RAG Evaluator")
    parser.add_argument("--sources-dir", default=str(DEFAULT_SOURCES_DIR))
    parser.add_argument("--manifest-path", default=str(DEFAULT_MANIFEST_PATH))
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET_PATH))
    parser.add_argument("--chroma-root", default=str(DEFAULT_EVAL_CHROMA_ROOT))
    parser.add_argument("--report-dir", default=str(DEFAULT_REPORT_DIR))
    parser.add_argument(
        "--models",
        nargs="+",
        default=["text-embedding-3-small", "text-embedding-3-large"],
    )
    parser.add_argument("--bm25-only", action="store_true")
    parser.add_argument("--rebuild", action="store_true")
    args = parser.parse_args()
    asyncio.run(run_evaluation(args))
    return 0


if __name__ == "__main__":
    sys.exit(main())
