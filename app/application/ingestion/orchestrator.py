"""Canonical application-level orchestration for a staged corpus ingestion run."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.application.ingestion.errors import IngestionStageError
from app.application.ingestion.stages.batch_embedding_stage import (
    BatchEmbeddingInput,
    BatchEmbeddingStage,
)
from app.application.ingestion.stages.downloader_stage import DownloaderInput, DownloaderStage
from app.application.ingestion.stages.entity_resolver_stage import (
    EntityResolverInput,
    EntityResolverStage,
)
from app.application.ingestion.stages.incremental_router_stage import (
    IncrementalRouterInput,
    IncrementalRouterStage,
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
from app.application.ingestion.stages.validation_stage import ValidationInput, ValidationStage
from app.domain.entities.lore import LoreParent
from app.domain.interfaces.pipeline import PipelineResult
from app.domain.interfaces.repositories import (
    ICorpusReleaseRepository,
    ILoreParentRepository,
    IPipelineJobRepository,
)
from app.domain.models.corpus_manifest import (
    LoreManifestRow,
    ParentManifestRow,
    lore_manifest_checksum,
    parent_manifest_checksum,
)
from app.domain.models.corpus_release import (
    CorpusRelease,
    CorpusReleaseAuditAction,
    CorpusReleaseAuditEvent,
)
from app.domain.models.evidence import EvidenceAccess
from app.domain.models.lore_collections import (
    corpus_version_from_staging_collection,
    logical_collection_from_staging_collection,
    validate_lore_staging_collection,
)

_INGESTION_SERVICE_ACTOR_ID = "service:ingestion"


class IngestionRunRequest(BaseModel):
    """Input for one versioned corpus build; active aliases are never valid targets."""

    staging_collection: str = Field(min_length=4, max_length=192)
    source_id: uuid.UUID
    download_limit: int | None = Field(default=None, ge=1, le=10_000)

    @field_validator("staging_collection")
    @classmethod
    def require_physical_staging_collection(cls, value: str) -> str:
        return validate_lore_staging_collection(value)

    @property
    def corpus_version(self) -> str:
        return corpus_version_from_staging_collection(self.staging_collection)


@dataclass(frozen=True)
class IngestionRunResult:
    """Durable summary with no corpus text or provider payloads."""

    job_id: uuid.UUID
    release_id: uuid.UUID
    downloaded_pages: int
    parsed_pages: int
    parent_documents: int
    staged_chunks: int
    acknowledged_vectors: int
    parent_manifest_checksum: str
    vector_manifest_checksum: str


class IngestionOrchestrator:
    """Coordinates the application ingestion DAG under one durable job identity.

    Each concrete stage owns its domain work. This class owns only ordering,
    acknowledgement checks, parent persistence, and sanitized job lifecycle.
    """

    def __init__(
        self,
        *,
        downloader: DownloaderStage,
        parser: ParserStage,
        parent_builder: ParentBuilderStage,
        semantic_chunk_builder: SemanticChunkBuilderStage,
        entity_resolver: EntityResolverStage,
        metadata_enricher: MetadataEnricherStage,
        validator: ValidationStage,
        incremental_router: IncrementalRouterStage,
        batch_embedding: BatchEmbeddingStage,
        qdrant_upsert: QdrantUpsertStage,
        parent_repository: ILoreParentRepository,
        release_repository: ICorpusReleaseRepository,
        job_repository: IPipelineJobRepository,
        source_access: EvidenceAccess,
    ) -> None:
        self._downloader = downloader
        self._parser = parser
        self._parent_builder = parent_builder
        self._semantic_chunk_builder = semantic_chunk_builder
        self._entity_resolver = entity_resolver
        self._metadata_enricher = metadata_enricher
        self._validator = validator
        self._incremental_router = incremental_router
        self._batch_embedding = batch_embedding
        self._qdrant_upsert = qdrant_upsert
        self._parent_repository = parent_repository
        self._release_repository = release_repository
        self._job_repository = job_repository
        self._source_access = source_access

    async def run(self, request: IngestionRunRequest) -> IngestionRunResult:
        job_id = await self._job_repository.create_job(
            "ingestion_dag", "application_ingestion_orchestrator"
        )
        await self._job_repository.update_job_status(job_id, "RUNNING")

        try:
            downloaded = await self._execute(
                "download",
                self._downloader.execute(job_id, DownloaderInput(limit=request.download_limit)),
            )
            parsed = await self._execute(
                "parse",
                self._parser.execute(job_id, ParserInput(downloaded_pages=downloaded.output)),
            )

            parents: list[LoreParent] = []
            for page in parsed.output:
                parent_result = await self._execute(
                    "parent_build",
                    self._parent_builder.execute(
                        job_id,
                        ParentBuilderInput(
                            parsed_page=page,
                            corpus_version=request.corpus_version,
                            source_id=request.source_id,
                            access=self._source_access,
                        ),
                    ),
                )
                parents.extend(parent_result.output)

            self._validate_parent_provenance(
                parents,
                source_id=request.source_id,
                corpus_version=request.corpus_version,
            )

            chunks = await self._execute(
                "semantic_chunk",
                self._semantic_chunk_builder.execute(
                    job_id, SemanticChunkBuilderInput(parents=parents)
                ),
            )
            resolved = await self._execute(
                "entity_resolve",
                self._entity_resolver.execute(job_id, EntityResolverInput(chunks=chunks.output)),
            )
            enriched = await self._execute(
                "metadata_enrich",
                self._metadata_enricher.execute(
                    job_id, MetadataEnricherInput(chunks=resolved.output)
                ),
            )
            validated = await self._execute(
                "validate",
                self._validator.execute(job_id, ValidationInput(chunks=enriched.output)),
            )
            routed = await self._execute(
                "incremental_route",
                self._incremental_router.execute(
                    job_id,
                    IncrementalRouterInput(
                        chunks=validated.output,
                        full_version_rebuild=True,
                    ),
                ),
            )
            embedded = await self._execute(
                "embed",
                self._batch_embedding.execute(job_id, BatchEmbeddingInput(chunks=routed.output)),
            )
            upserted = await self._execute(
                "qdrant_upsert",
                self._qdrant_upsert.execute(
                    job_id,
                    QdrantUpsertInput(
                        chunks=embedded.output,
                        staging_collection=request.staging_collection,
                    ),
                ),
            )
            # A failed vector acknowledgement must not leave parent rows for an
            # unpublished corpus version. The staging collection is retry-safe
            # because point IDs are deterministic; parent persistence happens
            # only after every vector write has been acknowledged.
            for parent in parents:
                await self._parent_repository.save_parent(parent)
            await self._job_repository.log_event(
                job_id, "ParentsPersisted", {"parent_count": len(parents)}
            )
            release = CorpusRelease(
                job_id=job_id,
                source_id=request.source_id,
                logical_collection=logical_collection_from_staging_collection(
                    request.staging_collection
                ),
                staging_collection=request.staging_collection,
                corpus_version=request.corpus_version,
                parent_count=len(parents),
                vector_count=upserted.metrics.items_processed,
                parent_manifest_checksum=self._parent_manifest_checksum(parents),
                vector_manifest_checksum=self._vector_manifest_checksum(upserted.output),
            )
            await self._release_repository.save_release(release)
            await self._release_repository.record_audit(
                CorpusReleaseAuditEvent(
                    release_id=release.release_id,
                    actor_id=_INGESTION_SERVICE_ACTOR_ID,
                    action=CorpusReleaseAuditAction.STAGED,
                    new_status=release.status,
                    new_corpus_version=release.corpus_version,
                )
            )
        except Exception as exc:
            await self._job_repository.log_event(
                job_id,
                "IngestionFailed",
                {"error_type": type(exc).__name__},
            )
            await self._job_repository.update_job_status(
                job_id, "FAILED", error=type(exc).__name__
            )
            raise

        await self._job_repository.log_event(
            job_id,
            "IngestionAcknowledged",
            {
                "downloaded_pages": len(downloaded.output),
                "parsed_pages": len(parsed.output),
                "parent_documents": len(parents),
                "staged_chunks": len(upserted.output),
                "acknowledged_vectors": upserted.metrics.items_processed,
                "parent_manifest_checksum": self._parent_manifest_checksum(parents),
                "vector_manifest_checksum": self._vector_manifest_checksum(upserted.output),
                "release_id": str(release.release_id),
            },
        )
        await self._job_repository.update_job_status(job_id, "SUCCEEDED")
        return IngestionRunResult(
            job_id=job_id,
            release_id=release.release_id,
            downloaded_pages=len(downloaded.output),
            parsed_pages=len(parsed.output),
            parent_documents=len(parents),
            staged_chunks=len(upserted.output),
            acknowledged_vectors=upserted.metrics.items_processed,
            parent_manifest_checksum=self._parent_manifest_checksum(parents),
            vector_manifest_checksum=self._vector_manifest_checksum(upserted.output),
        )

    @staticmethod
    def _validate_parent_provenance(
        parents: list[LoreParent],
        *,
        source_id: uuid.UUID,
        corpus_version: str,
    ) -> None:
        """Reject a parent store receipt that cannot be tied to this staged corpus."""
        if any(
            parent.source_id != source_id or parent.corpus_version != corpus_version
            for parent in parents
        ):
            raise IngestionStageError(stage="parent_manifest", failed_items=1)

    @staticmethod
    def _parent_manifest_checksum(parents: list[LoreParent]) -> str:
        """Hash the persisted parent identities and ACL/version provenance deterministically."""
        rows = [
            ParentManifestRow(
                parent_id=str(parent.id),
                content_hash=hashlib.sha256(parent.markdown.encode("utf-8")).hexdigest(),
                source_id=str(parent.source_id or ""),
                corpus_version=str(parent.corpus_version or ""),
                access=parent.access,
            )
            for parent in parents
        ]
        return parent_manifest_checksum(rows)

    @staticmethod
    def _vector_manifest_checksum(chunks: list[Any]) -> str:
        """Hash only acknowledged vector rows using the Qdrant payload contract."""
        rows: list[LoreManifestRow] = []
        for chunk in chunks:
            if (
                not chunk.is_valid
                or chunk.skip_embedding
                or chunk.vector is None
                or chunk.payload is None
            ):
                continue
            payload = chunk.payload
            if (
                payload.chunk_hash is None
                or payload.source_id is None
                or payload.corpus_version is None
            ):
                raise IngestionStageError(stage="manifest", failed_items=1)
            rows.append(
                LoreManifestRow(
                    point_id=str(chunk.chunk_id),
                    chunk_hash=payload.chunk_hash,
                    parent_id=payload.parent_id,
                    source_id=payload.source_id,
                    corpus_version=payload.corpus_version,
                    access=EvidenceAccess(
                        scope=payload.access_scope,
                        subject_id=payload.access_subject_id,
                        tenant_id=payload.access_tenant_id,
                        channel_id=payload.access_channel_id,
                    ),
                )
            )
        return lore_manifest_checksum(rows)

    @staticmethod
    async def _execute(stage: str, operation: Any) -> PipelineResult[Any]:
        result = await operation
        if result.metrics.items_failed:
            raise IngestionStageError(
                stage=stage, failed_items=result.metrics.items_failed
            )
        return result
