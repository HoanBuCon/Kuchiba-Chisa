from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field

class LorePayload(BaseModel):
    """
    Optimized strict typing for vector payload metadata stored in Qdrant.
    Designed for 1M+ chunks on limited VPS RAM. Offloads parent texts to relational DB.
    """
    # Structural Identity
    parent_id: str = Field(..., description="UUID of the parent document. Used to fetch parent text.")
    page_id: int = Field(..., description="ID of the Wiki page. Used to prevent orphans during updates.")
    source_file: str = Field(..., description="Original markdown file name (e.g., 'breaking_the_loop.md')")
    chunk_index: int = Field(default=0, description="Sequential index of this child chunk")
    text_content: str = Field(..., description="The actual text content of the child chunk for vector matching")

    # Entity-Centric Retrieval Metadata
    entities: List[str] = Field(
        default_factory=list, 
        description="Canonical names of entities present in this chunk. Used for Qdrant filtering."
    )

    # Domain Filters (Optional, used for hard cross-filtering)
    region: Optional[str] = Field(None, description="e.g., 'Septimont'")
    faction: Optional[str] = Field(None, description="e.g., 'Huanglong'")
    quest: Optional[str] = Field(None, description="e.g., 'Breaking the Loop'")
    source_type: Optional[str] = Field(None, description="e.g., 'Quest', 'Voice Line', 'Item'")
    game_version: Optional[str] = Field(None, description="e.g., '2.8'")
    page_type: Optional[str] = Field(None, description="e.g., 'Character', 'Weapon', 'Lore'")
    
    # Schema Governance
    schema_version: int = Field(default=2, description="Integer version for backward compatibility tracking")

    # Strictly prevent accidental payload bloat
    model_config = ConfigDict(extra="ignore")

import uuid
from dataclasses import dataclass

@dataclass
class LoreParent:
    """
    Represents the full parent document stored in a relational database.
    Retrieved via parent_id after vector search finds relevant child chunks.
    """
    id: uuid.UUID
    page_id: int
    page_title: str
    heading: Optional[str]
    markdown: str
    source_file: Optional[str]
    revision_id: int
    created_at: Optional[any] = None
    updated_at: Optional[any] = None
