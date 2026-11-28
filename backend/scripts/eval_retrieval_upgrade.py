"""NutriSight RAG Retrieval Quality Upgrade A/B/C 평가 스크립트.

기능:
- 38문항 Work 데이터셋(Calibration 10 + Holdout 10 + Independent 12 + Patient 6) 기준으로
  A(Large v2.2), B(BM25 + Large + RRF), C(B + BGE ONNX Reranker)를 동일 지표로 비교한다.
- 평가 지표 분리 보고:
  1) Document Hit@1 / Hit@3 / Recall@3 / MRR
  2) Candidate Evidence Recall@10 (1단계 후보군 Top 10 내 필수 근거 그룹 커버율)
  3) Exact Evidence@3 (최종 Top 3에서 모든 필수 근거 그룹 충족 문항 수/비율)
  4) Raw OOS 차단율 + `safe_search_guidelines` 결합 OOS 차단율
  5) 정상 9문항 과차단 여부 + CKD 위험 9문항 차단율
  6) EvidenceRef 역조회, 반복 일관성, 지연(mean/median/p95), 오류 수
- GLIM Table 5 라벨 정합성 보정 규칙(`table:jpen2756-tbl-0005` <-> `xml:tbl:jpen2756-tbl-0005#c*`)을
  원본 결과 덮어쓰기 없이 별도 매핑 규칙으로 적용하고 보정 전/후 수치를 모두 보고한다.
- 기본 모드(`--cached-dense-json`)는 기존 v2.2 Large 캐시 결과를 사용해 API 비용 $0으로 동작한다.
  (단, 캐시 JSON이 Top 5인 경우 `cached_dense_top5`로 명시적으로 표기한다.)
- `--live-dense` 모드는 명시적으로 지정하고 `OPENAI_API_KEY`가 설정된 경우에만 실행한다.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import statistics
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.recommender.bm25_search import Bm25GuidelineSearch  # noqa: E402
from app.recommender.guideline_types import GuidelineHit  # noqa: E402
from app.recommender.hybrid_search import HybridGuidelineSearch, fuse_rrf  # noqa: E402
from app.recommender.rag_sources import DEFAULT_SOURCES_DIR, load_guideline_chunks  # noqa: E402
from app.recommender.reranker import (  # noqa: E402
    DEFAULT_BGE_ONNX_DIR,
    OnnxBgeReranker,
    RerankStatus,
)
from app.recommender.retrieval_guard import (  # noqa: E402
    RetrievalStatus,
    detect_unsupported_scope,
    safe_search_guidelines,
)

SPLITS = ("calibration", "holdout", "independent", "patient")

# GLIM Table 5 라벨 정합성 별도 매핑 규칙 (기존 v2.2 보고서·원본 데이터셋을 덮어쓰지 않음)
GLIM_TABLE5_LEGACY_REF = ("glim_2025", "table:jpen2756-tbl-0005")
GLIM_TABLE5_XML_PREFIX = "xml:tbl:jpen2756-tbl-0005#"


def matches_gold_ref(
    candidate_ref: tuple[str, str],
    gold_ref: tuple[str, str],
    *,
    apply_glim_table5_mapping: bool = False,
) -> bool:
    """후보 `(doc_id, section)`이 정답 `gold_ref`와 일치하는지 판정한다."""
    if candidate_ref == gold_ref:
        return True
    if (
        apply_glim_table5_mapping
        and gold_ref == GLIM_TABLE5_LEGACY_REF
        and candidate_ref[0] == "glim_2025"
        and candidate_ref[1].startswith(GLIM_TABLE5_XML_PREFIX)
    ):
        return True
    return False


def evaluate_passage_groups(
    ranked_refs: Sequence[tuple[str, str]],
    passage_groups: Sequence[Sequence[Sequence[str]]],
    *,
    apply_glim_table5_mapping: bool = False,
) -> tuple[int, int, bool]:
    """`ranked_refs`가 필수 근거 그룹(`passage_groups`) 중 몇 개를 충족하는지 계산한다."""
    if not passage_groups:
        return 0, 0, False
    covered = 0
    for group in passage_groups:
        group_refs = [(ref[0], ref[1]) for ref in group]
        hit = any(
            matches_gold_ref(
                cand,
                gold,
                apply_glim_table5_mapping=apply_glim_table5_mapping,
            )
            for cand in ranked_refs
            for gold in group_refs
        )
        if hit:
            covered += 1
    total = len(passage_groups)
    return covered, total, covered == total


def _percentile(values: Sequence[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, math.ceil(len(ordered) * pct / 100.0) - 1))
    return round(ordered[idx], 2)


def score_query_result(
    *,
    row: dict[str, Any],
    top3_refs: Sequence[tuple[str, str]],
    candidate_refs: Sequence[tuple[str, str]],
    latency_ms: float,
    error: bool = False,
    apply_glim_table5_mapping: bool = False,
) -> dict[str, Any]:
    """단일 문항의 문서·후보군·정밀 근거·OOS 지표를 계산한다."""
    is_oos = bool(row["is_out_of_scope"])
    expected_docs = set(row["expected_doc_ids"])
    groups = row.get("passage_groups", [])

    top3 = list(top3_refs)[:3]
    cand10 = list(candidate_refs)[:10]

    # Document metrics
    doc_hit1 = bool(top3 and top3[0][0] in expected_docs)
    doc_rr = next((1.0 / i for i, (doc, _) in enumerate(top3, 1) if doc in expected_docs), 0.0)
    doc_hit3 = doc_rr > 0.0
    doc_recall3 = (
        len({doc for doc, _ in top3} & expected_docs) / len(expected_docs)
        if expected_docs
        else None
    )

    # Candidate Evidence Recall@10 vs Exact Evidence@3
    cand_cov, total_groups, cand_all = evaluate_passage_groups(
        cand10, groups, apply_glim_table5_mapping=apply_glim_table5_mapping
    )
    top3_cov, _, top3_all = evaluate_passage_groups(
        top3, groups, apply_glim_table5_mapping=apply_glim_table5_mapping
    )

    # Raw OOS refusal vs safe_search_guidelines combined OOS refusal
    raw_oos_refusal = is_oos and (len(top3) == 0) and (not error)
    scope_blocked = detect_unsupported_scope(row["query"]) is not None
    safe_oos_refusal = is_oos and (scope_blocked or len(top3) == 0) and (not error)

    return {
        "query_id": row["query_id"],
        "query": row["query"],
        "is_out_of_scope": is_oos,
        "expected_doc_ids": sorted(expected_docs),
        "top3": top3,
        "candidate_count": len(cand10),
        "doc_hit1": doc_hit1,
        "doc_hit3": doc_hit3,
        "doc_rr3": doc_rr,
        "doc_recall3": doc_recall3,
        "cand10_groups_covered": cand_cov,
        "cand10_all_covered": cand_all,
        "top3_groups_covered": top3_cov,
        "total_groups": total_groups,
        "exact_evidence_at_3": top3_all,
        "raw_oos_refusal": raw_oos_refusal,
        "safe_oos_refusal": safe_oos_refusal,
        "scope_blocked": scope_blocked,
        "latency_ms": round(latency_ms, 2),
        "error": error,
    }


def aggregate_metrics(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """문항별 점수를 Split 또는 전체 집계 지표로 합산한다."""
    pos = [r for r in rows if not r["is_out_of_scope"]]
    neg = [r for r in rows if r["is_out_of_scope"]]
    latencies = [float(r["latency_ms"]) for r in rows]

    pos_n = len(pos)
    neg_n = len(neg)
    total_groups = sum(r["total_groups"] for r in pos)
    cand10_groups = sum(r["cand10_groups_covered"] for r in pos)
    top3_groups = sum(r["top3_groups_covered"] for r in pos)

    return {
        "queries": len(rows),
        "positive": pos_n,
        "oos": neg_n,
        "doc_hit1_count": sum(r["doc_hit1"] for r in pos),
        "doc_hit1_rate": round(sum(r["doc_hit1"] for r in pos) / pos_n, 4) if pos_n else 0.0,
        "doc_hit3_count": sum(r["doc_hit3"] for r in pos),
        "doc_hit3_rate": round(sum(r["doc_hit3"] for r in pos) / pos_n, 4) if pos_n else 0.0,
        "doc_recall3": round(statistics.mean(r["doc_recall3"] for r in pos), 4) if pos_n else 0.0,
        "doc_mrr": round(statistics.mean(r["doc_rr3"] for r in pos), 4) if pos_n else 0.0,
        "cand10_group_recall": round(cand10_groups / total_groups, 4) if total_groups else 0.0,
        "cand10_exact_all_count": sum(r["cand10_all_covered"] for r in pos),
        "cand10_exact_all_rate": (
            round(sum(r["cand10_all_covered"] for r in pos) / pos_n, 4) if pos_n else 0.0
        ),
        "exact_evidence3_count": sum(r["exact_evidence_at_3"] for r in pos),
        "exact_evidence3_rate": (
            round(sum(r["exact_evidence_at_3"] for r in pos) / pos_n, 4) if pos_n else 0.0
        ),
        "top3_group_coverage": round(top3_groups / total_groups, 4) if total_groups else 0.0,
        "top3_groups_covered": top3_groups,
        "total_groups": total_groups,
        "raw_oos_refusal_count": sum(r["raw_oos_refusal"] for r in neg),
        "raw_oos_refusal_rate": (
            round(sum(r["raw_oos_refusal"] for r in neg) / neg_n, 4) if neg_n else 0.0
        ),
        "safe_oos_refusal_count": sum(r["safe_oos_refusal"] for r in neg),
        "safe_oos_refusal_rate": (
            round(sum(r["safe_oos_refusal"] for r in neg) / neg_n, 4) if neg_n else 0.0
        ),
        "normal_overblocked_count": sum(r["scope_blocked"] for r in pos),
        "latency_mean_ms": round(statistics.mean(latencies), 2) if latencies else 0.0,
        "latency_median_ms": round(statistics.median(latencies), 2) if latencies else 0.0,
        "latency_p95_ms": _percentile(latencies, 95.0),
        "errors": sum(r["error"] for r in rows),
    }


def _load_cached_dense_by_qid(
    cached_json_path: Path,
    chunk_map: dict[tuple[str, str], GuidelineHit],
    *,
    threshold: float = 0.50,
) -> tuple[dict[str, list[tuple[GuidelineHit, float]]], dict[str, float], int]:
    """기존 v2.2 Large 평가 JSON에서 문항별 Dense 후보(threshold 적용)와 지연 시간을 로드한다."""
    data = json.loads(cached_json_path.read_text(encoding="utf-8"))
    hits_by_qid: dict[str, list[tuple[GuidelineHit, float]]] = {}
    latency_by_qid: dict[str, float] = {}
    max_raw_hits = 0
    for split in SPLITS:
        for row in data["splits"][split]["rows"]:
            qid = row["query_id"]
            raw_hits = row.get("raw_hits", [])
            max_raw_hits = max(max_raw_hits, len(raw_hits))
            parsed: list[tuple[GuidelineHit, float]] = []
            for h in raw_hits:
                score = float(h["score"])
                if score < threshold:
                    continue
                key = (h["doc_id"], h["section"])
                if key in chunk_map:
                    parsed.append((chunk_map[key], score))
            hits_by_qid[qid] = parsed
            latency_by_qid[qid] = float(row.get("latency_ms", 0.0))
    return hits_by_qid, latency_by_qid, max_raw_hits


async def run_evaluation(args: argparse.Namespace) -> dict[str, Any]:
    dataset = json.loads(Path(args.dataset).read_text(encoding="utf-8"))
    sources_dir = Path(args.sources)
    chunks, _ = load_guideline_chunks(sources_dir)
    chunk_map = {
        (c.doc_id, c.section): GuidelineHit(
            doc_id=c.doc_id,
            section=c.section,
            text=c.text,
            source_url=c.source_url,
        )
        for c in chunks
    }
    bm25 = Bm25GuidelineSearch(chunks, min_score=0.0, enable_bilingual_expand=True)

    dense_mode = "cached_dense_json"
    dense_candidate_depth = 0
    cached_dense_hits: dict[str, list[tuple[GuidelineHit, float]]] = {}
    cached_dense_lat: dict[str, float] = {}
    live_chroma = None

    if args.live_dense:
        import os

        from app.recommender.chroma_search import ChromaGuidelineSearch, OpenAIEmbeddingBackend

        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("--live-dense requires OPENAI_API_KEY (approval gate).")
        backend = OpenAIEmbeddingBackend(api_key=api_key, model=args.embedding_model)
        live_chroma = ChromaGuidelineSearch(
            persist_dir=args.chroma_dir,
            embedding_backend=backend,
            embedding_model=args.embedding_model,
            min_relevance_score=args.dense_threshold,
        )
        dense_mode = "live_chroma_top10"
        dense_candidate_depth = args.candidate_k
    else:
        cached_dense_hits, cached_dense_lat, dense_candidate_depth = _load_cached_dense_by_qid(
            Path(args.cached_dense_json), chunk_map, threshold=args.dense_threshold
        )

    reranker: OnnxBgeReranker | None = None
    reranker_available = False
    if args.enable_bge_reranker:
        model_dir = Path(args.bge_model_dir)
        if (model_dir / "model_int8.onnx").exists() and (model_dir / "tokenizer.json").exists():
            reranker = OnnxBgeReranker(
                model_dir=model_dir,
                max_tokens=args.rerank_max_tokens,
            )
            reranker_available = True

    systems = ["A_large_v22", "B_hybrid_rrf"]
    if reranker_available:
        systems.append("C_hybrid_bge_rerank")

    per_system_raw: dict[str, list[dict[str, Any]]] = {s: [] for s in systems}
    per_system_mapped: dict[str, list[dict[str, Any]]] = {s: [] for s in systems}
    traces: list[dict[str, Any]] = []
    rerank_truncated_total = 0
    rerank_unavailable_count = 0

    for split in SPLITS:
        for row in dataset[f"{split}_queries"]:
            qid = row["query_id"]
            query = row["query"]

            # 1) BM25 Top K
            t0 = time.perf_counter()
            bm25_scored = await bm25.search_with_scores(query, limit=args.candidate_k)
            bm25_ms = (time.perf_counter() - t0) * 1000.0
            bm25_hits = [h for h, _ in bm25_scored]
            bm25_scores = {(h.doc_id, h.section): s for h, s in bm25_scored}

            # 2) Dense Top K (cached or live)
            if live_chroma is not None:
                td0 = time.perf_counter()
                dense_scored_raw, _ = await live_chroma.search_with_scores(
                    query, limit=args.candidate_k, apply_threshold=True
                )
                dense_ms = (time.perf_counter() - td0) * 1000.0
                dense_hits = [h for h, _, _ in dense_scored_raw]
                dense_scores = {(h.doc_id, h.section): s for h, s, _ in dense_scored_raw}
            else:
                dense_list = cached_dense_hits.get(qid, [])
                dense_hits = [h for h, _ in dense_list]
                dense_scores = {(h.doc_id, h.section): s for h, s in dense_list}
                dense_ms = cached_dense_lat.get(qid, 0.0)

            dense_refs = [(h.doc_id, h.section) for h in dense_hits]

            # System A: Large v2.2 baseline
            per_system_raw["A_large_v22"].append(
                score_query_result(
                    row=row,
                    top3_refs=dense_refs[:3],
                    candidate_refs=dense_refs[:10],
                    latency_ms=dense_ms,
                    apply_glim_table5_mapping=False,
                )
            )
            per_system_mapped["A_large_v22"].append(
                score_query_result(
                    row=row,
                    top3_refs=dense_refs[:3],
                    candidate_refs=dense_refs[:10],
                    latency_ms=dense_ms,
                    apply_glim_table5_mapping=True,
                )
            )

            # System B: Hybrid (BM25 + Large + RRF, Dense 0건 OOS 가드 적용)
            tr0 = time.perf_counter()
            if len(dense_hits) == 0:
                rrf_candidates = ()
            else:
                rrf_candidates = fuse_rrf(
                    bm25_hits,
                    dense_hits,
                    rrf_k=args.rrf_k,
                    bm25_scores=bm25_scores,
                    dense_scores=dense_scores,
                )
            rrf_ms = (time.perf_counter() - tr0) * 1000.0
            hybrid_ms = dense_ms + bm25_ms + rrf_ms
            hybrid_refs = [(c.hit.doc_id, c.hit.section) for c in rrf_candidates]

            per_system_raw["B_hybrid_rrf"].append(
                score_query_result(
                    row=row,
                    top3_refs=hybrid_refs[:3],
                    candidate_refs=hybrid_refs[:10],
                    latency_ms=hybrid_ms,
                    apply_glim_table5_mapping=False,
                )
            )
            b_mapped_row = score_query_result(
                row=row,
                top3_refs=hybrid_refs[:3],
                candidate_refs=hybrid_refs[:10],
                latency_ms=hybrid_ms,
                apply_glim_table5_mapping=True,
            )
            per_system_mapped["B_hybrid_rrf"].append(b_mapped_row)

            # System C: Hybrid + BGE ONNX Reranker (Top 10 RRF candidates -> Top 3)
            rerank_refs: list[tuple[str, str]] = []
            rerank_scores_trace: list[dict[str, Any]] = []
            if reranker is not None:
                cand_for_rerank = [c.hit for c in rrf_candidates[: args.rerank_top_n]]
                rerank_res = await reranker.rerank(query, cand_for_rerank, limit=3)
                rerank_truncated_total += rerank_res.truncated_count
                if rerank_res.status != RerankStatus.OK:
                    rerank_unavailable_count += 1
                rerank_refs = [(h.doc_id, h.section) for h in rerank_res.hits]
                rerank_scores_trace = [
                    {
                        "doc_id": s.hit.doc_id,
                        "section": s.hit.section,
                        "score": s.score,
                        "orig_rrf_rank": s.original_rank,
                        "truncated": s.truncated,
                    }
                    for s in rerank_res.scored
                ]
                total_c_ms = hybrid_ms + rerank_res.latency_ms
                per_system_raw["C_hybrid_bge_rerank"].append(
                    score_query_result(
                        row=row,
                        top3_refs=rerank_refs[:3],
                        candidate_refs=hybrid_refs[:10],
                        latency_ms=total_c_ms,
                        apply_glim_table5_mapping=False,
                    )
                )
                c_mapped_row = score_query_result(
                    row=row,
                    top3_refs=rerank_refs[:3],
                    candidate_refs=hybrid_refs[:10],
                    latency_ms=total_c_ms,
                    apply_glim_table5_mapping=True,
                )
                per_system_mapped["C_hybrid_bge_rerank"].append(c_mapped_row)

            traces.append(
                {
                    "split": split,
                    "query_id": qid,
                    "query": query,
                    "is_out_of_scope": row["is_out_of_scope"],
                    "passage_groups": row.get("passage_groups", []),
                    "bm25_top10": [(h.doc_id, h.section) for h in bm25_hits[:10]],
                    "dense_candidates": dense_refs,
                    "rrf_top10": [
                        {
                            "doc_id": c.hit.doc_id,
                            "section": c.hit.section,
                            "rrf": c.rrf_score,
                            "bm25_rank": c.bm25_rank,
                            "dense_rank": c.dense_rank,
                        }
                        for c in rrf_candidates[:10]
                    ],
                    "rerank_top3": rerank_scores_trace,
                }
            )

    # Split-level & overall summary
    summary: dict[str, Any] = {
        "dense_mode": dense_mode,
        "dense_candidate_depth": dense_candidate_depth,
        "bm25_candidate_depth": args.candidate_k,
        "rrf_k": args.rrf_k,
        "rerank_top_n": args.rerank_top_n,
        "reranker_available": reranker_available,
        "rerank_truncated_total": rerank_truncated_total,
        "rerank_unavailable_count": rerank_unavailable_count,
        "corpus_chunks": len(chunks),
        "systems_raw_label": {},
        "systems_glim_table5_mapped": {},
        "splits_glim_table5_mapped": {},
        "traces": traces,
    }

    split_sizes = {s: len(dataset[f"{s}_queries"]) for s in SPLITS}
    for sys_name in systems:
        summary["systems_raw_label"][sys_name] = aggregate_metrics(per_system_raw[sys_name])
        summary["systems_glim_table5_mapped"][sys_name] = aggregate_metrics(
            per_system_mapped[sys_name]
        )
        split_agg: dict[str, Any] = {}
        offset = 0
        for s in SPLITS:
            n = split_sizes[s]
            split_agg[s] = aggregate_metrics(per_system_mapped[sys_name][offset : offset + n])
            offset += n
        summary["splits_glim_table5_mapped"][sys_name] = split_agg

    # Also verify safe_search_guidelines on hybrid (with dummy cached dense adapter)
    class _StaticDense:
        async def search(self, query: str, limit: int = 5) -> tuple[GuidelineHit, ...]:
            return ()

    _hybrid_probe = HybridGuidelineSearch(bm25_search=bm25, dense_search=_StaticDense())
    ckd_probe = await safe_search_guidelines(
        _hybrid_probe,
        "CKD G4 만성콩팥병 환자 단백질 목표가 미등록 상태인데 하루 몇 g/kg 처방할까?",
        limit=3,
    )
    summary["safety_probe_ckd_blocked"] = ckd_probe.status == RetrievalStatus.UNSUPPORTED_SCOPE

    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="NutriSight RAG Retrieval Quality Upgrade A/B/C")
    parser.add_argument(
        "--dataset", required=True, help="38-question evaluation-questions.json path"
    )
    parser.add_argument(
        "--sources",
        default=str(DEFAULT_SOURCES_DIR),
        help="Approved guideline sources directory",
    )
    parser.add_argument(
        "--cached-dense-json",
        default="",
        help="Existing v2.2 Large evaluation JSON for $0 offline comparison",
    )
    parser.add_argument("--live-dense", action="store_true", help="Query live Chroma + OpenAI API")
    parser.add_argument("--chroma-dir", default="var/eval_chroma_final/text-embedding-3-large")
    parser.add_argument("--embedding-model", default="text-embedding-3-large")
    parser.add_argument("--dense-threshold", type=float, default=0.50)
    parser.add_argument("--candidate-k", type=int, default=10)
    parser.add_argument("--rrf-k", type=int, default=60)
    parser.add_argument("--enable-bge-reranker", action="store_true")
    parser.add_argument("--bge-model-dir", default=str(DEFAULT_BGE_ONNX_DIR))
    parser.add_argument("--rerank-top-n", type=int, default=10)
    parser.add_argument("--rerank-max-tokens", type=int, default=512)
    parser.add_argument("--out-json", default="", help="Optional path to save full JSON output")
    args = parser.parse_args()

    result = asyncio.run(run_evaluation(args))
    if args.out_json:
        out_path = Path(args.out_json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    # Compact console summary
    compact = {k: v for k, v in result.items() if k != "traces"}
    print(json.dumps(compact, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
