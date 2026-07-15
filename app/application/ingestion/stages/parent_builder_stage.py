import uuid
import time
from typing import List, Optional
from pydantic import BaseModel
from app.domain.entities.parser_models import ParsedPage
from app.domain.entities.lore import LoreParent
from app.domain.interfaces.pipeline import IPipelineStage, PipelineResult, PipelineMetrics
from app.domain.interfaces.repositories import IPipelineJobRepository
from app.shared.utils.logger import get_logger

log = get_logger(__name__)

class ParentBuilderInput(BaseModel):
    parsed_page: ParsedPage

class ParentBuilderStage(IPipelineStage[ParentBuilderInput, List[LoreParent]]):
    """
    Transforms a ParsedPage into multiple LoreParent documents by splitting at H2 (Level 2) boundaries.
    """
    
    def __init__(self, job_repo: IPipelineJobRepository):
        self.job_repo = job_repo

    async def execute(self, job_id: uuid.UUID, input_data: ParentBuilderInput) -> PipelineResult[List[LoreParent]]:
        log.info("Starting ParentBuilderStage", job_id=job_id, page_id=input_data.parsed_page.page_id)
        
        start_time = time.perf_counter()
        parents: List[LoreParent] = []
        
        current_h2_title: Optional[str] = "Lead"
        current_h2_content_blocks: List[str] = []
        
        # Iterate through sections and group by H2 (Level 2 or Level 1)
        # Any Level > 2 belongs to the most recent Level <= 2
        for section in input_data.parsed_page.document.sections:
            if section.level <= 2:
                # Flush current group if it has content
                if current_h2_content_blocks:
                    parents.append(
                        self._create_parent(
                            input_data.parsed_page, 
                            current_h2_title, 
                            "\n\n".join(current_h2_content_blocks)
                        )
                    )
                # Start new group
                current_h2_title = section.title
                current_h2_content_blocks = [f"## {section.title}\n{section.content}"] if section.title != "Lead" else [section.content]
            else:
                # Add to current group
                prefix = "#" * section.level
                current_h2_content_blocks.append(f"{prefix} {section.title}\n{section.content}")
                
        # Flush the last group
        if current_h2_content_blocks:
             parents.append(
                self._create_parent(
                    input_data.parsed_page, 
                    current_h2_title, 
                    "\n\n".join(current_h2_content_blocks)
                )
            )

        metrics = PipelineMetrics(
            duration_seconds=time.perf_counter() - start_time,
            items_processed=len(parents),
            items_failed=0,
            items_skipped=0
        )
        
        await self.job_repo.log_event(job_id, "ParentBuilderComplete", metrics.model_dump())
        return PipelineResult(output=parents, metrics=metrics)

    def _create_parent(self, page: ParsedPage, heading: Optional[str], markdown: str) -> LoreParent:
        return LoreParent(
            id=uuid.uuid4(),
            page_id=page.page_id,
            page_title=page.title,
            heading=heading,
            markdown=markdown.strip(),
            source_file=None, # TBD if needed
            revision_id=page.revision_id
        )
