import uuid
import time
from typing import List
from pydantic import BaseModel
from app.domain.entities.chunk_models import ProcessingChunk
from app.domain.interfaces.embedding_provider import IEmbeddingProvider
from app.domain.interfaces.pipeline import IPipelineStage, PipelineResult, PipelineMetrics
from app.domain.interfaces.repositories import IPipelineJobRepository
from app.shared.utils.logger import get_logger

log = get_logger(__name__)

class BatchEmbeddingInput(BaseModel):
    chunks: List[ProcessingChunk]

class BatchEmbeddingStage(IPipelineStage[BatchEmbeddingInput, List[ProcessingChunk]]):
    """
    Embeds chunks in batches using the configured IEmbeddingProvider.
    Skips chunks marked with `skip_embedding = True` or `is_valid = False`.
    """
    def __init__(self, provider: IEmbeddingProvider, job_repo: IPipelineJobRepository, batch_size: int = 64):
        self.provider = provider
        self.job_repo = job_repo
        self.batch_size = batch_size

    async def execute(self, job_id: uuid.UUID, input_data: BatchEmbeddingInput) -> PipelineResult[List[ProcessingChunk]]:
        log.info("Starting BatchEmbeddingStage", job_id=job_id, chunks=len(input_data.chunks))
        start_time = time.perf_counter()
        
        # Filter chunks that need embedding
        to_embed = [c for c in input_data.chunks if c.is_valid and not c.skip_embedding]
        
        items_processed = 0
        items_failed = 0
        
        if to_embed:
            # Batch process
            for i in range(0, len(to_embed), self.batch_size):
                batch = to_embed[i:i + self.batch_size]
                texts = [c.text_content for c in batch]
                
                try:
                    vectors = await self.provider.embed_batch(texts)
                    for j, chunk in enumerate(batch):
                        chunk.vector = vectors[j]
                    items_processed += len(batch)
                except Exception as e:
                    log.error("Failed to embed batch", error=str(e), batch_start=i)
                    for chunk in batch:
                        chunk.is_valid = False
                        chunk.validation_errors.append(f"Embedding failed: {str(e)}")
                    items_failed += len(batch)
                    
        items_skipped = len(input_data.chunks) - items_processed - items_failed
                    
        metrics = PipelineMetrics(
            duration_seconds=time.perf_counter() - start_time,
            items_processed=items_processed,
            items_failed=items_failed,
            items_skipped=items_skipped,
            details={
                "model": self.provider.model_name,
                "dimension": self.provider.dimension,
                "version": self.provider.version
            }
        )
        
        await self.job_repo.log_event(job_id, "BatchEmbeddingComplete", metrics.model_dump())
        return PipelineResult(output=input_data.chunks, metrics=metrics)
