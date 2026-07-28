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
    Transforms a ParsedPage into multiple LoreParent documents by splitting at H2 (Level 2) and H3 (Level 3) boundaries.
    Generates section_id and full hierarchical heading_path (e.g., 'Page Title > H2 Heading > H3 Heading').
    """
    
    def __init__(self, job_repo: IPipelineJobRepository):
        self.job_repo = job_repo

    async def execute(self, job_id: uuid.UUID, input_data: ParentBuilderInput) -> PipelineResult[List[LoreParent]]:
        log.info("Starting ParentBuilderStage", job_id=job_id, page_id=input_data.parsed_page.page_id)
        
        start_time = time.perf_counter()
        parents: List[LoreParent] = []
        
        page = input_data.parsed_page
        h2_idx = 0
        h3_idx = 0
        
        current_h2_title: Optional[str] = None
        current_h3_title: Optional[str] = None
        current_heading: Optional[str] = "Lead"
        current_depth: int = 1
        current_blocks: List[str] = []
        
        def flush_current():
            nonlocal current_blocks, current_heading, current_depth
            if current_blocks:
                # Build heading_path
                parts = [page.title]
                if current_h2_title and current_h2_title != "Lead":
                    parts.append(current_h2_title)
                if current_h3_title:
                    parts.append(current_h3_title)
                
                heading_path = " > ".join(parts)
                
                # Generate section_id
                sec_id = f"{page.page_id}-H2-{h2_idx:02d}"
                if h3_idx > 0:
                    sec_id += f"-H3-{h3_idx:02d}"
                    
                parents.append(
                    self._create_parent(
                        page=page,
                        heading=current_heading,
                        markdown="\n\n".join(current_blocks),
                        section_id=sec_id,
                        heading_path=heading_path,
                        section_depth=current_depth
                    )
                )
                current_blocks = []

        for section in page.document.sections:
            if section.level <= 2:
                flush_current()
                h2_idx += 1
                h3_idx = 0
                current_h2_title = section.title
                current_h3_title = None
                current_heading = section.title
                current_depth = 2
                
                prefix = "## " if section.title != "Lead" else ""
                current_blocks.append(f"{prefix}{section.title}\n{section.content}".strip() if prefix else section.content.strip())
            elif section.level == 3:
                flush_current()
                h3_idx += 1
                current_h3_title = section.title
                current_heading = section.title
                current_depth = 3
                
                current_blocks.append(f"### {section.title}\n{section.content}".strip())
            else:
                prefix = "#" * section.level
                current_blocks.append(f"{prefix} {section.title}\n{section.content}".strip())

        flush_current()

        metrics = PipelineMetrics(
            duration_seconds=time.perf_counter() - start_time,
            items_processed=len(parents),
            items_failed=0,
            items_skipped=0
        )
        
        await self.job_repo.log_event(job_id, "ParentBuilderComplete", metrics.model_dump())
        return PipelineResult(output=parents, metrics=metrics)

    def _create_parent(
        self,
        page: ParsedPage,
        heading: Optional[str],
        markdown: str,
        section_id: str,
        heading_path: str,
        section_depth: int
    ) -> LoreParent:
        return LoreParent(
            id=uuid.uuid4(),
            page_id=page.page_id,
            page_title=page.title,
            heading=heading,
            markdown=markdown.strip(),
            source_file=None,
            revision_id=page.revision_id,
            section_id=section_id,
            heading_path=heading_path,
            section_depth=section_depth
        )
