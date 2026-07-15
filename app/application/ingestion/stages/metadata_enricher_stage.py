import uuid
import time
from typing import List
from pydantic import BaseModel
from app.domain.entities.chunk_models import ProcessingChunk
from app.domain.entities.lore import LorePayload
from app.domain.interfaces.pipeline import IPipelineStage, PipelineResult, PipelineMetrics
from app.domain.interfaces.repositories import IPipelineJobRepository
from app.shared.utils.logger import get_logger

log = get_logger(__name__)

class MetadataEnricherInput(BaseModel):
    chunks: List[ProcessingChunk]
    
class MetadataEnricherStage(IPipelineStage[MetadataEnricherInput, List[ProcessingChunk]]):
    """
    Builds restricted Qdrant payload to save RAM.
    Fields: entities, region, faction, quest, source_type, game_version, page_type.
    """
    def __init__(self, job_repo: IPipelineJobRepository):
        self.job_repo = job_repo

    async def execute(self, job_id: uuid.UUID, input_data: MetadataEnricherInput) -> PipelineResult[List[ProcessingChunk]]:
        log.info("Starting MetadataEnricherStage", job_id=job_id, chunks=len(input_data.chunks))
        start_time = time.perf_counter()
        
        for chunk in input_data.chunks:
            # For a real implementation, we would extract these fields from the ParsedPage's infobox or categories.
            # Here we provide a skeleton that expects `chunk.metadata` to be populated by the Orchestrator
            # or we extract basic defaults from the page_title.
            
            # TODO: Extract real region, faction from DB or infobox
            region = chunk.metadata.get("region")
            faction = chunk.metadata.get("faction")
            quest = chunk.metadata.get("quest")
            source_type = chunk.metadata.get("source_type")
            game_version = chunk.metadata.get("game_version")
            page_type = chunk.metadata.get("page_type")
            
            chunk.payload = LorePayload(
                parent_id=str(chunk.parent_id),
                page_id=chunk.page_id,
                source_file=f"{chunk.page_title.replace(' ', '_').lower()}.md",
                chunk_index=chunk.chunk_index,
                text_content=chunk.text_content,
                entities=chunk.resolved_entities,
                region=region,
                faction=faction,
                quest=quest,
                source_type=source_type,
                game_version=game_version,
                page_type=page_type,
                schema_version=2
            )
            
        metrics = PipelineMetrics(
            duration_seconds=time.perf_counter() - start_time,
            items_processed=len(input_data.chunks),
            items_failed=0,
            items_skipped=0
        )
        
        await self.job_repo.log_event(job_id, "MetadataEnricherComplete", metrics.model_dump())
        return PipelineResult(output=input_data.chunks, metrics=metrics)
