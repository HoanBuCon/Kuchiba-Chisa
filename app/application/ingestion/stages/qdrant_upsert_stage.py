"""Application stage for acknowledged writes to a versioned Qdrant collection."""

from __future__ import annotations

import time
import uuid

from pydantic import BaseModel, Field, field_validator

from app.application.ingestion.errors import QdrantIngestionAcknowledgementError
from app.domain.entities.chunk_models import ProcessingChunk
from app.domain.interfaces.pipeline import IPipelineStage, PipelineMetrics, PipelineResult
from app.domain.interfaces.repositories import IPipelineJobRepository
from app.domain.interfaces.vector_store import IVectorStore
from app.shared.utils.logger import get_logger

log = get_logger(__name__)


class QdrantUpsertInput(BaseModel):
    """Only a physical staging collection is valid for corpus ingestion."""

    chunks: list[ProcessingChunk]
    staging_collection: str = Field(min_length=4, max_length=192)

    @field_validator("staging_collection")
    @classmethod
    def require_physical_staging_collection(cls, value: str) -> str:
        target = value.strip()
        if "__" not in target or target.endswith("__active"):
            raise ValueError("Qdrant ingestion requires a physical versioned staging collection")
        return target


class QdrantUpsertStage(IPipelineStage[QdrantUpsertInput, list[ProcessingChunk]]):
    """Upsert embedded chunks without mutating the currently active corpus."""

    def __init__(
        self,
        vector_store: IVectorStore,
        job_repo: IPipelineJobRepository,
        batch_size: int = 100,
    ) -> None:
        self.vector_store = vector_store
        self.job_repo = job_repo
        self.batch_size = batch_size

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
