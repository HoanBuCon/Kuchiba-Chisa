import uuid
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from app.domain.entities.lore import LorePayload

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
    
    # Metadata extracted by subsequent stages
    extracted_entities: List[str] = Field(default_factory=list)
    resolved_entities: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    # Final generated payload and vector
    payload: Optional[LorePayload] = None
    vector: Optional[List[float]] = None
    
    # Validation
    is_valid: bool = True
    validation_errors: List[str] = Field(default_factory=list)
    
    # Action routing
    skip_embedding: bool = False
