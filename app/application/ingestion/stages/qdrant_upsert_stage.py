"""Application stage for acknowledged writes to a versioned Qdrant collection."""

from __future__ import annotations

import time
import uuid

from pydantic import BaseModel, Field, field_validator

from app.application.ingestion.errors import (
    CorpusSafetyGateError,
    QdrantIngestionAcknowledgementError,
)
from app.domain.entities.chunk_models import ProcessingChunk
from app.domain.interfaces.pipeline import IPipelineStage, PipelineMetrics, PipelineResult
from app.domain.interfaces.repositories import IPipelineJobRepository
from app.domain.interfaces.vector_store import IVectorStore
from app.domain.models.corpus_safety_exception import CorpusSafetyProvenance
from app.domain.models.lore_collections import validate_lore_staging_collection
from app.domain.services.guardrails import CorpusSafetyGate
from app.shared.utils.logger import get_logger

log = get_logger(__name__)


class QdrantUpsertInput(BaseModel):
    """Only a physical staging collection is valid for corpus ingestion."""

    chunks: list[ProcessingChunk]
    staging_collection: str = Field(min_length=4, max_length=192)

    @field_validator("staging_collection")
    @classmethod
    def require_physical_staging_collection(cls, value: str) -> str:
        return validate_lore_staging_collection(value)


class QdrantUpsertStage(IPipelineStage[QdrantUpsertInput, list[ProcessingChunk]]):
    """Upsert embedded chunks without mutating the currently active corpus."""

    def __init__(
        self,
        vector_store: IVectorStore,
        job_repo: IPipelineJobRepository,
        batch_size: int = 100,
        corpus_safety_gate: CorpusSafetyGate | None = None,
    ) -> None:
        self.vector_store = vector_store
        self.job_repo = job_repo
        self.batch_size = batch_size
        self.corpus_safety_gate = corpus_safety_gate or CorpusSafetyGate()

    async def execute(
        self, job_id: uuid.UUID, input_data: QdrantUpsertInput
    ) -> PipelineResult[list[ProcessingChunk]]:
        log.info(
            "Starting QdrantUpsertStage",
            job_id=job_id,
            chunks=len(input_data.chunks),
            target_collection=input_data.staging_collection,
        )
        start_time = time.perf_counter()
        to_upsert = [
            chunk
            for chunk in input_data.chunks
            if chunk.is_valid
            and not chunk.skip_embedding
            and chunk.vector is not None
            and chunk.payload is not None
        ]
        decisions = [
            self.corpus_safety_gate.inspect(
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
            for chunk in to_upsert
        ]
        exceptions = [decision for decision in decisions if decision.exception_applied]
        if exceptions:
            await self.job_repo.log_event(
                job_id,
                "CorpusSafetyExceptionApplied",
                {
                    "exception_count": len(exceptions),
                    "records": [
                        {
                            "source_id": decision.source_id,
                            "checksum": decision.checksum,
                            "rule_id": decision.rule_id,
                            "finding_fingerprint": decision.fingerprint,
                            "exception_id": decision.exception_id,
                            "curator_reason": decision.exception_reason,
                            "approved_by": decision.approved_by,
                            "approved_at": decision.approved_at,
                            "provenance": (
                                decision.provenance.model_dump(mode="json")
                                if decision.provenance is not None
                                else None
                            ),
                        }
                        for decision in exceptions
                    ],
                },
            )
        quarantined = [decision for decision in decisions if decision.quarantined]
        if quarantined:
            await self.job_repo.log_event(
                job_id,
                "CorpusSafetyQuarantined",
                {
                    "quarantined_count": len(quarantined),
                    "records": [
                        {
                            "source_id": decision.source_id,
                            "checksum": decision.checksum,
                            "rule_id": decision.rule_id,
                            "fingerprint": decision.fingerprint,
                        }
                        for decision in quarantined
                    ],
                },
            )
            raise CorpusSafetyGateError(
                quarantined_count=len(quarantined),
                report_path=f"ingestion-job:{job_id}",
            )
        acknowledged_count = 0

        for batch_start in range(0, len(to_upsert), self.batch_size):
            batch = to_upsert[batch_start : batch_start + self.batch_size]
            for chunk in batch:
                vector = chunk.vector
                payload = chunk.payload
                if vector is None or payload is None:
                    raise ValueError("Validated chunk is missing vector or payload")
                point_id = str(chunk.chunk_id)
                try:
                    await self.vector_store.upsert_lore(
                        collection=input_data.staging_collection,
                        point_id=point_id,
                        vector=vector,
                        payload=payload.model_dump(exclude_none=True),
                    )
                except Exception as exc:
                    error = QdrantIngestionAcknowledgementError(
                        target_collection=input_data.staging_collection,
                        failed_point_id=point_id,
                        acknowledged_count=acknowledged_count,
                    )
                    await self.job_repo.log_event(
                        job_id,
                        "QdrantUpsertUnacknowledged",
                        {
                            "acknowledged_count": acknowledged_count,
                            "failed_point_id": point_id,
                            "target_collection": input_data.staging_collection,
                        },
                    )
                    raise error from exc
                acknowledged_count += 1

        metrics = PipelineMetrics(
            duration_seconds=time.perf_counter() - start_time,
            items_processed=acknowledged_count,
            items_failed=0,
            items_skipped=len(input_data.chunks) - acknowledged_count,
        )
        await self.job_repo.log_event(job_id, "QdrantUpsertComplete", metrics.model_dump())
        return PipelineResult(output=input_data.chunks, metrics=metrics)
