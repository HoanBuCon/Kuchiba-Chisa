"""Run the versioned, public raw_wiki RAG-05 reranker ablation.

The offline harness builds its candidate snapshot from the complete approved
``raw_wiki`` directory before it reads relevance labels. It never opens
Qdrant, PostgreSQL, Redis, user memory, or a tenant corpus, so an active
deployment index cannot be changed by an evaluation.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import re
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
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

_RAW_WIKI_ROOT = (_PROJECT_ROOT / "data" / "raw_wiki").resolve()
_RAW_WIKI_MAIN_SUFFIX = "_main.wikitext"
_RAW_WIKI_TEXT_LIMIT = 1200
_RAW_WIKI_EVIDENCE_ID = re.compile(
    r"^raw_wiki:(?P<page_id>[1-9][0-9]*):(?P<revision_id>[1-9][0-9]*):"
    r"(?P<checksum>[0-9a-f]{16}):chunk:000$"
)
_CONTEXT_PRECISION_NOT_EVALUABLE = "not_evaluable_label_incomplete"
_ABSTENTION_NOT_EVALUABLE = "not_evaluable_at_retrieval_stage"


class GoldenExpectedBehavior(StrEnum):
    """Schema-defined evaluation behavior for a golden case."""

    RETRIEVE = "retrieve"
    ABSTAIN = "abstain"


@dataclass(frozen=True)
class GoldenCase:
    """One human-approved public evaluation case."""

    case_id: str
    query: str
    relevant_evidence_ids: tuple[str, ...]
    expected_behavior: GoldenExpectedBehavior = GoldenExpectedBehavior.RETRIEVE

    @property
    def is_answerable(self) -> bool:
        """Return whether positive-evidence ranking metrics apply to this case."""
        return self.expected_behavior is GoldenExpectedBehavior.RETRIEVE


@dataclass(frozen=True)
class PublicDocument:
    """A locally loaded document allowed across the approved provider boundary."""

    document_id: str
    text: str
    source_path: str | None = None


class VoyageTierZeroPacer:
    """Reserve conservative request/token budget before an approved provider call."""

    _REQUESTS_PER_MINUTE = 3
    _TOKENS_PER_MINUTE = 10_000

    def __init__(self) -> None:
        self._reservations: list[tuple[float, int]] = []

    async def reserve(self, estimated_tokens: int) -> float:
        """Reserve capacity and return milliseconds actually spent asleep."""
        if not 0 < estimated_tokens <= self._TOKENS_PER_MINUTE:
            raise ValueError("a benchmark request exceeds the Voyage Tier 0 token budget")
        waited_ms = 0.0
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
                return waited_ms
            wait_seconds = max(0.01, 60 - (now - self._reservations[0][0]))
            wait_started = time.perf_counter()
            await asyncio.sleep(wait_seconds)
            waited_ms += (time.perf_counter() - wait_started) * 1000


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
        raw_behavior = raw_case.get("expected_behavior")
        if not isinstance(raw_behavior, str):
            raise ValueError(
                "golden case expected_behavior must be 'retrieve' or 'abstain'"
            )
        try:
            expected_behavior = GoldenExpectedBehavior(raw_behavior)
        except ValueError as error:
            raise ValueError(
                "golden case expected_behavior must be 'retrieve' or 'abstain'"
            ) from error
        raw_evidence_ids = raw_case.get("relevant_evidence_ids")
        if not isinstance(raw_evidence_ids, list):
            raise ValueError("golden case relevant_evidence_ids must be a list")
        if expected_behavior is GoldenExpectedBehavior.RETRIEVE and not raw_evidence_ids:
            raise ValueError("answerable golden case needs relevant evidence")
        if expected_behavior is GoldenExpectedBehavior.ABSTAIN and raw_evidence_ids:
            raise ValueError("abstention golden case cannot declare relevant evidence")
        evidence_ids = tuple(
            _require_string(value, "relevant_evidence_ids") for value in raw_evidence_ids
        )
        if len(set(evidence_ids)) != len(evidence_ids):
            raise ValueError("golden case evidence identifiers must be unique")
        case = GoldenCase(
            case_id=_require_string(raw_case.get("id"), "id"),
            query=_require_string(raw_case.get("query"), "query"),
            relevant_evidence_ids=evidence_ids,
            expected_behavior=expected_behavior,
        )
        if case.case_id in case_ids:
            raise ValueError("golden dataset case identifiers must be unique")
        case_ids.add(case.case_id)
        cases.append(case)
    return raw_dataset["dataset_version"], cases


def load_raw_wiki_documents(corpus_root: Path = _RAW_WIKI_ROOT) -> list[PublicDocument]:
    """Load a deterministic, label-independent snapshot of the raw_wiki corpus."""
    resolved_root = corpus_root.resolve()
    if not resolved_root.is_dir():
        raise ValueError("raw_wiki corpus root is unavailable")

    documents: list[PublicDocument] = []
    seen: set[str] = set()
    paths = sorted(
        resolved_root.rglob(f"*{_RAW_WIKI_MAIN_SUFFIX}"),
        key=lambda path: path.relative_to(resolved_root).as_posix(),
    )
    if not paths:
        raise ValueError("raw_wiki corpus contains no main revisions")
    for unresolved_path in paths:
        path = unresolved_path.resolve()
        if resolved_root not in path.parents or not path.is_file():
            raise ValueError("raw_wiki revision resolves outside the corpus root")
        metadata_path = path.with_suffix(".meta.json")
        try:
            raw_text = path.read_text(encoding="utf-8")
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError("unable to read a raw_wiki revision and metadata pair") from error
        if not isinstance(metadata, dict):
            raise ValueError("raw_wiki metadata must be a JSON object")
        page_id = metadata.get("page_id")
        revision_id = metadata.get("revision_id")
        if (
            not isinstance(page_id, int)
            or isinstance(page_id, bool)
            or page_id < 1
            or not isinstance(revision_id, int)
            or isinstance(revision_id, bool)
            or revision_id < 1
        ):
            raise ValueError("raw_wiki metadata requires positive page and revision IDs")
        if path.name != f"{page_id}{_RAW_WIKI_MAIN_SUFFIX}":
            raise ValueError("raw_wiki filename does not match its metadata page ID")
        normalized_text = " ".join(raw_text.split())[:_RAW_WIKI_TEXT_LIMIT]
        if not normalized_text:
            raise ValueError("raw_wiki revision text is empty")
        checksum = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()[:16]
        document_id = f"raw_wiki:{page_id}:{revision_id}:{checksum}:chunk:000"
        if document_id in seen:
            raise ValueError("raw_wiki corpus contains a duplicate evidence ID")
        seen.add(document_id)
        documents.append(
            PublicDocument(
                document_id=document_id,
                text=normalized_text,
                source_path=path.relative_to(resolved_root).as_posix(),
            )
        )
    return documents


def validate_relevant_evidence_ids(
    cases: Sequence[GoldenCase], documents: Sequence[PublicDocument]
) -> None:
    """Validate labels only after the independent corpus snapshot is complete."""
    available_ids = {document.document_id for document in documents}
    for case in cases:
        for evidence_id in case.relevant_evidence_ids:
            if _RAW_WIKI_EVIDENCE_ID.fullmatch(evidence_id) is None:
                raise ValueError("golden dataset contains an invalid raw_wiki evidence ID")
            if evidence_id not in available_ids:
                raise ValueError("golden dataset references a missing raw_wiki revision")


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
) -> int | None:
    ranks = [
        ranked_document_ids.index(document_id) + 1
        for document_id in relevant_evidence_ids
        if document_id in ranked_document_ids
    ]
    return min(ranks, default=None)


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


def _latency_summary(values: Sequence[float]) -> dict[str, float]:
    if not values:
        return {"min": 0.0, "mean": 0.0, "p50": 0.0, "p95": 0.0, "max": 0.0}
    return {
        "min": round(min(values), 3),
        "mean": round(sum(values) / len(values), 3),
        "p50": _percentile(values, 50),
        "p95": _percentile(values, 95),
        "max": round(max(values), 3),
    }


def _metric_summary(ranks: Sequence[int | None]) -> dict[str, float | str]:
    total = max(len(ranks), 1)
    return {
        "hit_at_1": round(sum(rank == 1 for rank in ranks) / total, 6),
        "hit_at_3": round(
            sum(rank is not None and rank <= 3 for rank in ranks) / total, 6
        ),
        "hit_at_5": round(
            sum(rank is not None and rank <= 5 for rank in ranks) / total, 6
        ),
        "mrr_at_10": round(
            sum((1 / rank) for rank in ranks if rank is not None and rank <= 10) / total,
            6,
        ),
        "context_precision": _CONTEXT_PRECISION_NOT_EVALUABLE,
    }


def _answerable_ranking_slice(
    cases: Sequence[GoldenCase], ranks: Sequence[int | None]
) -> list[int | None]:
    """Exclude abstentions from positive-evidence retrieval denominators."""
    if len(cases) != len(ranks):
        raise ValueError("case and rank counts must match")
    return [
        rank
        for case, rank in zip(cases, ranks, strict=True)
        if case.is_answerable
    ]


def _first_stage_retrieval_misses(
    cases: Sequence[GoldenCase], ranks: Sequence[int | None]
) -> list[str]:
    """Report only genuine positive-evidence misses."""
    if len(cases) != len(ranks):
        raise ValueError("case and rank counts must match")
    return [
        case.case_id
        for case, rank in zip(cases, ranks, strict=True)
        if case.is_answerable and rank is None
    ]


async def run_ablation(dataset_path: Path) -> dict[str, Any]:
    """Compare deterministic hybrid RRF with the configured Voyage reranker."""
    if settings.RERANKER_PROVIDER != "voyage" or not settings.VOYAGE_API_KEY:
        raise RuntimeError("RAG-05 ablation requires configured Voyage credentials")
    documents = load_raw_wiki_documents()
    dataset_version, cases = load_golden_dataset(dataset_path)
    validate_relevant_evidence_ids(cases, documents)
    document_by_id = {document.document_id: document for document in documents}
    embedder = FastEmbedAdapter()
    sparse_encoder = SparseTextEncoder()
    document_vectors = await embedder.embed_batch(
        [document.text for document in documents], prefix="passage: "
    )
    if len(document_vectors) != len(documents):
        raise RuntimeError("local embedding provider returned an incomplete document batch")

    baseline_case_ranks: list[int | None] = []
    voyage_rank_by_case: dict[str, int | None] = {}
    fallback_latencies_ms: list[float] = []
    total_latencies_ms: list[float] = []
    pacing_waits_ms: list[float] = []
    provider_http_latencies_ms: list[float] = []
    reranker_total_elapsed_ms: list[float] = []
    processed_tokens = 0
    reserved_provider_tokens = 0
    fallback_count = 0
    provider_calls = 0
    provider_success_count = 0
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
            query_vector = (await embedder.embed_batch([case.query], prefix="query: "))[0]
            baseline_order = _hybrid_rrf_order(
                documents, query_vector, document_vectors, case.query, sparse_encoder
            )[: settings.RERANKER_API_MAX_DOCUMENTS]
            fallback_latency_ms = (time.perf_counter() - retrieval_started) * 1000
            fallback_latencies_ms.append(fallback_latency_ms)
            baseline_rank = _first_relevant_rank(case.relevant_evidence_ids, baseline_order)
            baseline_case_ranks.append(baseline_rank)

            reranker_started = time.perf_counter()
            pacing_wait_ms = 0.0
            provider_http_latency_ms: float | None = None
            provider_token_estimate = 0
            try:
                ordered_documents = [
                    document_by_id[document_id]
                    for document_id in baseline_order
                ]
                provider_token_estimate = _conservative_provider_token_estimate(
                    case.query, ordered_documents
                )
                pacing_wait_ms = await pacer.reserve(provider_token_estimate)
                reserved_provider_tokens += provider_token_estimate
                provider_calls += 1
                scores = await reranker.rerank(
                    case.query, [document.text for document in ordered_documents]
                )
                provider_http_latency_ms = reranker.last_http_latency_ms
                if provider_http_latency_ms is None:
                    raise RuntimeError(
                        "successful reranker call did not publish provider HTTP latency"
                    )
                provider_http_latencies_ms.append(provider_http_latency_ms)
                voyage_order = [
                    document.document_id
                    for document, _ in sorted(
                        zip(ordered_documents, scores, strict=True),
                        key=lambda item: (-item[1], item[0].document_id),
                    )
                ]
                processed_tokens += TokenEstimator.estimate(case.query) * len(ordered_documents)
                processed_tokens += sum(
                    TokenEstimator.estimate(document.text)
                    for document in ordered_documents
                )
                final_rank = _first_relevant_rank(case.relevant_evidence_ids, voyage_order)
                reranker_mode = "voyage"
                failure_kind: str | None = None
                voyage_rank_by_case[case.case_id] = final_rank
                provider_success_count += 1
            except RerankerUnavailableError as error:
                failure_counts[error.failure_kind.value] += 1
                fallback_count += 1
                final_rank = baseline_rank
                reranker_mode = "deterministic_fallback"
                failure_kind = error.failure_kind.value

            reranker_elapsed_ms = (time.perf_counter() - reranker_started) * 1000
            total_elapsed_ms = (time.perf_counter() - retrieval_started) * 1000
            pacing_waits_ms.append(pacing_wait_ms)
            reranker_total_elapsed_ms.append(reranker_elapsed_ms)
            total_latencies_ms.append(total_elapsed_ms)
            case_results.append(
                {
                    "case_id": case.case_id,
                    "expected_behavior": case.expected_behavior.value,
                    "relevant_evidence_ids": case.relevant_evidence_ids,
                    "baseline_rank": baseline_rank,
                    "voyage_rank": final_rank if reranker_mode == "voyage" else None,
                    "fallback_rank": final_rank if reranker_mode != "voyage" else None,
                    "reranker_mode": reranker_mode,
                    "failure_kind": failure_kind,
                    "processed_token_estimate": provider_token_estimate,
                    "pacing_wait_ms": round(pacing_wait_ms, 3),
                    "provider_http_latency_ms": (
                        round(provider_http_latency_ms, 3)
                        if provider_http_latency_ms is not None
                        else None
                    ),
                    "reranker_total_elapsed_ms": round(reranker_elapsed_ms, 3),
                    "total_retrieval_latency_ms": round(total_elapsed_ms, 3),
                    "abstention_evaluation": (
                        None if case.is_answerable else _ABSTENTION_NOT_EVALUABLE
                    ),
                }
            )

    answerable_cases = [case for case in cases if case.is_answerable]
    abstention_cases = [case for case in cases if not case.is_answerable]
    fallback_ranks = _answerable_ranking_slice(cases, baseline_case_ranks)
    voyage_answerable_complete = all(
        case.case_id in voyage_rank_by_case for case in answerable_cases
    )
    voyage_ranks = [
        voyage_rank_by_case[case.case_id]
        for case in answerable_cases
        if case.case_id in voyage_rank_by_case
    ]
    successful_answerable_results = [
        result
        for result in case_results
        if result["expected_behavior"] == GoldenExpectedBehavior.RETRIEVE.value
        and result["reranker_mode"] == "voyage"
    ]
    improved_cases = [
        result["case_id"]
        for result in successful_answerable_results
        if result["voyage_rank"] is not None
        and (
            result["baseline_rank"] is None
            or result["voyage_rank"] < result["baseline_rank"]
        )
    ]
    unchanged_cases = [
        result["case_id"]
        for result in successful_answerable_results
        if result["voyage_rank"] == result["baseline_rank"]
    ]
    degraded_cases = [
        result["case_id"]
        for result in successful_answerable_results
        if result["baseline_rank"] is not None
        and (
            result["voyage_rank"] is None
            or result["voyage_rank"] > result["baseline_rank"]
        )
    ]
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
        "total_cases": len(cases),
        "answerable_cases": len(answerable_cases),
        "abstention_cases": len(abstention_cases),
        "abstention_evaluation": _ABSTENTION_NOT_EVALUABLE,
        "candidate_corpus_documents": len(documents),
        "candidate_document_representation": (
            "normalized raw_wiki main revision prefix, first 1200 characters"
        ),
        "retrieval_parity": {
            "mode": "offline_raw_wiki_page_snapshot",
            "production_equivalent": False,
            "gaps": [
                "production queries Qdrant named dense and BM25 sparse vectors with ACL filters",
                "production applies score thresholds and bounded per-branch candidate limits",
                "production hydrates versioned parent/child records after candidate retrieval",
            ],
        },
        "baseline_deterministic_hybrid_rrf": _metric_summary(fallback_ranks),
        "voyage_rerank": (
            _metric_summary(voyage_ranks) if voyage_answerable_complete else None
        ),
        "answerable_case_outcomes": {
            "improved": improved_cases,
            "unchanged": unchanged_cases,
            "degraded": degraded_cases,
        },
        "provider_http_latency_ms": _latency_summary(provider_http_latencies_ms),
        "pacing_wait_ms": {
            "total": round(sum(pacing_waits_ms), 3),
            "mean": round(sum(pacing_waits_ms) / len(pacing_waits_ms), 3),
            "p50": _percentile(pacing_waits_ms, 50),
            "p95": _percentile(pacing_waits_ms, 95),
            "paced_case_count": sum(wait > 0 for wait in pacing_waits_ms),
        },
        "reranker_total_elapsed_ms": _latency_summary(reranker_total_elapsed_ms),
        "total_retrieval_latency_ms": {
            "baseline": _latency_summary(fallback_latencies_ms),
            "with_reranker": _latency_summary(total_latencies_ms),
        },
        "processed_tokens": processed_tokens,
        "reserved_provider_tokens": reserved_provider_tokens,
        "estimated_cost_usd": round(estimated_cost_usd, 8),
        "provider_calls": provider_calls,
        "provider_success_count": provider_success_count,
        "provider_failure_counts": failure_counts,
        "timeout_rate": round(failure_counts["timeout"] / len(cases), 6),
        "rate_limit_rate": round(failure_counts["rate_limit"] / len(cases), 6),
        "error_rate": round(sum(failure_counts.values()) / len(cases), 6),
        "fallback_rate": round(fallback_count / len(cases), 6),
        "quality_comparison_valid": voyage_answerable_complete,
        "privacy_policy_rejection_count": 0,
        "first_stage_retrieval_misses": _first_stage_retrieval_misses(
            cases, baseline_case_ranks
        ),
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
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    serialized = json.dumps(
        asyncio.run(run_ablation(args.dataset)), ensure_ascii=False, indent=2
    )
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)


if __name__ == "__main__":
    main()
