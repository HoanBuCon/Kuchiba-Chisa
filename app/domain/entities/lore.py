import uuid
from dataclasses import dataclass, field
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.models.evidence import EvidenceAccess


class LorePayload(BaseModel):
    """
    Optimized strict typing for vector payload metadata stored in Qdrant.
    Designed for 1M+ chunks on limited VPS RAM. Offloads parent texts to relational DB.
    """
    # Structural Identity
    parent_id: str = Field(..., description="UUID of the parent document. Used to fetch parent text.")
    section_id: str | None = Field(None, description="Unique section ID, e.g., '1024-H2-01-H3-02'")
    page_id: int = Field(..., description="ID of the Wiki page. Used to prevent orphans during updates.")
    source_file: str = Field(..., description="Original markdown file name (e.g., 'breaking_the_loop.md')")
    revision_id: int | None = Field(
        None, description="Immutable source revision used to reproduce the indexed chunk."
    )
    chunk_index: int = Field(default=0, description="Sequential index of this child chunk")
    chunk_start_offset: int | None = Field(
        None, ge=0, description="Inclusive character offset within the parent source."
    )
    chunk_end_offset: int | None = Field(
        None, ge=0, description="Exclusive character offset within the parent source."
    )
    text_content: str = Field(..., description="The actual text content of the child chunk for vector matching")
    source_id: str | None = Field(
        None, description="Approved source registry identifier for this corpus record."
    )
    corpus_version: str | None = Field(
        None, description="Version of the corpus staging build that produced this chunk."
    )
    chunk_hash: str | None = Field(
        None,
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-fA-F]{64}$",
        description="SHA-256 of the indexed child text, used to verify staged corpus manifests.",
    )
    access_scope: str = Field(default="public", description="Indexed evidence access scope.")
    access_subject_id: str | None = Field(default=None, max_length=128)
    access_tenant_id: str | None = Field(default=None, max_length=128)
    access_channel_id: str | None = Field(default=None, max_length=128)

    # Hierarchy Metadata
    heading_path: str | None = Field(
        None,
        description=(
            "Hierarchical heading path, e.g., 'Characters > Kuchiba Chisa > Forte Circuit'"
        ),
    )
    section_depth: int | None = Field(
        None, description="Depth level of heading (2 for H2, 3 for H3)"
    )

    # Entity Metadata
    canonical_name: str | None = Field(None, description="Canonical name of primary entity")
    entity_id: str | None = Field(None, description="Unique entity ID in dictionary")
    entity_type: str | None = Field(
        None,
        description="Entity classification: 'CHARACTER', 'WEAPON', 'WORLD', 'STORY'",
    )
    entities: list[str] = Field(
        default_factory=list, 
        description="Canonical names of entities present in this chunk. Used for Qdrant filtering.",
    )

    # Domain Filters (Optional, used for hard cross-filtering)
    region: str | None = Field(None, description="e.g., 'Septimont'")
    faction: str | None = Field(None, description="e.g., 'Huanglong'")
    quest: str | None = Field(None, description="e.g., 'Breaking the Loop'")
    source_type: str | None = Field(None, description="e.g., 'Quest', 'Voice Line', 'Item'")
    game_version: str | None = Field(None, description="e.g., '2.8'")
    page_type: str | None = Field(None, description="e.g., 'Character', 'Weapon', 'Lore'")
    
    # Schema Governance
    schema_version: int = Field(default=3, description="Integer version for backward compatibility tracking")

    @model_validator(mode="after")
    def validate_chunk_offsets(self) -> "LorePayload":
        """Reject partial or inverted source spans before an index write."""

        if (self.chunk_start_offset is None) != (self.chunk_end_offset is None):
            raise ValueError("chunk offsets must be present together")
        if (
            self.chunk_start_offset is not None
            and self.chunk_end_offset is not None
            and self.chunk_end_offset < self.chunk_start_offset
        ):
            raise ValueError("chunk_end_offset must not precede chunk_start_offset")
        return self

    @model_validator(mode="after")
    def validate_access_labels(self) -> "LorePayload":
        EvidenceAccess(
            scope=self.access_scope,
            subject_id=self.access_subject_id,
            tenant_id=self.access_tenant_id,
            channel_id=self.access_channel_id,
        )
        return self

    # Strictly prevent accidental payload bloat
    model_config = ConfigDict(extra="ignore")

@dataclass
class LoreParent:
    """
    Represents the full parent section document stored in a relational database.
    Retrieved via parent_id or section_id after vector search finds relevant child chunks.
    """
    id: uuid.UUID
    page_id: int
    page_title: str
    heading: str | None
    markdown: str
    source_file: str | None
    revision_id: int
    corpus_version: str | None = None
    source_id: uuid.UUID | None = None
    access: EvidenceAccess = field(default_factory=lambda: EvidenceAccess(scope="public"))
    section_id: str | None = None
    heading_path: str | None = None
    section_depth: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
