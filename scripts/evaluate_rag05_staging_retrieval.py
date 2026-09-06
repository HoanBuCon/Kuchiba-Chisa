"""Evaluate RAG-05 through an isolated Qdrant and production lore retrieval path.

The command is deliberately restricted to the disposable test endpoints. It
creates uniquely named physical collections, never publishes aliases, and
records the before/after Qdrant namespace so active data cannot be mistaken for
evaluation data.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import tempfile
import time
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from qdrant_client import AsyncQdrantClient

from app.application.ingestion.stages.batch_embedding_stage import (
    BatchEmbeddingInput,
    BatchEmbeddingStage,
)
from app.application.ingestion.stages.metadata_enricher_stage import (
    MetadataEnricherInput,
    MetadataEnricherStage,
)
from app.application.ingestion.stages.parent_builder_stage import (
    ParentBuilderInput,
    ParentBuilderStage,
)
from app.application.ingestion.stages.parser_stage import ParserInput, ParserStage
from app.application.ingestion.stages.qdrant_upsert_stage import (
    QdrantUpsertInput,
    QdrantUpsertStage,
)
from app.application.ingestion.stages.semantic_chunk_builder_stage import (
    SemanticChunkBuilderInput,
    SemanticChunkBuilderStage,
)
from app.application.ingestion.stages.validation_stage import (
    ValidationInput,
    ValidationStage,
)
from app.config.settings import settings
from app.domain.entities.chunk_models import ProcessingChunk
from app.domain.entities.lore import LoreParent
from app.domain.entities.wiki import DownloadedPage
from app.domain.models.corpus_safety_exception import CorpusSafetyProvenance
from app.domain.models.evidence import EvidenceAccess
from app.domain.models.ingestion_source import (
    IngestionSource,
    SourceAccessPolicy,
    SourceStatus,
    SourceTrustTier,
)
from app.domain.services.guardrails import CorpusSafetyGate
from app.domain.services.rag.lore_fusion import fuse_lore_collection_buckets
from app.domain.services.rag.retriever_lore import LoreRetriever
from app.domain.tuning.rag import RAGTuning
from app.infrastructure.database.engine import AsyncSessionFactory
from app.infrastructure.database.repositories.ingestion_source import IngestionSourceRepository
from app.infrastructure.database.repositories.lore_parent import LoreParentRepository
from app.infrastructure.embeddings.fastembed_adapter import FastEmbedAdapter
from app.infrastructure.ingestion.corpus_safety_exceptions import (
    load_corpus_safety_exception_manifest,
)
from app.infrastructure.ingestion.parsers.classifier import classify_page_type
from app.infrastructure.ingestion.raw_storage import FileRawStorage
from app.infrastructure.ingestion.storage.qdrant_sync import map_page_type_to_collection
from app.infrastructure.vector.qdrant.qdrant_service import (
    COLLECTION_CHARACTER_LORE,
    COLLECTION_STORY_LORE,
    COLLECTION_WORLD_LORE,
    QdrantService,
)
from scripts.benchmark_rag05_reranker import (
    GoldenCase,
    _answerable_ranking_slice,
    _first_relevant_rank,
    _first_stage_retrieval_misses,
    _hybrid_rrf_order,
    _metric_summary,
    load_golden_dataset,
    load_raw_wiki_documents,
    validate_relevant_evidence_ids,
)
from scripts.validate_rag05_raw_wiki_golden import _content_fingerprint

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data/evaluations/drafts/rag05_raw_wiki_golden_v1.json"
VALIDATION = ROOT / "data/evaluations/drafts/rag05_raw_wiki_golden_v1.validation.json"
SAFETY_EXCEPTIONS = (
    ROOT / "data/evaluations/approvals/rag05_corpus_safety_exceptions_v1.json"
)
RAW_WIKI = ROOT / "data/raw_wiki"
JSON_REPORT = ROOT / "reports/RAG05_Staging_Qdrant_Retrieval_Evaluation.json"
MARKDOWN_REPORT = ROOT / "reports/RAG05_Staging_Qdrant_Retrieval_Evaluation.md"
LOGICAL_COLLECTIONS = (
    COLLECTION_CHARACTER_LORE,
    COLLECTION_WORLD_LORE,
    COLLECTION_STORY_LORE,
)
EVALUATION_SOURCE_ID = uuid.UUID("543b2265-40c0-5e2c-9bb5-f941e7d1094a")


class EvaluationSafetyError(RuntimeError):
    """Raised before an evaluation could affect a non-isolated resource."""


class _EventSink:
    async def create_job(self, stage: str, worker: str) -> uuid.UUID:
        del stage, worker
        return uuid.uuid4()

    async def update_job_status(
        self, job_id: uuid.UUID, status: str, error: str | None = None
    ) -> None:
        del job_id, status, error
        return None

    async def log_event(
        self, job_id: uuid.UUID, event_type: str, details: dict[str, Any]
    ) -> None:
        del job_id, event_type, details
        return None


@dataclass(frozen=True)
class RawRevision:
    page_id: int
    revision_id: int
    title: str
    categories: tuple[str, ...]
    raw_text: str
    evidence_id: str
    source_path: str


def require_isolated_endpoints(qdrant_url: str, database_url: str) -> None:
    """Fail closed unless both stores are the repository's disposable test stack."""

    qdrant = urlparse(qdrant_url)
    if qdrant.scheme != "http" or qdrant.hostname not in {"localhost", "127.0.0.1"}:
        raise EvaluationSafetyError("Qdrant evaluation requires the localhost test endpoint")
    if qdrant.port != 16333:
        raise EvaluationSafetyError("Qdrant evaluation requires port 16333")

    database = urlparse(database_url.replace("postgresql+asyncpg", "postgresql", 1))
    if database.hostname not in {"localhost", "127.0.0.1"} or database.port != 55432:
        raise EvaluationSafetyError("parent hydration requires the localhost test database")
    if database.path != "/chisa_test":
        raise EvaluationSafetyError("parent hydration requires database chisa_test")


def _load_revisions() -> list[RawRevision]:
    documents = load_raw_wiki_documents(RAW_WIKI)
    revisions: list[RawRevision] = []
    for document in documents:
        if document.source_path is None:
            raise ValueError("raw_wiki document is missing its auditable source path")
        path = RAW_WIKI / document.source_path
        metadata = json.loads(path.with_suffix(".meta.json").read_text(encoding="utf-8"))
        revisions.append(
            RawRevision(
                page_id=int(metadata["page_id"]),
                revision_id=int(metadata["revision_id"]),
                title=str(metadata["title"]),
                categories=tuple(str(value) for value in metadata.get("categories", [])),
                raw_text=path.read_text(encoding="utf-8"),
                evidence_id=document.document_id,
                source_path=document.source_path,
            )
        )
    return revisions


def _pipeline_fingerprint() -> str:
    paths = (
        "app/application/ingestion/stages/parser_stage.py",
        "app/application/ingestion/stages/parent_builder_stage.py",
        "app/application/ingestion/stages/semantic_chunk_builder_stage.py",
        "app/application/ingestion/stages/metadata_enricher_stage.py",
        "app/application/ingestion/stages/validation_stage.py",
        "app/application/ingestion/stages/batch_embedding_stage.py",
        "app/infrastructure/vector/qdrant/qdrant_service.py",
        "app/domain/services/rag/retriever_lore.py",
        "app/domain/services/rag/lore_fusion.py",
        "app/domain/tuning/rag.py",
    )
    digest = hashlib.sha256()
    for relative in paths:
        digest.update(relative.encode("utf-8"))
        digest.update((ROOT / relative).read_bytes())
    return digest.hexdigest()


async def _build_processing_corpus(
    revisions: list[RawRevision], corpus_version: str
) -> tuple[list[LoreParent], list[ProcessingChunk]]:
    event_sink = _EventSink()
    job_id = uuid.uuid5(uuid.NAMESPACE_URL, f"rag05-staging:{corpus_version}")
    revision_by_page = {revision.page_id: revision for revision in revisions}

    with tempfile.TemporaryDirectory(prefix="rag05-raw-storage-") as temp_root:
        storage = FileRawStorage(Path(temp_root))
        downloads: list[DownloadedPage] = []
        for revision in revisions:
            uri = await storage.save_raw_page(
                revision.title, revision.page_id, revision.raw_text
            )
            downloads.append(
                DownloadedPage(
                    page_id=revision.page_id,
                    title=revision.title,
                    revision_id=revision.revision_id,
                    file_path=uri,
                )
            )
        parsed_result = await ParserStage(storage, event_sink).execute(
            job_id, ParserInput(downloaded_pages=downloads)
        )

    if len(parsed_result.output) != len(revisions):
        raise RuntimeError("production parser did not acknowledge every raw_wiki revision")

    parents: list[LoreParent] = []
    page_type_by_id: dict[int, str] = {}
    for page in parsed_result.output:
        revision = revision_by_page[page.page_id]
        classification = classify_page_type(
            categories=list(revision.categories),
            title=page.title,
            section_titles=[section.title for section in page.document.sections],
            page_id=page.page_id,
        )
        page_type_by_id[page.page_id] = classification.page_type.value
        result = await ParentBuilderStage(event_sink).execute(
            job_id,
            ParentBuilderInput(
                parsed_page=page,
                corpus_version=corpus_version,
                source_id=EVALUATION_SOURCE_ID,
                access=EvidenceAccess(scope="public"),
            ),
        )
        parents.extend(result.output)

    chunk_result = await SemanticChunkBuilderStage(event_sink).execute(
        job_id, SemanticChunkBuilderInput(parents=parents)
    )
    for chunk in chunk_result.output:
        revision = revision_by_page[chunk.page_id]
        chunk.metadata.update(
            {
                "canonical_name": revision.title,
                "entity_type": page_type_by_id[chunk.page_id],
                "page_type": page_type_by_id[chunk.page_id],
                "source_type": "raw_wiki",
            }
        )
    enriched = await MetadataEnricherStage(event_sink).execute(
        job_id, MetadataEnricherInput(chunks=chunk_result.output)
    )
    validated = await ValidationStage(event_sink).execute(
        job_id, ValidationInput(chunks=enriched.output)
    )
    if len(validated.output) != len(enriched.output):
        raise RuntimeError("production validation rejected one or more corpus chunks")
    return parents, validated.output


async def _namespace_snapshot(client: AsyncQdrantClient) -> dict[str, Any]:
    collections = await client.get_collections()
    aliases = await client.get_aliases()
    return {
        "collections": sorted(item.name for item in collections.collections),
        "aliases": sorted(
            (
                {"alias_name": item.alias_name, "collection_name": item.collection_name}
                for item in aliases.aliases
            ),
            key=lambda item: item["alias_name"],
        ),
    }


def assess_namespace_safety(
    before: dict[str, Any],
    after: dict[str, Any],
    physical_collections: dict[str, str],
) -> tuple[bool, list[str]]:
    """Prove that the run only added its named physical collections."""

    aliases_unchanged = before["aliases"] == after["aliases"]
    expected_after = set(before["collections"]) | set(physical_collections.values())
    unexpected_changes = sorted(set(after["collections"]).symmetric_difference(expected_after))
    return aliases_unchanged, unexpected_changes


def _rank(case: GoldenCase, ranked_ids: list[str]) -> int | None:
    return _first_relevant_rank(case.relevant_evidence_ids, ranked_ids)


def _page_evidence_map(revisions: list[RawRevision]) -> dict[tuple[int, int], str]:
    return {
        (revision.page_id, revision.revision_id): revision.evidence_id
        for revision in revisions
    }


def validate_corpus_safety(
    chunks: list[ProcessingChunk], gate: CorpusSafetyGate | None = None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return sanitized quarantine receipts before any staging side effect."""

    safety_gate = gate or CorpusSafetyGate()
    blocked: list[dict[str, Any]] = []
    approved: list[dict[str, Any]] = []
    for chunk in chunks:
        decision = safety_gate.inspect(
            text=chunk.text_content,
            source_id=f"page:{chunk.page_id}:chunk:{chunk.chunk_id}",
            checksum=chunk.chunk_hash,
            provenance=(
                CorpusSafetyProvenance(
                    source_id=str(chunk.source_id),
                    corpus_version=chunk.corpus_version,
                    page_id=chunk.page_id,
                    revision_id=chunk.revision_id,
                    chunk_id=str(chunk.chunk_id),
                )
                if chunk.source_id is not None and chunk.corpus_version is not None
                else None
            ),
        )
        if decision.quarantined:
            blocked.append(
                {
                    "page_id": chunk.page_id,
                    "revision_id": chunk.revision_id,
                    "chunk_id": str(chunk.chunk_id),
                    "chunk_hash": chunk.chunk_hash,
                    "rule_id": decision.rule_id,
                    "fingerprint": decision.fingerprint,
                }
            )
        if decision.exception_applied:
            approved.append(
                {
                    "page_id": chunk.page_id,
                    "revision_id": chunk.revision_id,
                    "chunk_id": str(chunk.chunk_id),
                    "chunk_hash": chunk.chunk_hash,
                    "rule_id": decision.rule_id,
                    "finding_fingerprint": decision.fingerprint,
                    "exception_id": decision.exception_id,
                    "approved_by": decision.approved_by,
                    "approved_at": decision.approved_at,
                }
            )
    return blocked, approved


def _mapped_evidence_ids(
    results: list[tuple[str, float, dict[str, Any]]],
    evidence_by_revision: dict[tuple[int, int], str],
) -> list[str]:
    mapped: list[str] = []
    for _, _, metadata in results:
        key = (int(metadata["page_id"]), int(metadata["revision_id"]))
        try:
            mapped.append(evidence_by_revision[key])
        except KeyError as error:
            raise RuntimeError(
                "retrieved chunk cannot map to approved raw_wiki evidence"
            ) from error
    return mapped


async def _persist_source_and_parents(
    parents: list[LoreParent], raw_dataset: dict[str, Any]
) -> None:
    async with AsyncSessionFactory() as session:
        source_repository = IngestionSourceRepository(session)
        existing_source = await source_repository.get_source(EVALUATION_SOURCE_ID)
        corpus_checksum = str(raw_dataset["corpus_version"]).removeprefix(
            "raw-wiki-sha256:"
        )
        approval = raw_dataset["approval"]
        approved_at = datetime.fromisoformat(
            str(approval["approved_at"]).replace("Z", "+00:00")
        )
        source = IngestionSource(
            source_id=EVALUATION_SOURCE_ID,
            uri="https://wutheringwaves.fandom.com/wiki/Wuthering_Waves_Wiki",
            owner_id=str(approval["approved_by"]),
            license_identifier="project-approved-evaluation-snapshot",
            access_policy=SourceAccessPolicy(access=EvidenceAccess(scope="public")),
            trust_tier=SourceTrustTier.REVIEWED,
            checksum=corpus_checksum,
            crawl_schedule="0 0 1 1 *",
            status=SourceStatus.APPROVED,
            approved_by=str(approval["approved_by"]),
            approved_at=approved_at,
        )
        if existing_source is not None and existing_source != source:
            raise EvaluationSafetyError("isolated source registry contains conflicting data")
        if existing_source is None:
            await source_repository.save_source(source)
        repository = LoreParentRepository(session)
        for parent in parents:
            await repository.save_parent(parent)
        await session.commit()


async def _index_chunks(
    service: QdrantService,
    chunks: list[ProcessingChunk],
    physical_collections: dict[str, str],
    embedder: FastEmbedAdapter,
    corpus_safety_gate: CorpusSafetyGate,
) -> dict[str, int]:
    event_sink = _EventSink()
    job_id = uuid.uuid4()
    embedded = await BatchEmbeddingStage(embedder, event_sink).execute(
        job_id, BatchEmbeddingInput(chunks=chunks)
    )
    if embedded.metrics.items_failed or embedded.metrics.items_processed != len(chunks):
        raise RuntimeError("production embedding stage did not embed every valid chunk")

    counts: dict[str, int] = {}
    for logical_collection in LOGICAL_COLLECTIONS:
        partition = [
            chunk
            for chunk in embedded.output
            if map_page_type_to_collection(str(chunk.metadata["page_type"]))
            == logical_collection
        ]
        result = await QdrantUpsertStage(
            service, event_sink, corpus_safety_gate=corpus_safety_gate
        ).execute(
            job_id,
            QdrantUpsertInput(
                chunks=partition,
                staging_collection=physical_collections[logical_collection],
            ),
        )
        counts[logical_collection] = result.metrics.items_processed
    return counts


async def _evaluate(
    *,
    cases: list[GoldenCase],
    revisions: list[RawRevision],
    service: QdrantService,
    physical_collections: dict[str, str],
    embedder: FastEmbedAdapter,
    parents: list[LoreParent],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    documents = load_raw_wiki_documents(RAW_WIKI)
    document_vectors = await embedder.embed_batch(
        [document.text for document in documents], prefix="passage: "
    )
    sparse_encoder = service._sparse_encoder
    evidence_by_revision = _page_evidence_map(revisions)
    parent_by_id = {str(parent.id): parent for parent in parents}
    retriever = LoreRetriever(
        vector_store=service,
        lore_parent_repo_factory=LoreParentRepository,
    )
    ranks: list[int | None] = []
    offline_ranks: list[int | None] = []
    case_results: list[dict[str, Any]] = []
    hydration_mismatches: list[str] = []
    retrieval_modes: Counter[str] = Counter()
    query_latencies_ms: list[float] = []

    async with AsyncSessionFactory() as session:
        for case in cases:
            query_started = time.perf_counter()
            query_vector = (
                await embedder.embed_batch([case.query], prefix="query: ")
            )[0]
            buckets: dict[str, list[tuple[str, float, dict[str, Any]]]] = {}
            for logical_collection in LOGICAL_COLLECTIONS:
                buckets[logical_collection] = await retriever.retrieve_lore_parent_child(
                    collection=physical_collections[logical_collection],
                    query_vector=query_vector,
                    session=session,
                    query_text=case.query,
                    top_k=RAGTuning.TOP_K,
                    score_threshold=RAGTuning.SCORE_THRESHOLD,
                    enable_cross_encoder_rerank=False,
                )
            fused = fuse_lore_collection_buckets(buckets)[: RAGTuning.TOP_K]
            staging_ids = _mapped_evidence_ids(fused, evidence_by_revision)
            staging_rank = _rank(case, staging_ids) if case.is_answerable else None
            ranks.append(staging_rank)
            query_latencies_ms.append((time.perf_counter() - query_started) * 1000)

            for _, _, metadata in fused:
                retrieval_modes[str(metadata.get("retrieval_mode"))] += 1
                parent_id = str(metadata.get("parent_id", ""))
                parent = parent_by_id.get(parent_id)
                if (
                    parent is None
                    or parent.corpus_version is None
                    or parent.revision_id != int(metadata["revision_id"])
                ):
                    hydration_mismatches.append(case.case_id)

            offline_ids = _hybrid_rrf_order(
                documents,
                query_vector,
                document_vectors,
                case.query,
                sparse_encoder,
            )[: RAGTuning.TOP_K]
            offline_rank = _rank(case, offline_ids) if case.is_answerable else None
            offline_ranks.append(offline_rank)
            case_results.append(
                {
                    "case_id": case.case_id,
                    "expected_behavior": case.expected_behavior.value,
                    "relevant_evidence_ids": list(case.relevant_evidence_ids),
                    "offline_top_k_evidence_ids": offline_ids,
                    "staging_top_k_evidence_ids": staging_ids,
                    "offline_rank": offline_rank,
                    "staging_rank": staging_rank,
                    "identical_top_k": offline_ids == staging_ids,
                    "candidate_set_added": sorted(set(staging_ids) - set(offline_ids)),
                    "candidate_set_removed": sorted(set(offline_ids) - set(staging_ids)),
                    "query_latency_ms": round(query_latencies_ms[-1], 3),
                    "abstention_evaluation": (
                        None
                        if case.is_answerable
                        else "not_evaluable_at_retrieval_stage"
                    ),
                }
            )

    answerable_ranks = _answerable_ranking_slice(cases, ranks)
    answerable_offline_ranks = _answerable_ranking_slice(cases, offline_ranks)
    comparison = {
        "identical_top_k_cases": sum(item["identical_top_k"] for item in case_results),
        "ranking_changed_cases": [
            item["case_id"]
            for item in case_results
            if item["offline_rank"] != item["staging_rank"]
        ],
        "newly_missed_cases": [
            case.case_id
            for case, offline_rank, staging_rank in zip(
                cases, offline_ranks, ranks, strict=True
            )
            if case.is_answerable and offline_rank is not None and staging_rank is None
        ],
        "recovered_cases": [
            case.case_id
            for case, offline_rank, staging_rank in zip(
                cases, offline_ranks, ranks, strict=True
            )
            if case.is_answerable and offline_rank is None and staging_rank is not None
        ],
        "offline_metrics": _metric_summary(answerable_offline_ranks),
        "staging_metrics": _metric_summary(answerable_ranks),
        "staging_first_stage_misses": _first_stage_retrieval_misses(cases, ranks),
        "offline_first_stage_misses": _first_stage_retrieval_misses(cases, offline_ranks),
        "hydration_mismatches": sorted(set(hydration_mismatches)),
        "retrieval_modes": dict(sorted(retrieval_modes.items())),
        "query_latency_ms": _latency_summary(query_latencies_ms),
    }
    return case_results, comparison


def _latency_summary(values: list[float]) -> dict[str, float]:
    if not values:
        return {"mean": 0.0, "p50": 0.0, "p95": 0.0, "max": 0.0}
    ordered = sorted(values)

    def percentile(fraction: float) -> float:
        return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * fraction))]

    return {
        "mean": round(sum(values) / len(values), 3),
        "p50": round(percentile(0.50), 3),
        "p95": round(percentile(0.95), 3),
        "max": round(max(values), 3),
    }


def _render_markdown(report: dict[str, Any]) -> str:
    metrics = report["quality"]["staging_metrics"]
    comparison = report["comparison"]
    return "\n".join(
        [
            "# RAG-05 Isolated Staging Qdrant Retrieval Evaluation",
            "",
            f"- Executed at: `{report['executed_at']}`",
            f"- Dataset: `{report['dataset_version']}`",
            f"- Approved content fingerprint: `{report['approved_content_sha256']}`",
            f"- Corpus version: `{report['corpus_version']}`",
            f"- Production equivalent: `{str(report['production_equivalent']).lower()}`",
            f"- Qdrant endpoint: `{report['environment']['qdrant_url']}`",
            "- Collections: `"
            f"{json.dumps(report['index']['physical_collections'], sort_keys=True)}`",
            "",
            "## Answerable-slice quality",
            "",
            f"- Cases: `{report['answerable_cases']}`",
            f"- Hit@1: `{metrics['hit_at_1']}`",
            f"- Hit@3: `{metrics['hit_at_3']}`",
            f"- Hit@5: `{metrics['hit_at_5']}`",
            f"- MRR@10: `{metrics['mrr_at_10']}`",
            f"- First-stage misses: `{len(report['quality']['staging_first_stage_misses'])}`",
            "- Context precision: `not_evaluable_label_incomplete`",
            "- Abstention evaluation: `not_evaluable_at_retrieval_stage`",
            "",
            "## Offline comparison",
            "",
            f"- Identical top-k: `{comparison['identical_top_k_cases']}/{report['total_cases']}`",
            f"- Ranking changes: `{len(comparison['ranking_changed_cases'])}`",
            f"- Newly missed: `{len(comparison['newly_missed_cases'])}`",
            f"- Recovered: `{len(comparison['recovered_cases'])}`",
            "- Material semantic differences: Qdrant named dense/BM25 search, public ACL filter, "
            "configured score threshold/candidate budgets, production parent hydration, and "
            "production cross-collection fusion are exercised only by this staging run.",
            "",
            "## Safety and parity",
            "",
            f"- Alias namespace unchanged: `{str(report['safety']['aliases_unchanged']).lower()}`",
            "- Unexpected collection changes: "
            f"`{report['safety']['unexpected_collection_changes']}`",
            f"- Parent hydration mismatches: `{len(report['quality']['hydration_mismatches'])}`",
            "- Retrieval modes: "
            f"`{json.dumps(report['quality']['retrieval_modes'], sort_keys=True)}`",
            "- Remote reranker: disabled; no provider request was made.",
            "- Active corpus/index aliases were not created, changed, or deleted.",
            "",
            "Per-case evidence and candidate differences are recorded in the JSON artifact.",
        ]
    )


async def run() -> dict[str, Any]:
    require_isolated_endpoints(settings.QDRANT_URL, settings.DATABASE_URL)
    raw_dataset = json.loads(DATASET.read_text(encoding="utf-8"))
    validation = json.loads(VALIDATION.read_text(encoding="utf-8"))
    approved_fingerprint = _content_fingerprint(raw_dataset)
    if approved_fingerprint != validation.get("approved_content_sha256"):
        raise RuntimeError("approved golden-set fingerprint does not match validation record")

    dataset_version, cases = load_golden_dataset(DATASET)
    revisions = _load_revisions()
    documents = load_raw_wiki_documents(RAW_WIKI)
    validate_relevant_evidence_ids(cases, documents)
    corpus_version = str(raw_dataset["corpus_version"])
    pipeline_fingerprint = _pipeline_fingerprint()
    run_component = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    staging_version = f"rag05eval_{approved_fingerprint[:10]}_{run_component}"

    exception_manifest = load_corpus_safety_exception_manifest(SAFETY_EXCEPTIONS)
    corpus_safety_gate = CorpusSafetyGate(
        approved_exceptions=exception_manifest.exceptions
    )
    client = AsyncQdrantClient(url=settings.QDRANT_URL, timeout=30)
    service = QdrantService(client=client, corpus_safety_gate=corpus_safety_gate)
    before = await _namespace_snapshot(client)
    physical_collections = {
        logical: f"{logical}__{staging_version}" for logical in LOGICAL_COLLECTIONS
    }
    if set(physical_collections.values()) & set(before["collections"]):
        raise EvaluationSafetyError("unique staging collection already exists")
    if any(
        alias["collection_name"] in physical_collections.values()
        for alias in before["aliases"]
    ):
        raise EvaluationSafetyError("an alias targets a proposed evaluation collection")

    parents, chunks = await _build_processing_corpus(revisions, corpus_version)
    quarantined, approved_exceptions = validate_corpus_safety(
        chunks, corpus_safety_gate
    )
    if quarantined:
        raise EvaluationSafetyError(
            "production corpus safety gate requires curator review: "
            + json.dumps(quarantined, sort_keys=True)
        )
    if len(approved_exceptions) != len(exception_manifest.exceptions):
        raise EvaluationSafetyError(
            "approved corpus safety exception did not match its immutable chunk"
        )
    await _persist_source_and_parents(parents, raw_dataset)
    for logical, physical in physical_collections.items():
        created = await service.prepare_versioned_collection(
            logical, staging_version, settings.QDRANT_EMBEDDING_DIM
        )
        if created != physical:
            raise EvaluationSafetyError("versioned collection identity changed unexpectedly")

    embedder = FastEmbedAdapter()
    indexed_counts = await _index_chunks(
        service,
        chunks,
        physical_collections,
        embedder,
        corpus_safety_gate,
    )
    for logical, expected in indexed_counts.items():
        actual = await client.count(
            collection_name=physical_collections[logical], exact=True
        )
        if actual.count != expected:
            raise RuntimeError("Qdrant exact point count does not match acknowledged writes")

    case_results, quality = await _evaluate(
        cases=cases,
        revisions=revisions,
        service=service,
        physical_collections=physical_collections,
        embedder=embedder,
        parents=parents,
    )
    after = await _namespace_snapshot(client)
    await client.close()

    aliases_unchanged, unexpected_changes = assess_namespace_safety(
        before, after, physical_collections
    )
    retrieval_mode_gap = any(
        mode not in {"hybrid_rrf"} for mode in quality["retrieval_modes"]
    )
    production_equivalent = bool(
        aliases_unchanged
        and not unexpected_changes
        and not quality["hydration_mismatches"]
        and not retrieval_mode_gap
    )
    report = {
        "task": "RAG-05 production-equivalent first-stage retrieval evaluation",
        "executed_at": datetime.now(UTC).isoformat(),
        "dataset_version": dataset_version,
        "approved_content_sha256": approved_fingerprint,
        "corpus_version": corpus_version,
        "pipeline_fingerprint": pipeline_fingerprint,
        "total_cases": len(cases),
        "answerable_cases": sum(case.is_answerable for case in cases),
        "abstention_cases": sum(not case.is_answerable for case in cases),
        "abstention_evaluation": "not_evaluable_at_retrieval_stage",
        "context_precision": "not_evaluable_label_incomplete",
        "production_equivalent": production_equivalent,
        "environment": {
            "qdrant_url": settings.QDRANT_URL,
            "database": "localhost:55432/chisa_test",
        },
        "configuration": {
            "embedding_model": settings.EMBEDDING_MODEL,
            "embedding_dimension": settings.QDRANT_EMBEDDING_DIM,
            "document_embedding_path": "BatchEmbeddingStage current production default",
            "query_embedding_prefix": "query: ",
            "top_k": RAGTuning.TOP_K,
            "score_threshold": RAGTuning.SCORE_THRESHOLD,
            "candidate_multiplier": RAGTuning.HYBRID_CANDIDATE_MULTIPLIER,
            "rrf_k": RAGTuning.HYBRID_RRF_K,
            "dense_weight": RAGTuning.HYBRID_DENSE_WEIGHT,
            "sparse_weight": RAGTuning.HYBRID_SPARSE_WEIGHT,
            "reranker_enabled": False,
            "access_scope": "public",
        },
        "corpus": {
            "raw_revisions": len(revisions),
            "parents": len(parents),
            "chunks": len(chunks),
            "identity": "raw_wiki page/revision/checksum mapped from retrieved chunk payload",
            "parent_child": "production parent IDs, persisted parent rows, windowed hydration",
        },
        "index": {
            "staging_version": staging_version,
            "physical_collections": physical_collections,
            "indexed_counts": indexed_counts,
            "aliases_published": False,
        },
        "quality": quality,
        "comparison": {
            key: quality[key]
            for key in (
                "identical_top_k_cases",
                "ranking_changed_cases",
                "newly_missed_cases",
                "recovered_cases",
                "offline_metrics",
            )
        },
        "safety": {
            "namespace_before": before,
            "namespace_after": after,
            "aliases_unchanged": aliases_unchanged,
            "unexpected_collection_changes": unexpected_changes,
            "active_alias_mutations": 0,
        },
        "case_results": case_results,
        "parity_gaps": (
            []
            if production_equivalent
            else {
                "aliases_changed": not aliases_unchanged,
                "unexpected_collection_changes": unexpected_changes,
                "hydration_mismatches": quality["hydration_mismatches"],
                "non_hybrid_modes": dict(quality["retrieval_modes"]),
            }
        ),
    }
    JSON_REPORT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    MARKDOWN_REPORT.write_text(_render_markdown(report), encoding="utf-8")
    return report


async def verify_curator_exception() -> dict[str, Any]:
    """Build the immutable corpus and prove only the approved finding is released."""

    raw_dataset = json.loads(DATASET.read_text(encoding="utf-8"))
    revisions = _load_revisions()
    _, chunks = await _build_processing_corpus(
        revisions, str(raw_dataset["corpus_version"])
    )
    manifest = load_corpus_safety_exception_manifest(SAFETY_EXCEPTIONS)
    original_findings, _ = validate_corpus_safety(chunks)
    blocked, approved = validate_corpus_safety(
        chunks, CorpusSafetyGate(approved_exceptions=manifest.exceptions)
    )
    expected_exception_ids = {
        exception.exception_id for exception in manifest.exceptions
    }
    applied_exception_ids = {str(record["exception_id"]) for record in approved}
    if blocked:
        raise EvaluationSafetyError(
            "an independent corpus safety finding still requires human review: "
            + json.dumps(blocked, sort_keys=True)
        )
    if applied_exception_ids != expected_exception_ids:
        raise EvaluationSafetyError(
            "approved corpus safety exception did not match its immutable chunk"
        )
    return {
        "corpus_version": raw_dataset["corpus_version"],
        "raw_revisions": len(revisions),
        "generated_chunks": len(chunks),
        "original_findings": original_findings,
        "approved_exceptions": approved,
        "remaining_blocked_findings": blocked,
        "qdrant_mutations": 0,
        "postgresql_mutations": 0,
        "alias_mutations": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        required=True,
        choices=["isolated-staging", "verify-curator-exception"],
    )
    arguments = parser.parse_args()
    if arguments.mode == "verify-curator-exception":
        print(json.dumps(asyncio.run(verify_curator_exception()), indent=2))
        return
    report = asyncio.run(run())
    print(
        json.dumps(
            {
                "production_equivalent": report["production_equivalent"],
                "quality": report["quality"]["staging_metrics"],
                "first_stage_misses": report["quality"][
                    "staging_first_stage_misses"
                ],
                "aliases_unchanged": report["safety"]["aliases_unchanged"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
