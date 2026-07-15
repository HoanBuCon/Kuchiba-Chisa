import uuid
import time
import mwparserfromhell
from typing import List, Dict, Any
from pydantic import BaseModel
from app.domain.entities.wiki import DownloadedPage
from app.domain.entities.parser_models import WikiDocument, WikiSection, ParsedPage
from app.domain.interfaces.pipeline import IPipelineStage, PipelineResult, PipelineMetrics
from app.domain.interfaces.storage import IRawStorage
from app.domain.interfaces.repositories import IPipelineJobRepository
from app.shared.utils.logger import get_logger

log = get_logger(__name__)

class ParserInput(BaseModel):
    downloaded_pages: List[DownloadedPage]

class ParserStage(IPipelineStage[ParserInput, List[ParsedPage]]):
    """
    Parses raw Wikicode into structured WikiDocuments using mwparserfromhell.
    Converts Infoboxes to Dicts, extracts Links and Categories, and determines confidence.
    """
    
    def __init__(self, raw_storage: IRawStorage, job_repo: IPipelineJobRepository):
        self.raw_storage = raw_storage
        self.job_repo = job_repo

    async def execute(self, job_id: uuid.UUID, input_data: ParserInput) -> PipelineResult[List[ParsedPage]]:
        log.info("Starting ParserStage", job_id=job_id, count=len(input_data.downloaded_pages))
        await self.job_repo.log_event(job_id, "ParseStart", {"count": len(input_data.downloaded_pages)})
        
        start_time = time.perf_counter()
        parsed_pages: List[ParsedPage] = []
        items_failed = 0
        items_skipped = 0
        
        for page in input_data.downloaded_pages:
            try:
                raw_content = await self.raw_storage.read_raw_page(page.file_path)
                wikicode = mwparserfromhell.parse(raw_content)
                
                # Extract structured elements
                links = [str(link.title) for link in wikicode.filter_wikilinks()]
                categories = [link for link in links if link.lower().startswith("category:")]
                
                # Extract templates & infoboxes
                templates: List[Dict[str, Any]] = []
                infobox: Dict[str, Any] = {}
                
                for template in wikicode.filter_templates():
                    t_name = str(template.name).strip()
                    t_dict = {str(p.name).strip(): str(p.value).strip() for p in template.params}
                    
                    if "infobox" in t_name.lower():
                        infobox.update(t_dict)
                    else:
                        templates.append({"name": t_name, "params": t_dict})
                        
                # Extract sections
                sections: List[WikiSection] = []
                for section in wikicode.get_sections(include_lead=True):
                    # Find headings
                    headings = section.filter_headings()
                    if headings:
                        level = headings[0].level
                        title = str(headings[0].title).strip()
                        # Remove heading from content to avoid duplication
                        content = str(section).replace(str(headings[0]), "").strip()
                    else:
                        level = 1
                        title = "Lead"
                        content = str(section).strip()
                        
                    # Basic markdown conversion (strip wikitext)
                    clean_content = mwparserfromhell.parse(content).strip_code()
                    if clean_content:
                        sections.append(WikiSection(title=title, content=clean_content, level=level))
                
                # Determine confidence
                confidence = 1.0
                if len(sections) == 0 or len(raw_content) < 50:
                    confidence = 0.5
                else:
                    # Check the last processed clean_content just to see if there are raw templates leftover
                    if "{{" in clean_content: 
                        confidence -= 0.1
                
                doc = WikiDocument(
                    metadata={},
                    sections=sections,
                    links=links,
                    templates=templates,
                    categories=categories,
                    infobox=infobox,
                    confidence=max(0.0, confidence)
                )
                
                parsed_pages.append(
                    ParsedPage(
                        page_id=page.page_id,
                        title=page.title,
                        revision_id=page.revision_id,
                        document=doc
                    )
                )
                await self.job_repo.log_event(job_id, "ParseSuccess", {"page_id": page.page_id})
                
            except Exception as e:
                log.error("Failed to parse page", page_id=page.page_id, error=str(e))
                await self.job_repo.log_event(job_id, "ParseFailed", {"page_id": page.page_id, "error": str(e)})
                items_failed += 1
                
        metrics = PipelineMetrics(
            duration_seconds=time.perf_counter() - start_time,
            items_processed=len(parsed_pages),
            items_failed=items_failed,
            items_skipped=items_skipped
        )

        await self.job_repo.log_event(job_id, "ParseComplete", metrics.model_dump())
        return PipelineResult(output=parsed_pages, metrics=metrics)
