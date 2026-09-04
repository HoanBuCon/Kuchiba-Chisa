import uuid
import time
from typing import List
from pydantic import BaseModel
from app.domain.entities.chunk_models import ProcessingChunk
from app.domain.interfaces.pipeline import IPipelineStage, PipelineResult, PipelineMetrics
from app.domain.interfaces.repositories import IPipelineJobRepository, IChunkStateRepository
from app.shared.utils.logger import get_logger

log = get_logger(__name__)

class IncrementalRouterInput(BaseModel):
    chunks: List[ProcessingChunk]
    full_version_rebuild: bool = False
    
class IncrementalRouterStage(IPipelineStage[IncrementalRouterInput, List[ProcessingChunk]]):
    """
    Checks the DB for existing chunk_hash. If it matches, the chunk is skipped (skip_embedding = True).
    Allows massive speedups for incremental game patches.
    """
    def __init__(self, chunk_repo: IChunkStateRepository, job_repo: IPipelineJobRepository):
        self.chunk_repo = chunk_repo
        self.job_repo = job_repo

    async def execute(self, job_id: uuid.UUID, input_data: IncrementalRouterInput) -> PipelineResult[List[ProcessingChunk]]:
        log.info("Starting IncrementalRouterStage", job_id=job_id, chunks=len(input_data.chunks))
        start_time = time.perf_counter()

        if input_data.full_version_rebuild:
            metrics = PipelineMetrics(
                duration_seconds=time.perf_counter() - start_time,
                items_processed=len(input_data.chunks),
                items_failed=0,
                items_skipped=0,
                details={"mode": "full_version_rebuild"},
            )
            await self.job_repo.log_event(job_id, "IncrementalRouterComplete", metrics.model_dump())
            return PipelineResult(output=input_data.chunks, metrics=metrics)
        
        items_skipped = 0
        
        for chunk in input_data.chunks:
            if not chunk.is_valid:
                continue
                
            exists = await self.chunk_repo.check_hash_exists(chunk.chunk_hash)
            if exists:
                chunk.skip_embedding = True
                items_skipped += 1
                
        metrics = PipelineMetrics(
            duration_seconds=time.perf_counter() - start_time,
            items_processed=len(input_data.chunks),
            items_failed=0,
            items_skipped=items_skipped
        )
        
        await self.job_repo.log_event(job_id, "IncrementalRouterComplete", metrics.model_dump())
        return PipelineResult(output=input_data.chunks, metrics=metrics)
