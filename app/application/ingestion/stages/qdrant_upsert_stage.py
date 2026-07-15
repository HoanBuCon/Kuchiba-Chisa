import uuid
import time
from typing import List
from pydantic import BaseModel
from app.domain.entities.chunk_models import ProcessingChunk
from app.domain.interfaces.vector_store import IVectorStore
from app.domain.interfaces.pipeline import IPipelineStage, PipelineResult, PipelineMetrics
from app.domain.interfaces.repositories import IPipelineJobRepository
from app.shared.utils.logger import get_logger

log = get_logger(__name__)

class QdrantUpsertInput(BaseModel):
    chunks: List[ProcessingChunk]
    collection_name: str = "character_lore"

class QdrantUpsertStage(IPipelineStage[QdrantUpsertInput, List[ProcessingChunk]]):
    """
    Upserts embedded chunks to Qdrant.
    Implements pre-delete strategy to prevent orphan vectors.
    """
    def __init__(self, vector_store: IVectorStore, job_repo: IPipelineJobRepository, batch_size: int = 100):
        self.vector_store = vector_store
        self.job_repo = job_repo
        self.batch_size = batch_size

    async def execute(self, job_id: uuid.UUID, input_data: QdrantUpsertInput) -> PipelineResult[List[ProcessingChunk]]:
        log.info("Starting QdrantUpsertStage", job_id=job_id, chunks=len(input_data.chunks))
        start_time = time.perf_counter()
        
        to_upsert = [c for c in input_data.chunks if c.is_valid and not c.skip_embedding and c.vector is not None]
        items_processed = 0
        items_failed = 0
        
        if to_upsert:
            # Pre-Delete Strategy: Delete old chunks for this page_id
            # Assuming all chunks belong to the same page in this batch
            page_id = to_upsert[0].page_id
            try:
                await self.vector_store.delete_lore_by_page(input_data.collection_name, page_id)
                log.debug("Deleted old vectors for page", page_id=page_id)
            except Exception as e:
                log.error("Failed to delete old vectors", error=str(e), page_id=page_id)
                # Continuing anyway, though it might leave orphans.
            
            # Upsert Batches
            for i in range(0, len(to_upsert), self.batch_size):
                batch = to_upsert[i:i + self.batch_size]
                try:
                    # Depending on the specific IVectorStore API, we might need a batch upsert method.
                    # Assuming upsert_lore can be called sequentially or we use an upsert_lore_batch
                    # For now, we simulate calling upsert_lore sequentially or if the provider supports batching.
                    for chunk in batch:
                        await self.vector_store.upsert_lore(
                            collection=input_data.collection_name,
                            point_id=str(chunk.chunk_id),
                            vector=chunk.vector,
                            payload=chunk.payload.model_dump(exclude_none=True)
                        )
                    items_processed += len(batch)
                except Exception as e:
                    log.error("Failed to upsert batch", error=str(e), batch_start=i)
                    for chunk in batch:
                        chunk.is_valid = False
                        chunk.validation_errors.append(f"Qdrant Upsert failed: {str(e)}")
                    items_failed += len(batch)
                    
        items_skipped = len(input_data.chunks) - items_processed - items_failed

        metrics = PipelineMetrics(
            duration_seconds=time.perf_counter() - start_time,
            items_processed=items_processed,
            items_failed=items_failed,
            items_skipped=items_skipped
        )
        
        await self.job_repo.log_event(job_id, "QdrantUpsertComplete", metrics.model_dump())
        return PipelineResult(output=input_data.chunks, metrics=metrics)
