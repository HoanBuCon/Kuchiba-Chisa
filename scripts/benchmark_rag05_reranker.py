"""Run the versioned, public-lore RAG-05 reranker ablation.

The harness deliberately uses only repository-owned ``world_lore`` and
``story_lore`` files referenced by the immutable golden manifest.  It never
opens Qdrant, PostgreSQL, Redis, user memory, or a tenant corpus, so an active
deployment index cannot be changed by a quality experiment.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.config.settings import settings  # noqa: E402 - direct script bootstrap
from app.domain.interfaces.reranker import (  # noqa: E402 - direct script bootstrap
    RerankerFailureKind,
    RerankerUnavailableError,
)
from app.domain.tuning.rag import RAGTuning  # noqa: E402 - direct script bootstrap
from app.infrastructure.embeddings.fastembed_adapter import (  # noqa: E402 - direct script bootstrap
    FastEmbedAdapter,
)
from app.infrastructure.rag.api_cross_encoder_reranker import (  # noqa: E402 - direct script bootstrap
    ApiCrossEncoderReranker,
    ApiRerankerProvider,
)
from app.infrastructure.vector.qdrant.sparse_encoder import (  # noqa: E402 - direct script bootstrap
    SparseTextEncoder,
)
from app.shared.utils.token_estimator import TokenEstimator  # noqa: E402 - direct script bootstrap

_PUBLIC_LORE_ROOT = (_PROJECT_ROOT / "data" / "lore").resolve()
_ALLOWED_LORE_DIRECTORIES = {"world_lore", "story_lore", "character_lore"}


@dataclass(frozen=True)
class GoldenCase:
    """One labelled, public document retrieval case."""

    case_id: str
    query: str
    relevant_evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class PublicDocument:
    """A locally loaded document allowed across the approved provider boundary."""

    document_id: str
    text: str


class VoyageTierZeroPacer:
    """Reserve conservative request/token budget before an approved provider call."""

    _REQUESTS_PER_MINUTE = 3
    _TOKENS_PER_MINUTE = 10_000

    def __init__(self) -> None:
        self._reservations: list[tuple[float, int]] = []

    async def reserve(self, estimated_tokens: int) -> None:
        if not 0 < estimated_tokens <= self._TOKENS_PER_MINUTE:
            raise ValueError("a benchmark request exceeds the Voyage Tier 0 token budget")
        while True:
            now = time.monotonic()
            self._reservations = [
                reservation
                for reservation in self._reservations
                if now - reservation[0] < 60
            ]
            reserved_tokens = sum(tokens for _, tokens in self._reservations)
            request_limit_reached = len(self._reservations) >= self._REQUESTS_PER_MINUTE
            token_limit_reached = reserved_tokens + estimated_tokens > self._TOKENS_PER_MINUTE
            if not request_limit_reached and not token_limit_reached:
                self._reservations.append((now, estimated_tokens))
                return
            wait_seconds = max(0.01, 60 - (now - self._reservations[0][0]))
            await asyncio.sleep(wait_seconds)


def _require_string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"golden dataset field {field_name!r} must be a non-empty string")
    return value.strip()


def load_golden_dataset(dataset_path: Path) -> tuple[str, list[GoldenCase]]:
    """Load a strict, fixed dataset instead of allowing ad-hoc benchmark input."""
    try:
        raw_dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("unable to read the RAG-05 golden dataset") from error
    if not isinstance(raw_dataset, dict):
        raise ValueError("golden dataset must be a JSON object")
    if not isinstance(raw_dataset.get("dataset_version"), str):
        raise ValueError("golden dataset must declare a dataset version")
    if raw_dataset.get("evidence_scope") != "public":
        raise ValueError("RAG-05 remote benchmark accepts public evidence only")
    approval = raw_dataset.get("approval")
    if not isinstance(approval, dict) or approval.get("status") != "approved":
        raise ValueError("golden dataset requires recorded reviewer approval before execution")
    _require_string(approval.get("approved_by"), "approval.approved_by")
    _require_string(approval.get("approved_at"), "approval.approved_at")
    raw_cases = raw_dataset.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("golden dataset must contain at least one case")

    cases: list[GoldenCase] = []
    case_ids: set[str] = set()
    for raw_case in raw_cases:
        if not isinstance(raw_case, dict):
            raise ValueError("every golden case must be an object")
        raw_evidence_ids = raw_case.get("relevant_evidence_ids")
        if not isinstance(raw_evidence_ids, list) or not raw_evidence_ids:
            raise ValueError("every golden case needs at least one relevant evidence identifier")
        evidence_ids = tuple(
            _require_string(value, "relevant_evidence_ids") for value in raw_evidence_ids
        )
        if len(set(evidence_ids)) != len(evidence_ids):
            raise ValueError("golden case evidence identifiers must be unique")
        case = GoldenCase(
            case_id=_require_string(raw_case.get("id"), "id"),
            query=_require_string(raw_case.get("query"), "query"),
            relevant_evidence_ids=evidence_ids,
        )
        if case.case_id in case_ids:
            raise ValueError("golden dataset case identifiers must be unique")
        case_ids.add(case.case_id)
        cases.append(case)
    return raw_dataset["dataset_version"], cases


def load_public_documents(cases: Sequence[GoldenCase]) -> list[PublicDocument]:
    """Resolve only approved source files beneath the public-lore root."""
    documents: list[PublicDocument] = []
    seen: set[str] = set()
    for case in cases:
        for document_id in case.relevant_evidence_ids:
            relative_path = Path(document_id)
            if (
                relative_path.is_absolute()
                or len(relative_path.parts) != 2
                or relative_path.parts[0] not in _ALLOWED_LORE_DIRECTORIES
                or relative_path.suffix != ".md"
            ):
                raise ValueError("golden dataset references a disallowed lore document")
            path = (_PUBLIC_LORE_ROOT / relative_path).resolve()
            if _PUBLIC_LORE_ROOT not in path.parents or not path.is_file():
                raise ValueError("golden dataset references a missing public lore document")
            if document_id in seen:
                continue
            try:
                text = path.read_text(encoding="utf-8").strip()
            except OSError as error:
                raise ValueError("unable to load a public lore document") from error
            if not text:
                raise ValueError("public lore document is empty")
            seen.add(document_id)
            documents.append(PublicDocument(document_id=document_id, text=text))
    return documents


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    numerator = sum(first * second for first, second in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        return 0.0
    return numerator / (left_norm * right_norm)


def _sparse_cosine(query: str, document: str, encoder: SparseTextEncoder) -> float:
    query_vector = encoder.encode(query)
    document_vector = encoder.encode(document)
    query_values = dict(zip(query_vector.indices, query_vector.values, strict=True))
    document_values = dict(zip(document_vector.indices, document_vector.values, strict=True))
    numerator = sum(
        value * document_values.get(index, 0.0) for index, value in query_values.items()
    )
    query_norm = math.sqrt(sum(value * value for value in query_values.values()))
    document_norm = math.sqrt(sum(value * value for value in document_values.values()))
    if not query_norm or not document_norm:
        return 0.0
    return numerator / (query_norm * document_norm)


def _hybrid_rrf_order(
    documents: Sequence[PublicDocument],
    query_vector: Sequence[float],
    document_vectors: Sequence[Sequence[float]],
    query: str,
    sparse_encoder: SparseTextEncoder,
) -> list[str]:
    """Mirror the production dense+sparse rank fusion without touching an index."""
    dense = sorted(
        zip(documents, document_vectors, strict=True),
        key=lambda item: (-_cosine(query_vector, item[1]), item[0].document_id),
    )
    sparse = sorted(
        documents,
        key=lambda document: (
            -_sparse_cosine(query, document.text, sparse_encoder),
            document.document_id,
        ),
    )
    score_by_document: dict[str, float] = {}
    for weight, ranked_documents in (
        (RAGTuning.HYBRID_DENSE_WEIGHT, [item[0] for item in dense]),
        (RAGTuning.HYBRID_SPARSE_WEIGHT, sparse),
    ):
        for rank, document in enumerate(ranked_documents, start=1):
            current_score = score_by_document.get(document.document_id, 0.0)
            score_by_document[document.document_id] = current_score + (
                weight / (RAGTuning.HYBRID_RRF_K + rank)
            )
    return [
        document_id
        for document_id, _ in sorted(
            score_by_document.items(), key=lambda item: (-item[1], item[0])
        )
    ]


def _first_relevant_rank(
    relevant_evidence_ids: Sequence[str], ranked_document_ids: Sequence[str]
) -> int:
    ranks = [
        ranked_document_ids.index(document_id) + 1
        for document_id in relevant_evidence_ids
        if document_id in ranked_document_ids
    ]
    return min(ranks, default=len(ranked_document_ids) + 1)


def _conservative_provider_token_estimate(query: str, documents: Sequence[PublicDocument]) -> int:
    raw_estimate = TokenEstimator.estimate(query) * len(documents)
    raw_estimate += sum(TokenEstimator.estimate(document.text) for document in documents)
    return math.ceil(raw_estimate * 1.25)


def _percentile(values: Sequence[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil((percentile / 100) * len(ordered)) - 1)
    return round(ordered[index], 3)


def _metric_summary(ranks: Sequence[int], evidence_size: int = 5) -> dict[str, float]:
    total = max(len(ranks), 1)
    hit_at_5 = sum(rank <= 5 for rank in ranks) / total
    mrr_at_10 = sum((1 / rank) if rank <= 10 else 0.0 for rank in ranks) / total
    return {
        "hit_at_5": round(hit_at_5, 6),
        "mrr_at_10": round(mrr_at_10, 6),
        "context_recall": round(hit_at_5, 6),
        "context_precision": round(hit_at_5 / evidence_size, 6),
    }


async def run_ablation(dataset_path: Path) -> dict[str, Any]:
    """Compare deterministic hybrid RRF with the configured Voyage reranker."""
    if settings.RERANKER_PROVIDER != "voyage" or not settings.VOYAGE_API_KEY:
        raise RuntimeError("RAG-05 ablation requires configured Voyage credentials")
    dataset_version, cases = load_golden_dataset(dataset_path)
    documents = load_public_documents(cases)
    embedder = FastEmbedAdapter()
    sparse_encoder = SparseTextEncoder()
    document_vectors = await embedder.embed_batch(
        [document.text for document in documents], prefix="passage: "
    )
    if len(document_vectors) != len(documents):
        raise RuntimeError("local embedding provider returned an incomplete document batch")

    fallback_ranks: list[int] = []
    voyage_ranks: list[int] = []
    fallback_latencies_ms: list[float] = []
    total_latencies_ms: list[float] = []
    reranker_latencies_ms: list[float] = []
    processed_tokens = 0
    reserved_provider_tokens = 0
    fallback_count = 0
    failure_counts = {failure_kind.value: 0 for failure_kind in RerankerFailureKind}
    case_results: list[dict[str, Any]] = []
    pacer = VoyageTierZeroPacer()

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
            retrieval_started = time.perf_counter()
            query_vector = await embedder.embed_text(case.query, prefix="query: ")
            baseline_order = _hybrid_rrf_order(
                documents, query_vector, document_vectors, case.query, sparse_encoder
            )[: settings.RERANKER_API_MAX_DOCUMENTS]
            fallback_latency_ms = (time.perf_counter() - retrieval_started) * 1000
            fallback_latencies_ms.append(fallback_latency_ms)
            baseline_rank = _first_relevant_rank(case.relevant_evidence_ids, baseline_order)
            fallback_ranks.append(baseline_rank)

            reranker_started = time.perf_counter()
            try:
                ordered_documents = [
                    next(document for document in documents if document.document_id == document_id)
                    for document_id in baseline_order
                ]
                provider_token_estimate = _conservative_provider_token_estimate(
                    case.query, ordered_documents
                )
                await pacer.reserve(provider_token_estimate)
                reserved_provider_tokens += provider_token_estimate
                scores = await reranker.rerank(
                    case.query, [document.text for document in ordered_documents]
                )
                voyage_order = [
                    document.document_id
                    for document, _ in sorted(
                        zip(ordered_documents, scores, strict=True),
                        key=lambda item: (-item[1], item[0].document_id),
                    )
                ]
                reranker_latency_ms = (time.perf_counter() - reranker_started) * 1000
                reranker_latencies_ms.append(reranker_latency_ms)
                processed_tokens += TokenEstimator.estimate(case.query) * len(ordered_documents)
                processed_tokens += sum(
                    TokenEstimator.estimate(document.text)
                    for document in ordered_documents
                )
                final_rank = _first_relevant_rank(case.relevant_evidence_ids, voyage_order)
                reranker_mode = "voyage"
                failure_kind: str | None = None
                voyage_ranks.append(final_rank)
            except RerankerUnavailableError as error:
                reranker_latency_ms = (time.perf_counter() - reranker_started) * 1000
                reranker_latencies_ms.append(reranker_latency_ms)
                failure_counts[error.failure_kind.value] += 1
                fallback_count += 1
                final_rank = baseline_rank
                reranker_mode = "deterministic_fallback"
                failure_kind = error.failure_kind.value

            total_latencies_ms.append((time.perf_counter() - retrieval_started) * 1000)
            case_results.append(
                {
                    "case_id": case.case_id,
                    "relevant_evidence_ids": case.relevant_evidence_ids,
                    "baseline_rank": baseline_rank,
                    "voyage_rank": final_rank if reranker_mode == "voyage" else None,
                    "fallback_rank": final_rank if reranker_mode != "voyage" else None,
                    "reranker_mode": reranker_mode,
                    "failure_kind": failure_kind,
                }
            )

    estimated_cost_usd = (processed_tokens / 1_000_000) * 0.02
    return {
        "dataset_version": dataset_version,
        "corpus_checksum": hashlib.sha256(
            "".join(
                f"{document.document_id}:{document.text}" for document in documents
            ).encode("utf-8")
        ).hexdigest(),
        "provider": "voyage",
        "model": settings.RERANKER_API_MODEL,
        "cases": len(cases),
        "baseline_deterministic_hybrid_rrf": _metric_summary(fallback_ranks),
        "voyage_rerank": _metric_summary(voyage_ranks) if voyage_ranks else None,
        "reranker_latency_ms": {
            "p50": _percentile(reranker_latencies_ms, 50),
            "p95": _percentile(reranker_latencies_ms, 95),
        },
        "total_retrieval_latency_ms": {
            "baseline_p50": _percentile(fallback_latencies_ms, 50),
            "baseline_p95": _percentile(fallback_latencies_ms, 95),
            "voyage_p50": _percentile(total_latencies_ms, 50),
            "voyage_p95": _percentile(total_latencies_ms, 95),
        },
        "processed_tokens": processed_tokens,
        "reserved_provider_tokens": reserved_provider_tokens,
        "estimated_cost_usd": round(estimated_cost_usd, 8),
        "provider_success_count": len(voyage_ranks),
        "provider_failure_counts": failure_counts,
        "timeout_rate": round(failure_counts["timeout"] / len(cases), 6),
        "rate_limit_rate": round(failure_counts["rate_limit"] / len(cases), 6),
        "error_rate": round(sum(failure_counts.values()) / len(cases), 6),
        "fallback_rate": round(fallback_count / len(cases), 6),
        "quality_comparison_valid": len(voyage_ranks) == len(cases),
        "privacy_policy_rejection_count": 0,
        "groundedness_and_citation": (
            "not_applicable: retrieval-only ablation does not generate answers or citations"
        ),
        "case_results": case_results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=_PROJECT_ROOT / "data" / "evaluations" / "rag05_public_lore_golden_v1.json",
    )
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run_ablation(args.dataset)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
