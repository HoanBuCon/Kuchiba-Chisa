from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field

class LorePayload(BaseModel):
    """
    Optimized strict typing for vector payload metadata stored in Qdrant.
    Designed for 1M+ chunks on limited VPS RAM. Offloads parent texts to relational DB.
    """
    # Structural Identity
    parent_id: str = Field(..., description="UUID of the parent document. Used to fetch parent text.")
    section_id: Optional[str] = Field(None, description="Unique section ID, e.g., '1024-H2-01-H3-02'")
    page_id: int = Field(..., description="ID of the Wiki page. Used to prevent orphans during updates.")
    source_file: str = Field(..., description="Original markdown file name (e.g., 'breaking_the_loop.md')")
    chunk_index: int = Field(default=0, description="Sequential index of this child chunk")
    text_content: str = Field(..., description="The actual text content of the child chunk for vector matching")

    # Hierarchy Metadata
    heading_path: Optional[str] = Field(None, description="Hierarchical heading path, e.g., 'Characters > Kuchiba Chisa > Forte Circuit'")
    section_depth: Optional[int] = Field(None, description="Depth level of heading (2 for H2, 3 for H3)")

    # Entity Metadata
    canonical_name: Optional[str] = Field(None, description="Canonical name of primary entity")
    entity_id: Optional[str] = Field(None, description="Unique entity ID in dictionary")
    entity_type: Optional[str] = Field(None, description="Entity classification: 'CHARACTER', 'WEAPON', 'WORLD', 'STORY'")
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
    schema_version: int = Field(default=3, description="Integer version for backward compatibility tracking")

    # Strictly prevent accidental payload bloat
    model_config = ConfigDict(extra="ignore")

import uuid
from dataclasses import dataclass

@dataclass
class LoreParent:
    """
    Represents the full parent section document stored in a relational database.
    Retrieved via parent_id or section_id after vector search finds relevant child chunks.
    """
    id: uuid.UUID
    page_id: int
    page_title: str
    heading: Optional[str]
    markdown: str
    source_file: Optional[str]
    revision_id: int
    section_id: Optional[str] = None
    heading_path: Optional[str] = None
    section_depth: Optional[int] = None
    created_at: Optional[any] = None
    updated_at: Optional[any] = None
