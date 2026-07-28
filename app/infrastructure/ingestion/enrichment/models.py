"""
Pydantic v2 Models for Offline LLM Enrichment (§6 of Architecture Specification).

Defines structured schemas enforced via instructor for LLM/SLM extraction.
"""

from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class QuestLoreSummary(BaseModel):
    """Structured summary of a story quest or lore-heavy narrative page."""

    summary: str = Field(..., description="High-level narrative summary of the quest or event.")
    key_events: List[str] = Field(default_factory=list, description="Chronological key plot points.")
    characters_involved: List[str] = Field(default_factory=list, description="List of Resonators or key NPCs featured.")
    lore_significance: Optional[str] = Field(None, description="Worldbuilding or lore significance in Wuthering Waves.")

    model_config = ConfigDict(extra="ignore")


class EntityRelationshipExtract(BaseModel):
    """Structured entity relationship extracted from lore text."""

    source_entity: str = Field(..., description="Name of the primary entity (e.g. Sanhua).")
    target_entity: str = Field(..., description="Name of the target entity (e.g. Jinzhou City Hall).")
    relationship_type: str = Field(..., description="Type of relation: Affiliation, Ally, Relative, Enemy, Master, Pupil.")
    description: str = Field(..., description="Short contextual summary of their relationship.")

    model_config = ConfigDict(extra="ignore")
