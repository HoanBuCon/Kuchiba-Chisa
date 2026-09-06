"""Diagnostic-only Voyage pilot; formal approved-golden gate remains unchanged."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config.settings import settings  # noqa: E402 - direct script bootstrap
from app.domain.interfaces.reranker import RerankerUnavailableError  # noqa: E402
from app.infrastructure.embeddings.fastembed_adapter import FastEmbedAdapter  # noqa: E402
from app.infrastructure.rag.api_cross_encoder_reranker import (  # noqa: E402
    ApiCrossEncoderReranker,
    ApiRerankerProvider,
)
from scripts.benchmark_rag05_reranker import (  # noqa: E402
    PublicDocument,
    SparseTextEncoder,
    TokenEstimator,
    VoyageTierZeroPacer,
    _conservative_provider_token_estimate,
    _hybrid_rrf_order,
    _percentile,
)

PILOT = ROOT / "data/evaluations/drafts/rag05_raw_wiki_pilot_v1.json"
REPORT = ROOT / "data/evaluations/drafts/rag05_raw_wiki_pilot_v1.benchmark.json"


def raw_documents() -> dict[str, PublicDocument]:
    result: dict[str, PublicDocument] = {}
    for page in (ROOT / "data/raw_wiki").rglob("*_main.wikitext"):
        meta = json.loads(page.with_suffix(".meta.json").read_text(encoding="utf-8"))
        text = page.read_text(encoding="utf-8")
        checksum = hashlib.sha256(text.encode()).hexdigest()[:16]
        evidence_id = f"raw_wiki:{meta['page_id']}:{meta['revision_id']}:{checksum}:chunk:000"
        result[evidence_id] = PublicDocument(evidence_id, " ".join(text.split())[:1200])
    return result


def rank(expected: list[str], ordered: list[str]) -> int | None:
    positions = [ordered.index(item) + 1 for item in expected if item in ordered]
    return min(positions) if positions else None


def aggregate(ranks: list[int | None]) -> dict[str, float]:
    total = len(ranks)
    return {
        "hit_at_1": sum(rank_value == 1 for rank_value in ranks) / total,
        "hit_at_3": sum(rank_value is not None and rank_value <= 3 for rank_value in ranks) / total,
        "hit_at_5": sum(rank_value is not None and rank_value <= 5 for rank_value in ranks) / total,
        "mrr_at_10": sum(1 / rank_value for rank_value in ranks if rank_value and rank_value <= 10)
        / total,
    }


def latency_summary(values: list[float]) -> dict[str, float]:
    if not values:
        return {"min": 0.0, "mean": 0.0, "p50": 0.0, "p95": 0.0, "max": 0.0}
    return {
        "min": round(min(values), 3),
        "mean": round(sum(values) / len(values), 3),
        "p50": _percentile(values, 50),
        "p95": _percentile(values, 95),
        "max": round(max(values), 3),
    }


async def run() -> dict[str, Any]:
    pilot = json.loads(PILOT.read_text(encoding="utf-8"))
    if pilot.get("approval", {}).get("status") != "draft":
        raise RuntimeError("authorized pilot requires the immutable draft pilot")
    if settings.RERANKER_PROVIDER != "voyage" or not settings.VOYAGE_API_KEY:
        raise RuntimeError("configured Voyage credentials are required")
    document_by_id = raw_documents()
    cases = pilot["cases"]
    if any(any(item not in document_by_id for item in case["evidence_ids"]) for case in cases):
        raise RuntimeError("pilot contains an evidence ID absent from raw_wiki")
    documents = list(document_by_id.values())
    embedder = FastEmbedAdapter()
    vectors = await embedder.embed_batch([item.text for item in documents], prefix="passage: ")
    sparse = SparseTextEncoder()
    pacer = VoyageTierZeroPacer()
    baseline_ranks: list[int | None] = []
    voyage_ranks: list[int | None] = []
    pacing_waits: list[float] = []
    provider_http_latencies: list[float] = []
    reranker_total_elapsed: list[float] = []
    total_latencies: list[float] = []
    processed_tokens = 0
    provider_calls = 0
    failures: dict[str, int] = {
        "rate_limit": 0,
        "timeout": 0,
        "provider": 0,
        "invalid_response": 0,
        "unavailable": 0,
    }
    results: list[dict[str, Any]] = []
    async with httpx.AsyncClient() as client:
        reranker = ApiCrossEncoderReranker(
            provider=ApiRerankerProvider.VOYAGE,
            api_key=settings.VOYAGE_API_KEY,
            model_name=settings.RERANKER_API_MODEL,
            timeout_seconds=settings.RERANKER_TIMEOUT_SECONDS,
            max_documents=settings.RERANKER_API_MAX_DOCUMENTS,
            http_client=client,
        )
        for case in cases:
            started = time.perf_counter()
            # Diagnostic mode deliberately avoids the deployment Redis cache: a
            # cache credential outage must not distort retrieval/reranker latency.
            query_vector = (await embedder.embed_batch([case["query"]], prefix="query: "))[0]
            baseline_ids = _hybrid_rrf_order(
                documents, query_vector, vectors, case["query"], sparse
            )[:15]
            before = rank(case["evidence_ids"], baseline_ids)
            baseline_ranks.append(before)
            candidates = [document_by_id[item] for item in baseline_ids]
            estimate = _conservative_provider_token_estimate(case["query"], candidates)
            rerank_started = time.perf_counter()
            pacing_wait_ms = 0.0
            provider_http_latency_ms: float | None = None
            try:
                pacing_wait_ms = await pacer.reserve(estimate)
                provider_calls += 1
                scores = await reranker.rerank(case["query"], [item.text for item in candidates])
                provider_http_latency_ms = reranker.last_http_latency_ms
                if provider_http_latency_ms is None:
                    raise RuntimeError("successful reranker call did not publish HTTP latency")
                after_ids = [
                    item.document_id
                    for item, _ in sorted(
                        zip(candidates, scores, strict=True), key=lambda pair: -pair[1]
                    )
                ]
                after = rank(case["evidence_ids"], after_ids)
                voyage_ranks.append(after)
                status = "success"
                provider_http_latencies.append(provider_http_latency_ms)
                processed_tokens += sum(
                    TokenEstimator.estimate(item.text) for item in candidates
                ) + TokenEstimator.estimate(case["query"]) * len(candidates)
            except RerankerUnavailableError as error:
                after_ids = []
                after = None
                status = f"degraded:{error.failure_kind.value}"
                failures[error.failure_kind.value] += 1
            reranker_elapsed_ms = (time.perf_counter() - rerank_started) * 1000
            pacing_waits.append(pacing_wait_ms)
            reranker_total_elapsed.append(reranker_elapsed_ms)
            total_latencies.append((time.perf_counter() - started) * 1000)
            results.append(
                {
                    "case_id": case["case_id"],
                    "query": case["query"],
                    "expected_evidence_ids": case["evidence_ids"],
                    "baseline_top_k_evidence_ids": baseline_ids,
                    "voyage_top_k_evidence_ids": after_ids,
                    "baseline_rank": before,
                    "voyage_rank": after,
                    "baseline_reciprocal_rank": (1 / before if before else 0),
                    "voyage_reciprocal_rank": (1 / after if after else 0),
                    "provider_status": status,
                    "processed_token_estimate": estimate,
                    "pacing_wait_ms": round(pacing_wait_ms, 3),
                    "provider_http_latency_ms": (
                        round(provider_http_latency_ms, 3)
                        if provider_http_latency_ms is not None
                        else None
                    ),
                    "reranker_total_elapsed_ms": round(reranker_elapsed_ms, 3),
                    "total_retrieval_latency_ms": round(total_latencies[-1], 3),
                }
            )
    successful = [item for item in results if item["provider_status"] == "success"]
    improved = [
        item["case_id"]
        for item in successful
        if item["voyage_rank"] is not None
        and (item["baseline_rank"] is None or item["voyage_rank"] < item["baseline_rank"])
    ]
    unchanged = [
        item["case_id"]
        for item in successful
        if item["voyage_rank"] == item["baseline_rank"]
    ]
    degraded = [
        item["case_id"]
        for item in successful
        if item["baseline_rank"] is not None
        and (item["voyage_rank"] is None or item["voyage_rank"] > item["baseline_rank"])
    ]
    return {
        "mode": "authorized-pilot-diagnostic",
        "formal_rag05_acceptance": False,
        "approval_status": "draft",
        "provider": "voyage",
        "model": settings.RERANKER_API_MODEL,
        "cases": results,
        "baseline": aggregate(baseline_ranks),
        "voyage": aggregate(voyage_ranks) if len(successful) == len(cases) else None,
        "context_precision": "not_evaluable_label_incomplete",
        "case_outcomes": {
            "improved": improved,
            "unchanged": unchanged,
            "degraded": degraded,
        },
        "provider_http_latency_ms": latency_summary(provider_http_latencies),
        "pacing_wait_ms": {
            "total": round(sum(pacing_waits), 3),
            "mean": round(sum(pacing_waits) / len(pacing_waits), 3),
            "p50": _percentile(pacing_waits, 50),
            "p95": _percentile(pacing_waits, 95),
            "paced_case_count": sum(wait > 0 for wait in pacing_waits),
        },
        "reranker_total_elapsed_ms": latency_summary(reranker_total_elapsed),
        "total_retrieval_latency_ms": {
            "p50": _percentile(total_latencies, 50),
            "p95": _percentile(total_latencies, 95),
        },
        "provider_calls": provider_calls,
        "provider_success_count": len(successful),
        "processed_tokens": processed_tokens,
        "estimated_cost_usd": round(processed_tokens * 0.02 / 1_000_000, 8),
        "failures": failures,
        "fallback_count": len(cases) - len(successful),
        "privacy_policy_rejection_count": 0,
        "initial_candidate_pool_misses": [
            item["case_id"] for item in results if item["baseline_rank"] is None
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True, choices=["authorized-pilot"])
    args = parser.parse_args()
    if args.mode != "authorized-pilot":
        raise RuntimeError("explicit authorized pilot mode required")
    report = asyncio.run(run())
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                key: report[key]
                for key in (
                    "provider_calls",
                    "failures",
                    "fallback_count",
                    "initial_candidate_pool_misses",
                )
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
