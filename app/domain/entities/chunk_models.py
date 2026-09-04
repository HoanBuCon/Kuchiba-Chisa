import uuid
from typing import Any

from pydantic import BaseModel, Field

from app.domain.entities.lore import LorePayload
from app.domain.models.evidence import EvidenceAccess


class ProcessingChunk(BaseModel):
    """
    Mutable state object passed through the chunk-level pipeline stages.
    """
    chunk_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    parent_id: uuid.UUID
    page_id: int
    revision_id: int
    page_title: str
    chunk_index: int
    text_content: str
    chunk_hash: str
    corpus_version: str | None = None
    source_id: uuid.UUID | None = None
    access: EvidenceAccess = Field(default_factory=lambda: EvidenceAccess(scope="public"))
    
    # Metadata extracted by subsequent stages
    extracted_entities: list[str] = Field(default_factory=list)
    resolved_entities: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    
    # Final generated payload and vector
    payload: LorePayload | None = None
    vector: list[float] | None = None
    
    # Validation
    is_valid: bool = True
    validation_errors: list[str] = Field(default_factory=list)
    
    # Action routing
    skip_embedding: bool = False
