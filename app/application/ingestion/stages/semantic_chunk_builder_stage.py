import uuid
import time
import hashlib
from typing import List
from pydantic import BaseModel
from app.domain.entities.lore import LoreParent
from app.domain.entities.chunk_models import ProcessingChunk
from app.domain.interfaces.pipeline import IPipelineStage, PipelineResult, PipelineMetrics
from app.domain.interfaces.repositories import IPipelineJobRepository
from app.shared.utils.logger import get_logger

log = get_logger(__name__)

class SemanticChunkBuilderInput(BaseModel):
    parents: List[LoreParent]

class SemanticChunkBuilderStage(IPipelineStage[SemanticChunkBuilderInput, List[ProcessingChunk]]):
    """
    Implements Rule-Based Semantic Adaptive Chunking.
    Treats nodes (Heading, Paragraph, Table, Dialogue, List) as atomic blocks.
    Merges blocks adaptively. Target: 400~700 tokens (1600-2800 chars), Hard Max: 900 tokens (3600 chars).
    """
    
    TARGET_MIN_CHARS = 1600
    TARGET_MAX_CHARS = 2800
    HARD_MAX_CHARS = 3600
    
    def __init__(self, job_repo: IPipelineJobRepository):
        self.job_repo = job_repo

    async def execute(self, job_id: uuid.UUID, input_data: SemanticChunkBuilderInput) -> PipelineResult[List[ProcessingChunk]]:
        log.info("Starting SemanticChunkBuilderStage", job_id=job_id, parents=len(input_data.parents))
        start_time = time.perf_counter()
        
        all_chunks: List[ProcessingChunk] = []
        
        for parent in input_data.parents:
            blocks = parent.markdown.split("\n\n")
            current_chunk_blocks: List[str] = []
            current_chunk_length = 0
            chunk_index = 0
            
            for block in blocks:
                block_len = len(block)
                
                # If adding this block exceeds HARD_MAX, flush the current chunk first
                if current_chunk_length + block_len > self.HARD_MAX_CHARS and current_chunk_blocks:
                    all_chunks.append(self._create_chunk(parent, current_chunk_blocks, chunk_index))
                    chunk_index += 1
                    current_chunk_blocks = []
                    current_chunk_length = 0
                
                # Add block to current chunk
                current_chunk_blocks.append(block)
                current_chunk_length += block_len
                
                # If current chunk is within TARGET range, flush it
                if self.TARGET_MIN_CHARS <= current_chunk_length <= self.TARGET_MAX_CHARS:
                    all_chunks.append(self._create_chunk(parent, current_chunk_blocks, chunk_index))
                    chunk_index += 1
                    current_chunk_blocks = []
                    current_chunk_length = 0
                    
            # Flush remaining blocks
            if current_chunk_blocks:
                all_chunks.append(self._create_chunk(parent, current_chunk_blocks, chunk_index))
                
        metrics = PipelineMetrics(
            duration_seconds=time.perf_counter() - start_time,
            items_processed=len(all_chunks),
            items_failed=0,
            items_skipped=0
        )
        
        await self.job_repo.log_event(job_id, "SemanticChunkBuilderComplete", metrics.model_dump())
        return PipelineResult(output=all_chunks, metrics=metrics)

    def _create_chunk(self, parent: LoreParent, blocks: List[str], chunk_index: int) -> ProcessingChunk:
        content = "\n\n".join(blocks).strip()
        # Create a stable hash of the content for incremental routing
        chunk_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        
        return ProcessingChunk(
            parent_id=parent.id,
            page_id=parent.page_id,
            revision_id=parent.revision_id,
            page_title=parent.page_title,
            chunk_index=chunk_index,
            text_content=content,
            chunk_hash=chunk_hash
        )
