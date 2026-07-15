from pydantic import BaseModel
from typing import List, Dict, Any, Optional

class WikiSection(BaseModel):
    title: str
    content: str
    level: int

class ExtractedEntity(BaseModel):
    name: str
    context: str
    inferred_type: Optional[str] = None

class WikiDocument(BaseModel):
    metadata: Dict[str, Any]
    sections: List[WikiSection]
    links: List[str]
    templates: List[Dict[str, Any]]
    categories: List[str]
    infobox: Dict[str, Any]
    confidence: float # Determines LLM fallback

class ParsedPage(BaseModel):
    page_id: int
    title: str
    revision_id: int
    document: WikiDocument
