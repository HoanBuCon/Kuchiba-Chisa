from __future__ import annotations

from typing import Dict, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EvidenceAccess(BaseModel):
    """Access constraints enforced before the evidence item was returned."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scope: Literal["public", "user", "tenant"]
    subject_id: str | None = None
    tenant_id: str | None = None
    channel_id: str | None = None

    @model_validator(mode="after")
    def require_scope_identifiers(self) -> "EvidenceAccess":
        """Reject incomplete or contradictory ACL labels before persistence/search."""
        private_identifiers = (self.subject_id, self.tenant_id, self.channel_id)
        if self.scope == "public" and any(private_identifiers):
            raise ValueError("public evidence cannot carry private access identifiers")
        if self.scope == "user" and not self.subject_id:
            raise ValueError("user evidence requires a subject identifier")
        if self.scope == "tenant" and not self.tenant_id:
            raise ValueError("tenant evidence requires a tenant identifier")
        return self


class EvidenceProvenance(BaseModel):
    """Stable source locator retained independently from rendered evidence text."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str = Field(min_length=1)
    source_type: str = Field(min_length=1)
    collection: str = Field(min_length=1)
    source_version: str | None = None
    parent_id: str | None = None
    page_id: int | None = None
    section_id: str | None = None
    chunk_index: int | None = Field(default=None, ge=0)
    chunk_start_offset: int | None = Field(default=None, ge=0)
    chunk_end_offset: int | None = Field(default=None, ge=0)


class EvidenceScore(BaseModel):
    """Final ranking score plus its retriever and fusion components."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    final: float
    components: Dict[str, float] = Field(default_factory=dict)


class Evidence(BaseModel):
    """Typed retrieval record passed through RAG without losing governance metadata."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: str = Field(min_length=1)
    kind: Literal["lore", "memory", "guild_memory", "image_memory"]
    text: str = Field(min_length=1)
    provenance: EvidenceProvenance
    access: EvidenceAccess
    score: EvidenceScore
