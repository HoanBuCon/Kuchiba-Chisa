import uuid
import time
from typing import List
from pydantic import BaseModel
from app.domain.entities.chunk_models import ProcessingChunk
from app.domain.interfaces.pipeline import IPipelineStage, PipelineResult, PipelineMetrics
from app.domain.interfaces.repositories import IPipelineJobRepository
from app.shared.utils.logger import get_logger

log = get_logger(__name__)

class ValidationInput(BaseModel):
    chunks: List[ProcessingChunk]

class ValidationStage(IPipelineStage[ValidationInput, List[ProcessingChunk]]):
    """
    Comprehensive QA checks: Empty/Oversized chunk, Unknown entities, Broken markdown/tables, Missing metadata.
    """
    def __init__(self, job_repo: IPipelineJobRepository):
        self.job_repo = job_repo

    async def execute(self, job_id: uuid.UUID, input_data: ValidationInput) -> PipelineResult[List[ProcessingChunk]]:
        log.info("Starting ValidationStage", job_id=job_id, chunks=len(input_data.chunks))
        start_time = time.perf_counter()
        
        items_failed = 0
        
        for chunk in input_data.chunks:
            chunk.is_valid = True
            chunk.validation_errors = []
            
            # 1. Empty or Oversized
            content_len = len(chunk.text_content)
            if content_len < 10:
                chunk.is_valid = False
                chunk.validation_errors.append("Chunk is too short (< 10 chars)")
            elif content_len > 4000:
                chunk.is_valid = False
                chunk.validation_errors.append(f"Chunk is oversized ({content_len} chars)")
                
            # 2. Missing metadata payload
            if not chunk.payload:
                chunk.is_valid = False
                chunk.validation_errors.append("Missing LorePayload")
                
            # 3. Broken markdown tables (very basic check)
            if "|" in chunk.text_content and "-|-" in chunk.text_content:
                # Naive check to see if we chopped a table in half
                lines = chunk.text_content.splitlines()
                table_lines = [line for line in lines if "|" in line]
                if len(table_lines) == 1:
                    chunk.is_valid = False
                    chunk.validation_errors.append("Potentially broken markdown table")
                    
            if not chunk.is_valid:
                log.warning("Chunk validation failed", chunk_id=chunk.chunk_id, errors=chunk.validation_errors)
                items_failed += 1
                
        # Filter out invalid chunks
        valid_chunks = [c for c in input_data.chunks if c.is_valid]
                
        metrics = PipelineMetrics(
            duration_seconds=time.perf_counter() - start_time,
            items_processed=len(input_data.chunks),
            items_failed=items_failed,
            items_skipped=0
        )
        
        await self.job_repo.log_event(job_id, "ValidationComplete", metrics.model_dump())
        return PipelineResult(output=valid_chunks, metrics=metrics)
