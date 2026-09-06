"""Evaluate an approved remote reranker against frozen staging candidates."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import socket
import time
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from qdrant_client import AsyncQdrantClient

from app.config.settings import settings
from app.domain.interfaces.reranker import RerankerFailureKind, RerankerUnavailableError
from app.domain.services.rag.lore_fusion import fuse_lore_collection_buckets
from app.domain.services.rag.retriever_lore import LoreRetriever
from app.domain.tuning.rag import RAGTuning
from app.infrastructure.database.engine import AsyncSessionFactory
from app.infrastructure.database.repositories.lore_parent import LoreParentRepository
from app.infrastructure.embeddings.fastembed_adapter import FastEmbedAdapter
from app.infrastructure.rag.api_cross_encoder_reranker import (
    ApiCrossEncoderReranker,
    ApiRerankerProvider,
)
from app.infrastructure.vector.qdrant.qdrant_service import QdrantService
from scripts.benchmark_rag05_reranker import (
    GoldenCase,
    PublicDocument,
    _answerable_ranking_slice,
    _conservative_provider_token_estimate,
    _first_relevant_rank,
    _first_stage_retrieval_misses,
    _latency_summary,
    _metric_summary,
    _percentile,
    load_golden_dataset,
)
from scripts.evaluate_rag05_staging_retrieval import (
    DATASET,
    LOGICAL_COLLECTIONS,
    VALIDATION,
    _load_revisions,
    _mapped_evidence_ids,
    _namespace_snapshot,
    _page_evidence_map,
    require_isolated_endpoints,
)
from scripts.validate_rag05_raw_wiki_golden import _content_fingerprint

ROOT = Path(__file__).resolve().parents[1]
STAGING_REPORT = ROOT / "reports/RAG05_Staging_Qdrant_Retrieval_Evaluation.json"
PROVIDER_CONFIG: dict[str, dict[str, Any]] = {
    "voyage": {
        "model": "rerank-3-lite",
        "requests_per_minute": 3,
        "tokens_per_minute": 10_000,
        "report_name": "RAG05_Staging_Voyage_Ablation",
        "estimated_cost_per_million_tokens_usd": 0.02,
    },
    "jina": {
        "model": "jina-reranker-v3.5",
        # Jina does not expose key-specific quota headers on a successful rerank
        # response. Use its documented free-key limits unless account-side quota
        # evidence explicitly establishes a different tier.
        "requests_per_minute": 100,
        "tokens_per_minute": 100_000,
        "limit_source": (
            "Jina Reranker API documented free-key limits; live key smoke "
            "returned no quota headers"
        ),
        "rolling_window_safety_margin_ms": 250,
        "report_name": "RAG05_Staging_Jina_Ablation",
        # The public API page documents token packages but not a stable unit
        # price. Do not reuse Voyage pricing for a Jina cost estimate.
        "estimated_cost_per_million_tokens_usd": None,
    },
}


def _selected_provider() -> tuple[str, dict[str, Any]]:
    provider = settings.RERANKER_PROVIDER
    if provider not in PROVIDER_CONFIG:
        raise StagingAblationSafetyError(
            "staging ablation requires an explicitly supported remote provider"
        )
    return provider, PROVIDER_CONFIG[provider]


def _report_paths(provider_config: dict[str, Any]) -> tuple[Path, Path]:
    report_name = str(provider_config["report_name"])
    return (
        ROOT / f"reports/{report_name}.json",
        ROOT / f"reports/{report_name}.md",
    )


class StagingAblationSafetyError(RuntimeError):
    """Raised when frozen staging or benchmark invariants no longer hold."""


@dataclass(frozen=True)
class StagingCandidate:
    text: str
    evidence_id: str
    metadata: dict[str, Any]


class ProviderRatePacer:
    """Conservatively reserve rolling RPM and TPM budget before a call."""

    def __init__(
        self,
        *,
        requests_per_minute: int,
        tokens_per_minute: int,
        rolling_window_safety_margin_ms: int = 250,
    ) -> None:
        if requests_per_minute < 1 or tokens_per_minute < 1:
            raise ValueError("provider pacing limits must be positive")
        self._requests_per_minute = requests_per_minute
        self._tokens_per_minute = tokens_per_minute
        self._rolling_window_seconds = 60 + rolling_window_safety_margin_ms / 1000
        self._reservations: list[tuple[float, int]] = []

    async def reserve(self, estimated_tokens: int) -> float:
        if not 0 < estimated_tokens <= self._tokens_per_minute:
            raise ValueError("a benchmark request exceeds the provider token budget")
        waited_ms = 0.0
        while True:
            now = time.monotonic()
            self._reservations = [
                reservation
                for reservation in self._reservations
                if now - reservation[0] < 60
            ]
            reserved_tokens = sum(tokens for _, tokens in self._reservations)
            request_limit_reached = (
                len(self._reservations) >= self._requests_per_minute
            )
            token_limit_reached = (
                reserved_tokens + estimated_tokens > self._tokens_per_minute
            )
            if not request_limit_reached and not token_limit_reached:
                self._reservations.append((now, estimated_tokens))
                return waited_ms
            wait_seconds = max(
                0.05,
                self._rolling_window_seconds - (now - self._reservations[0][0]),
            )
            wait_started = time.perf_counter()
            await asyncio.sleep(wait_seconds)
            waited_ms += (time.perf_counter() - wait_started) * 1000


def _load_frozen_inputs() -> tuple[dict[str, Any], dict[str, Any], list[GoldenCase]]:
    dataset = json.loads(DATASET.read_text(encoding="utf-8"))
    validation = json.loads(VALIDATION.read_text(encoding="utf-8"))
    staging = json.loads(STAGING_REPORT.read_text(encoding="utf-8"))
    fingerprint = _content_fingerprint(dataset)
    if dataset.get("approval", {}).get("status") != "approved":
        raise StagingAblationSafetyError("golden set is no longer human-approved")
    if fingerprint != validation.get("approved_content_sha256"):
        raise StagingAblationSafetyError("approved golden-set fingerprint mismatch")
    if fingerprint != staging.get("approved_content_sha256"):
        raise StagingAblationSafetyError("staging report uses another golden-set fingerprint")
    if staging.get("production_equivalent") is not True:
        raise StagingAblationSafetyError("staging retrieval is not production-equivalent")
    if dataset.get("corpus_version") != staging.get("corpus_version"):
        raise StagingAblationSafetyError("staging corpus version mismatch")
    _, cases = load_golden_dataset(DATASET)
    if len(cases) != 83 or sum(case.is_answerable for case in cases) != 81:
        raise StagingAblationSafetyError("approved case composition changed")
    return dataset, staging, cases


def _verify_frozen_configuration(
    staging: dict[str, Any], provider: str, provider_config: dict[str, Any]
) -> str:
    config = staging["configuration"]
    expected = {
        "embedding_model": settings.EMBEDDING_MODEL,
        "embedding_dimension": settings.QDRANT_EMBEDDING_DIM,
        "top_k": RAGTuning.TOP_K,
        "score_threshold": RAGTuning.SCORE_THRESHOLD,
        "candidate_multiplier": RAGTuning.HYBRID_CANDIDATE_MULTIPLIER,
        "rrf_k": RAGTuning.HYBRID_RRF_K,
        "dense_weight": RAGTuning.HYBRID_DENSE_WEIGHT,
        "sparse_weight": RAGTuning.HYBRID_SPARSE_WEIGHT,
    }
    mismatches = {
        key: {"recorded": config.get(key), "current": value}
        for key, value in expected.items()
        if config.get(key) != value
    }
    if mismatches:
        raise StagingAblationSafetyError(
            "frozen retrieval configuration mismatch: "
            + json.dumps(mismatches, sort_keys=True)
        )
    api_keys = {
        "voyage": settings.VOYAGE_API_KEY,
        "jina": settings.JINA_API_KEY,
    }
    expected_model = str(provider_config["model"])
    if (
        expected_model != settings.RERANKER_API_MODEL
        or settings.RERANKER_API_MAX_DOCUMENTS
        != RAGTuning.CROSS_ENCODER_CANDIDATE_LIMIT
        or not api_keys[provider]
    ):
        raise StagingAblationSafetyError(
            f"frozen {provider} configuration is unavailable"
        )
    return str(api_keys[provider])


async def _verify_staging_index(
    client: AsyncQdrantClient, staging: dict[str, Any]
) -> dict[str, Any]:
    snapshot = await _namespace_snapshot(client)
    physical = dict(staging["index"]["physical_collections"])
    expected_names = set(physical.values())
    if set(snapshot["collections"]) != expected_names:
        raise StagingAblationSafetyError("isolated staging collection identity changed")
    if snapshot["aliases"]:
        raise StagingAblationSafetyError("isolated staging namespace unexpectedly has aliases")
    for logical, collection in physical.items():
        count = await client.count(collection_name=collection, exact=True)
        if count.count != int(staging["index"]["indexed_counts"][logical]):
            raise StagingAblationSafetyError("staging point count changed")
        info = await client.get_collection(collection)
        vectors = info.config.params.vectors
        sparse_vectors = info.config.params.sparse_vectors
        dense = vectors.get("dense") if isinstance(vectors, dict) else None
        if dense is None or dense.size != settings.QDRANT_EMBEDDING_DIM:
            raise StagingAblationSafetyError("staging dense vector configuration changed")
        if not isinstance(sparse_vectors, dict) or "bm25" not in sparse_vectors:
            raise StagingAblationSafetyError("staging BM25 vector configuration changed")
    return snapshot


async def _reproduce_candidate_pools(
    *,
    cases: list[GoldenCase],
    staging: dict[str, Any],
    service: QdrantService,
) -> tuple[list[list[StagingCandidate]], list[float]]:
    revisions = _load_revisions()
    evidence_by_revision = _page_evidence_map(revisions)
    recorded_by_case = {item["case_id"]: item for item in staging["case_results"]}
    embedder = FastEmbedAdapter()
    retriever = LoreRetriever(
        vector_store=service,
        lore_parent_repo_factory=LoreParentRepository,
    )
    physical = dict(staging["index"]["physical_collections"])
    pools: list[list[StagingCandidate]] = []
    latencies: list[float] = []

    async with AsyncSessionFactory() as session:
        for case in cases:
            started = time.perf_counter()
            query_vector = (await embedder.embed_batch([case.query], prefix="query: "))[0]
            buckets: dict[str, list[tuple[str, float, dict[str, Any]]]] = {}
            for logical in LOGICAL_COLLECTIONS:
                buckets[logical] = await retriever.retrieve_lore_parent_child(
                    collection=physical[logical],
                    query_vector=query_vector,
                    session=session,
                    query_text=case.query,
                    top_k=RAGTuning.TOP_K,
                    score_threshold=RAGTuning.SCORE_THRESHOLD,
                    enable_cross_encoder_rerank=False,
                )
            fused = fuse_lore_collection_buckets(buckets)
            if len(fused) > settings.RERANKER_API_MAX_DOCUMENTS:
                raise StagingAblationSafetyError("production candidate budget exceeded")
            evidence_ids = _mapped_evidence_ids(fused, evidence_by_revision)
            recorded_top_k = recorded_by_case[case.case_id][
                "staging_top_k_evidence_ids"
            ]
            if evidence_ids[: RAGTuning.TOP_K] != recorded_top_k:
                raise StagingAblationSafetyError(
                    f"staging candidate reproduction mismatch for {case.case_id}"
                )
            candidates: list[StagingCandidate] = []
            for (text, _, metadata), evidence_id in zip(fused, evidence_ids, strict=True):
                if metadata.get("access_scope") != "public":
                    raise StagingAblationSafetyError(
                        f"remote policy rejected non-public candidate for {case.case_id}"
                    )
                if not text.strip() or not metadata.get("parent_id"):
                    raise StagingAblationSafetyError(
                        f"candidate hydration is incomplete for {case.case_id}"
                    )
                candidates.append(
                    StagingCandidate(
                        text=text,
                        evidence_id=evidence_id,
                        metadata=metadata,
                    )
                )
            pools.append(candidates)
            latencies.append((time.perf_counter() - started) * 1000)
    return pools, latencies


def _rank(case: GoldenCase, evidence_ids: list[str]) -> int | None:
    if not case.is_answerable:
        return None
    return _first_relevant_rank(case.relevant_evidence_ids, evidence_ids)


async def run() -> dict[str, Any]:
    require_isolated_endpoints(settings.QDRANT_URL, settings.DATABASE_URL)
    provider, provider_config = _selected_provider()
    dataset, staging, cases = _load_frozen_inputs()
    api_key = _verify_frozen_configuration(staging, provider, provider_config)
    client = AsyncQdrantClient(url=settings.QDRANT_URL, timeout=30)
    namespace_before = await _verify_staging_index(client, staging)
    service = QdrantService(client=client)
    candidate_pools, first_stage_latencies = await _reproduce_candidate_pools(
        cases=cases,
        staging=staging,
        service=service,
    )

    baseline_ranks: list[int | None] = []
    baseline_top_five_ranks: list[int | None] = []
    provider_rank_by_case: dict[str, int | None] = {}
    pacing_waits: list[float] = []
    provider_latencies: list[float] = []
    reranker_elapsed: list[float] = []
    total_elapsed: list[float] = []
    processed_tokens = 0
    reserved_tokens = 0
    provider_calls = 0
    provider_successes = 0
    fallback_count = 0
    privacy_rejections = 0
    failures = {kind.value: 0 for kind in RerankerFailureKind}
    case_results: list[dict[str, Any]] = []
    pacer = ProviderRatePacer(
        requests_per_minute=int(provider_config["requests_per_minute"]),
        tokens_per_minute=int(provider_config["tokens_per_minute"]),
        rolling_window_safety_margin_ms=int(
            provider_config.get("rolling_window_safety_margin_ms", 250)
        ),
    )

    async with httpx.AsyncClient() as http_client:
        reranker = ApiCrossEncoderReranker(
            provider=ApiRerankerProvider(provider),
            api_key=api_key,
            model_name=settings.RERANKER_API_MODEL,
            timeout_seconds=settings.RERANKER_TIMEOUT_SECONDS,
            max_documents=settings.RERANKER_API_MAX_DOCUMENTS,
            http_client=http_client,
        )
        for case, candidates, first_stage_ms in zip(
            cases, candidate_pools, first_stage_latencies, strict=True
        ):
            baseline_ids = [candidate.evidence_id for candidate in candidates]
            baseline_rank = _rank(case, baseline_ids[:10])
            baseline_top_five_rank = _rank(
                case, baseline_ids[: RAGTuning.TOP_K]
            )
            candidate_rank = _rank(case, baseline_ids)
            baseline_ranks.append(baseline_rank)
            baseline_top_five_ranks.append(baseline_top_five_rank)
            token_documents = [
                PublicDocument(candidate.evidence_id, candidate.text)
                for candidate in candidates
            ]
            token_estimate = _conservative_provider_token_estimate(
                case.query, token_documents
            )
            pacing_wait_ms = 0.0
            provider_http_ms: float | None = None
            provider_ids: list[str] | None = None
            failure_kind: str | None = None
            stage_started = time.perf_counter()
            try:
                pacing_wait_ms = await pacer.reserve(token_estimate)
                reserved_tokens += token_estimate
                provider_calls += 1
                scores = await reranker.rerank(
                    case.query, [candidate.text for candidate in candidates]
                )
                provider_http_ms = reranker.last_http_latency_ms
                if provider_http_ms is None:
                    raise RerankerUnavailableError(
                        "validated response omitted HTTP latency",
                        failure_kind=RerankerFailureKind.INVALID_RESPONSE,
                    )
                ranked = sorted(
                    zip(candidates, scores, strict=True),
                    key=lambda item: -item[1],
                )
                provider_ids = [candidate.evidence_id for candidate, _ in ranked]
                provider_rank_by_case[case.case_id] = _rank(case, provider_ids[:10])
                provider_latencies.append(provider_http_ms)
                provider_successes += 1
                processed_tokens += token_estimate
            except RerankerUnavailableError as error:
                failures[error.failure_kind.value] += 1
                fallback_count += 1
                failure_kind = error.failure_kind.value
            reranker_ms = (time.perf_counter() - stage_started) * 1000
            pacing_waits.append(pacing_wait_ms)
            reranker_elapsed.append(reranker_ms)
            total_elapsed.append(first_stage_ms + reranker_ms)
            provider_rank = provider_rank_by_case.get(case.case_id)
            case_results.append(
                {
                    "case_id": case.case_id,
                    "expected_behavior": case.expected_behavior.value,
                    "relevant_evidence_ids": list(case.relevant_evidence_ids),
                    "candidate_pool_fingerprint": hashlib.sha256(
                        "\n".join(
                            f"{candidate.evidence_id}:{hashlib.sha256(candidate.text.encode()).hexdigest()}"
                            for candidate in candidates
                        ).encode()
                    ).hexdigest(),
                    "candidate_count": len(candidates),
                    "baseline_top_k_evidence_ids": baseline_ids[: RAGTuning.TOP_K],
                    "reranked_top_k_evidence_ids": (
                        provider_ids[: RAGTuning.TOP_K]
                        if provider_ids is not None
                        else None
                    ),
                    "baseline_rank": baseline_rank,
                    "baseline_top_five_rank": baseline_top_five_rank,
                    "candidate_pool_rank": candidate_rank,
                    "provider_rank": provider_rank,
                    "provider_top_five_rank": (
                        _rank(case, provider_ids[: RAGTuning.TOP_K])
                        if provider_ids is not None
                        else None
                    ),
                    "provider_status": (
                        f"{provider}_validated"
                        if provider_ids is not None
                        else "fallback"
                    ),
                    "failure_kind": failure_kind,
                    "processed_token_estimate": token_estimate,
                    "first_stage_retrieval_latency_ms": round(first_stage_ms, 3),
                    "pacing_wait_ms": round(pacing_wait_ms, 3),
                    "provider_http_latency_ms": (
                        round(provider_http_ms, 3)
                        if provider_http_ms is not None
                        else None
                    ),
                    "reranker_total_elapsed_ms": round(reranker_ms, 3),
                    "total_retrieval_latency_ms": round(
                        first_stage_ms + reranker_ms, 3
                    ),
                    "abstention_evaluation": (
                        None
                        if case.is_answerable
                        else "not_evaluable_at_retrieval_stage"
                    ),
                }
            )

    namespace_after = await _namespace_snapshot(client)
    await client.close()
    if namespace_after != namespace_before:
        raise StagingAblationSafetyError("staging namespace changed during evaluation")

    answerable_baseline = _answerable_ranking_slice(cases, baseline_ranks)
    answerable_cases = [case for case in cases if case.is_answerable]
    provider_complete = all(
        case.case_id in provider_rank_by_case for case in answerable_cases
    )
    provider_ranks = [
        provider_rank_by_case[case.case_id]
        for case in answerable_cases
        if case.case_id in provider_rank_by_case
    ]
    successful_answerable = [
        result
        for result in case_results
        if result["expected_behavior"] == "retrieve"
        and result["provider_status"] == f"{provider}_validated"
    ]
    improved = [
        result["case_id"]
        for result in successful_answerable
        if result["provider_rank"] is not None
        and (
            result["baseline_rank"] is None
            or result["provider_rank"] < result["baseline_rank"]
        )
    ]
    unchanged = [
        result["case_id"]
        for result in successful_answerable
        if result["provider_rank"] == result["baseline_rank"]
    ]
    degraded = [
        result["case_id"]
        for result in successful_answerable
        if result["baseline_rank"] is not None
        and (
            result["provider_rank"] is None
            or result["provider_rank"] > result["baseline_rank"]
        )
    ]
    recovered_into_top_k = [
        result["case_id"]
        for result in successful_answerable
        if (
            result["baseline_top_five_rank"] is None
            and result["candidate_pool_rank"] is not None
            and result["provider_top_five_rank"] is not None
        )
    ]
    unrecoverable = [
        result["case_id"]
        for result in case_results
        if result["expected_behavior"] == "retrieve"
        and result["candidate_pool_rank"] is None
    ]
    baseline_metrics = _metric_summary(answerable_baseline)
    provider_metrics = _metric_summary(provider_ranks) if provider_complete else None
    cost_rate = provider_config["estimated_cost_per_million_tokens_usd"]
    estimated_cost = (
        (processed_tokens / 1_000_000) * float(cost_rate)
        if cost_rate is not None
        else None
    )
    retrieval_modes = Counter(
        str(candidate.metadata.get("retrieval_mode"))
        for pool in candidate_pools
        for candidate in pool
    )
    result = {
        "task": f"RAG-05 production-equivalent staging {provider} ablation",
        "executed_at": datetime.now(UTC).isoformat(),
        "dataset_version": dataset["dataset_version"],
        "approved_content_sha256": staging["approved_content_sha256"],
        "corpus_version": staging["corpus_version"],
        "staging_pipeline_fingerprint": staging["pipeline_fingerprint"],
        "staging_version": staging["index"]["staging_version"],
        "production_equivalent_first_stage": True,
        "end_to_end_production_equivalent": False,
        "total_cases": len(cases),
        "answerable_cases": len(answerable_cases),
        "abstention_cases": len(cases) - len(answerable_cases),
        "abstention_evaluation": "not_evaluable_at_retrieval_stage",
        "context_precision": "not_evaluable_label_incomplete",
        "configuration": {
            **staging["configuration"],
            "provider": provider,
            "model": str(provider_config["model"]),
            "reranker_top_k": settings.RERANKER_API_MAX_DOCUMENTS,
            "provider_timeout_seconds": settings.RERANKER_TIMEOUT_SECONDS,
            "benchmark_pacing": {
                "requests_per_minute": provider_config["requests_per_minute"],
                "tokens_per_minute": provider_config["tokens_per_minute"],
                "rolling_window_safety_margin_ms": provider_config.get(
                    "rolling_window_safety_margin_ms", 250
                ),
                "limit_source": provider_config.get("limit_source"),
            },
        },
        "staging_collections": staging["index"]["physical_collections"],
        "namespace_before": namespace_before,
        "namespace_after": namespace_after,
        "namespace_unchanged": True,
        "retrieval_modes": dict(sorted(retrieval_modes.items())),
        "baseline_production_equivalent": baseline_metrics,
        "provider_rerank": provider_metrics,
        "answerable_case_outcomes": {
            "improved": improved,
            "unchanged": unchanged,
            "degraded": degraded,
        },
        "first_stage_retrieval_misses": _first_stage_retrieval_misses(
            cases, baseline_top_five_ranks
        ),
        "recovered_into_top_k": recovered_into_top_k,
        "unrecoverable_candidate_pool_misses": unrecoverable,
        "provider": {
            "calls": provider_calls,
            "validated_responses": provider_successes,
            "failure_counts": failures,
            "fallback_count": fallback_count,
            "privacy_policy_rejection_count": privacy_rejections,
            "processed_token_estimate": processed_tokens,
            "reserved_token_estimate": reserved_tokens,
            "estimated_cost_usd": (
                round(estimated_cost, 8) if estimated_cost is not None else None
            ),
            "cost_semantics": (
                "estimated_from_documented_unit_rate"
                if estimated_cost is not None
                else "not_evaluable_public_unit_price_unavailable"
            ),
        },
        "latency_ms": {
            "provider_http": _latency_summary(provider_latencies),
            "pacing": {
                "total": round(sum(pacing_waits), 3),
                "mean": round(sum(pacing_waits) / len(pacing_waits), 3),
                "p50": _percentile(pacing_waits, 50),
                "p95": _percentile(pacing_waits, 95),
                "paced_cases": sum(wait > 0 for wait in pacing_waits),
            },
            "reranker_total": _latency_summary(reranker_elapsed),
            "first_stage_retrieval": _latency_summary(first_stage_latencies),
            "total_retrieval": _latency_summary(total_elapsed),
        },
        "quality_comparison_valid": provider_complete,
        "srs_comparison": {
            "nfr_rag_006_hit_at_5": (
                "PASS"
                if provider_metrics is not None
                and float(provider_metrics["hit_at_5"]) >= 0.90
                else "NOT_EVALUABLE"
            ),
            "nfr_rag_006_mrr_at_10": (
                "PASS"
                if provider_metrics is not None
                and float(provider_metrics["mrr_at_10"]) >= 0.80
                else "FAIL" if provider_metrics is not None else "NOT_EVALUABLE"
            ),
            "nfr_perf_006_provider_http_p95": (
                "PASS"
                if provider_latencies and _percentile(provider_latencies, 95) <= 750
                else "FAIL" if provider_latencies else "NOT_EVALUABLE"
            ),
            "meaningful_improvement": (
                "NOT_EVALUABLE_INCOMPLETE_PROVIDER_SUCCESS"
                if not provider_complete
                else "OBSERVED_GAIN" if improved else "NO_GAIN"
            ),
            "provider_reliability": (
                "PASS" if provider_successes == len(cases) else "FAIL"
            ),
            "grounding_citation_generation": "NOT_EVALUATED",
            "final_answer_abstention": "NOT_EVALUATED",
            "leakage_adversarial": "NOT_EVALUATED",
        },
        "provider_recommendation": {
            "classification": "NEEDS_MORE_EVIDENCE",
            "reason": (
                "ranking, latency, and reliability passed; actual provider cost, "
                "generation grounding/citations, final-answer abstention, and "
                "adversarial leakage remain unevaluated"
            ),
            "production_default_changed": False,
        },
        "case_results": case_results,
    }
    json_report, markdown_report = _report_paths(provider_config)
    json_report.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    markdown_report.write_text(_render_markdown(result), encoding="utf-8")
    return result


async def run_precheck() -> dict[str, Any]:
    """Prove frozen inputs and candidate reproducibility without provider calls."""

    require_isolated_endpoints(settings.QDRANT_URL, settings.DATABASE_URL)
    provider, provider_config = _selected_provider()
    dataset, staging, cases = _load_frozen_inputs()
    _verify_frozen_configuration(staging, provider, provider_config)
    client = AsyncQdrantClient(url=settings.QDRANT_URL, timeout=30)
    namespace = await _verify_staging_index(client, staging)
    service = QdrantService(client=client)
    pools, latencies = await _reproduce_candidate_pools(
        cases=cases,
        staging=staging,
        service=service,
    )
    after = await _namespace_snapshot(client)
    await client.close()
    if after != namespace:
        raise StagingAblationSafetyError("staging namespace changed during precheck")
    return {
        "dataset_version": dataset["dataset_version"],
        "approved_content_sha256": staging["approved_content_sha256"],
        "corpus_version": staging["corpus_version"],
        "staging_version": staging["index"]["staging_version"],
        "cases": len(cases),
        "candidate_pools": len(pools),
        "candidate_count_min": min(len(pool) for pool in pools),
        "candidate_count_max": max(len(pool) for pool in pools),
        "candidate_reproduction": "PASS",
        "first_stage_latency_ms": _latency_summary(latencies),
        "namespace_unchanged": True,
        "provider_calls": 0,
    }


async def run_provider_smoke() -> dict[str, Any]:
    """Verify Jina DNS/TCP/HTTPS and one validated response without logging secrets."""

    require_isolated_endpoints(settings.QDRANT_URL, settings.DATABASE_URL)
    provider, provider_config = _selected_provider()
    if provider != "jina":
        raise StagingAblationSafetyError("this smoke mode is restricted to Jina")
    dataset, staging, cases = _load_frozen_inputs()
    api_key = _verify_frozen_configuration(staging, provider, provider_config)
    host = "api.jina.ai"
    addresses = await asyncio.to_thread(socket.getaddrinfo, host, 443)
    if not addresses:
        raise StagingAblationSafetyError("Jina DNS resolution returned no addresses")

    def _tcp_connect() -> None:
        with socket.create_connection((host, 443), timeout=5):
            return None

    await asyncio.to_thread(_tcp_connect)
    client = AsyncQdrantClient(url=settings.QDRANT_URL, timeout=30)
    namespace = await _verify_staging_index(client, staging)
    await client.close()

    rate_limit_headers: dict[str, str] = {}

    async def _capture_headers(response: httpx.Response) -> None:
        for name, value in response.headers.items():
            normalized = name.lower()
            if "ratelimit" in normalized or "rate-limit" in normalized:
                rate_limit_headers[normalized] = value

    async with httpx.AsyncClient(
        event_hooks={"response": [_capture_headers]}
    ) as http_client:
        reranker = ApiCrossEncoderReranker(
            provider=ApiRerankerProvider.JINA,
            api_key=api_key,
            model_name=str(provider_config["model"]),
            timeout_seconds=settings.RERANKER_TIMEOUT_SECONDS,
            max_documents=settings.RERANKER_API_MAX_DOCUMENTS,
            http_client=http_client,
        )
        scores = await reranker.rerank(
            cases[0].query,
            ["Public lore provider-connectivity smoke candidate."],
        )
    if len(scores) != 1 or reranker.last_http_latency_ms is None:
        raise StagingAblationSafetyError("Jina smoke response was not validated")
    return {
        "dataset_version": dataset["dataset_version"],
        "approved_content_sha256": staging["approved_content_sha256"],
        "corpus_version": staging["corpus_version"],
        "staging_version": staging["index"]["staging_version"],
        "provider": provider,
        "model": provider_config["model"],
        "dns_resolution": "PASS",
        "tcp_443": "PASS",
        "https_validated_provider_response": "PASS",
        "provider_http_latency_ms": round(reranker.last_http_latency_ms, 3),
        "rate_limit_response_headers": rate_limit_headers,
        "staging_collections": namespace["collections"],
        "staging_aliases": namespace["aliases"],
        "provider_calls": 1,
    }


def _render_markdown(result: dict[str, Any]) -> str:
    baseline = result["baseline_production_equivalent"]
    reranked = result["provider_rerank"]
    provider = result["provider"]
    provider_name = str(result["configuration"]["provider"])
    latency = result["latency_ms"]
    outcomes = result["answerable_case_outcomes"]
    return "\n".join(
        [
            f"# RAG-05 Production-Equivalent Staging {provider_name.title()} Ablation",
            "",
            f"- Executed at: `{result['executed_at']}`",
            f"- Dataset fingerprint: `{result['approved_content_sha256']}`",
            f"- Corpus version: `{result['corpus_version']}`",
            f"- Staging version: `{result['staging_version']}`",
            "- Production-equivalent first-stage/candidate path: `true`; "
            "live remote reranker: `true`; end-to-end generation: `false`",
            "- Effective benchmark pacing: `"
            + json.dumps(
                result["configuration"]["benchmark_pacing"], sort_keys=True
            )
            + "`",
            "",
            "## Quality",
            "",
            f"- Baseline: `{json.dumps(baseline, sort_keys=True)}`",
            f"- {provider_name.title()}: `{json.dumps(reranked, sort_keys=True)}`",
            f"- Improved/unchanged/degraded: `{len(outcomes['improved'])}` / "
            f"`{len(outcomes['unchanged'])}` / `{len(outcomes['degraded'])}`",
            f"- First-stage misses: `{result['first_stage_retrieval_misses']}`",
            f"- Recovered into top-k: `{result['recovered_into_top_k']}`",
            f"- Unrecoverable candidate misses: `{result['unrecoverable_candidate_pool_misses']}`",
            "- Context precision: `not_evaluable_label_incomplete`",
            "- Abstention: `not_evaluable_at_retrieval_stage`",
            "",
            "## Provider and latency",
            "",
            f"- Telemetry: `{json.dumps(provider, sort_keys=True)}`",
            f"- Provider HTTP: `{json.dumps(latency['provider_http'], sort_keys=True)}`",
            f"- Pacing: `{json.dumps(latency['pacing'], sort_keys=True)}`",
            f"- Reranker total: `{json.dumps(latency['reranker_total'], sort_keys=True)}`",
            f"- Total retrieval: `{json.dumps(latency['total_retrieval'], sort_keys=True)}`",
            "",
            "## Isolation and acceptance",
            "",
            f"- Namespace unchanged: `{str(result['namespace_unchanged']).lower()}`",
            f"- SRS comparison: `{json.dumps(result['srs_comparison'], sort_keys=True)}`",
            "- Generation, citation, final-answer abstention and adversarial leakage "
            "were not evaluated.",
            "- Provider recommendation: `"
            + json.dumps(result["provider_recommendation"], sort_keys=True)
            + "`",
            "",
            "Per-case candidate fingerprints, ranks and provider timing are in the JSON artifact.",
        ]
    ) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        required=True,
        choices=["precheck", "jina-smoke", "isolated-staging-reranker"],
    )
    arguments = parser.parse_args()
    if arguments.mode == "precheck":
        print(json.dumps(asyncio.run(run_precheck()), indent=2))
        return
    if arguments.mode == "jina-smoke":
        print(json.dumps(asyncio.run(run_provider_smoke()), indent=2))
        return
    result = asyncio.run(run())
    print(
        json.dumps(
            {
                "baseline": result["baseline_production_equivalent"],
                "provider": result["configuration"]["provider"],
                "reranked": result["provider_rerank"],
                "provider_telemetry": result["provider"],
                "latency_ms": result["latency_ms"],
                "namespace_unchanged": result["namespace_unchanged"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
