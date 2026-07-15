import uuid
import time
from typing import List
from pydantic import BaseModel
from app.domain.entities.chunk_models import ProcessingChunk
from app.domain.interfaces.pipeline import IPipelineStage, PipelineResult, PipelineMetrics
from app.domain.interfaces.repositories import IPipelineJobRepository
from app.application.services.entity_cache_manager import EntityCacheManager
from app.shared.utils.logger import get_logger

log = get_logger(__name__)

class EntityResolverInput(BaseModel):
    chunks: List[ProcessingChunk]

class EntityResolverStage(IPipelineStage[EntityResolverInput, List[ProcessingChunk]]):
    """
    Extracts and resolves entities strictly within the chunk boundaries to preserve targeted context.
    Utilizes EntityCacheManager.
    """
    def __init__(self, cache_manager: EntityCacheManager, job_repo: IPipelineJobRepository):
        self.cache_manager = cache_manager
        self.job_repo = job_repo

    async def execute(self, job_id: uuid.UUID, input_data: EntityResolverInput) -> PipelineResult[List[ProcessingChunk]]:
        log.info("Starting EntityResolverStage", job_id=job_id, chunks=len(input_data.chunks))
        start_time = time.perf_counter()
        
        for chunk in input_data.chunks:
            # extract_entities uses Regex Trie to find all aliases and returns a set of canonical names
            resolved_set = self.cache_manager.extract_entities(chunk.text_content)
            chunk.resolved_entities = list(resolved_set)
            
        metrics = PipelineMetrics(
            duration_seconds=time.perf_counter() - start_time,
            items_processed=len(input_data.chunks),
            items_failed=0,
            items_skipped=0
        )
        
        await self.job_repo.log_event(job_id, "EntityResolverComplete", metrics.model_dump())
        return PipelineResult(output=input_data.chunks, metrics=metrics)
