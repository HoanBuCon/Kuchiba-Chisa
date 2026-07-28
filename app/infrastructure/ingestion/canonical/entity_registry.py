"""
Entity Registry — Centralized domain entity & relationship registry.

Implements Stage 5 (Metadata & Entity Extraction) from §4A & §6 of the
Ingestion Architecture Document v1.1.

Responsibilities:
    1. Register and resolve canonical entities and their aliases.
    2. Track cross-entity relationships (LOCATED_IN, AFFILIATED_WITH, OWNS, MEMBER_OF, etc.).
    3. Provide fuzzy/alias resolution for wiki links and text references.
    4. Pre-seeded with Wuthering Waves domain entities for deterministic extraction.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set

from pydantic import BaseModel, Field


class EntityRecord(BaseModel):
    """Canonical representation of a domain entity."""

    entity_id: str = Field(..., description="Unique entity identifier (slugified)")
    canonical_name: str = Field(..., description="Official primary name of the entity")
    entity_type: str = Field(..., description="Type of entity (CHARACTER, REGION, FACTION, WEAPON, etc.)")
    aliases: List[str] = Field(default_factory=list, description="Alternative names or titles")
    canonical_slug: str = Field(..., description="URL-safe slug")
    page_id: Optional[int] = Field(None, description="Wiki page ID if page exists")
    attributes: Dict[str, Any] = Field(default_factory=dict, description="Metadata attributes (element, rarity, etc.)")


class RelationshipRecord(BaseModel):
    """Directed relationship between two entities."""

    source_entity: str = Field(..., description="Canonical name of source entity")
    relation: str = Field(..., description="Relationship type (LOCATED_IN, AFFILIATED_WITH, MEMBER_OF, etc.)")
    target_entity: str = Field(..., description="Canonical name of target entity")
    confidence: float = Field(1.0, ge=0.0, le=1.0, description="Extraction confidence")
    evidence_section: Optional[str] = Field(None, description="Section title where relationship was extracted")


class EntityRegistry:
    """Centralized Registry for canonical entity lookup, alias resolution, and graph relationships."""

    def __init__(self) -> None:
        self._entities: Dict[str, EntityRecord] = {}  # Key: entity_id (slug)
        self._alias_map: Dict[str, str] = {}  # Key: normalized name/alias -> entity_id
        self._relationships: List[RelationshipRecord] = []
        self._seed_default_entities()

    def _normalize_name(self, name: str) -> str:
        """Normalize string for robust lookups."""
        norm = name.lower().strip()
        norm = re.sub(r"[^\w\s]", "", norm)
        return norm

    def _seed_default_entities(self) -> None:
        """Pre-seed registry with known Wuthering Waves domain entities."""
        defaults = [
            # Characters
            EntityRecord(
                entity_id="aalto",
                canonical_name="Aalto",
                entity_type="CHARACTER",
                aliases=["Aalto Information Broker", "Magician Aalto"],
                canonical_slug="aalto",
                attributes={"element": "Aero", "weapon": "Pistol", "rarity": 4, "faction": "Black Shores"},
            ),
            EntityRecord(
                entity_id="yinlin",
                canonical_name="Yinlin",
                entity_type="CHARACTER",
                aliases=["Patroller Yinlin", "Secret Agent Yinlin"],
                canonical_slug="yinlin",
                attributes={"element": "Electro", "weapon": "Rectifier", "rarity": 5},
            ),
            EntityRecord(
                entity_id="rover",
                canonical_name="Rover",
                entity_type="CHARACTER",
                aliases=["Main Character", "Protagonist"],
                canonical_slug="rover",
                attributes={"element": "Spectro/Havoc", "weapon": "Sword", "rarity": 5},
            ),
            EntityRecord(
                entity_id="kuchiba_chisa",
                canonical_name="Kuchiba Chisa",
                entity_type="CHARACTER",
                aliases=["Chisa", "Thread Master"],
                canonical_slug="kuchiba_chisa",
                attributes={"element": "Havoc", "weapon": "Sword", "rarity": 5},
            ),
            # Factions & Organizations
            EntityRecord(
                entity_id="startorch_academy",
                canonical_name="Startorch Academy",
                entity_type="FACTION",
                aliases=["Startorch", "Academy of Lahai-Roi"],
                canonical_slug="startorch_academy",
                attributes={"region": "Lahai-Roi"},
            ),
            EntityRecord(
                entity_id="spacetrek_collective",
                canonical_name="Spacetrek Collective",
                entity_type="FACTION",
                aliases=["Spacetrek"],
                canonical_slug="spacetrek_collective",
                attributes={"region": "Lahai-Roi"},
            ),
            EntityRecord(
                entity_id="fractsidus",
                canonical_name="Fractsidus",
                entity_type="FACTION",
                aliases=["Order of Fractsidus"],
                canonical_slug="fractsidus",
                attributes={},
            ),
            EntityRecord(
                entity_id="roya_tribe",
                canonical_name="Roya Tribe",
                entity_type="FACTION",
                aliases=["Roya"],
                canonical_slug="roya_tribe",
                attributes={"region": "Lahai-Roi"},
            ),
            EntityRecord(
                entity_id="court_of_savantae",
                canonical_name="Court of Savantae",
                entity_type="FACTION",
                aliases=["Savantae"],
                canonical_slug="court_of_savantae",
                attributes={"region": "Lahai-Roi"},
            ),
            # Regions
            EntityRecord(
                entity_id="lahai_roi",
                canonical_name="Lahai-Roi",
                entity_type="REGION",
                aliases=["Lahai Roi", "Roya Frostlands"],
                canonical_slug="lahai_roi",
                attributes={},
            ),
            EntityRecord(
                entity_id="jinzhou",
                canonical_name="Jinzhou",
                entity_type="REGION",
                aliases=["Jinzhou City", "Huanglong Jinzhou"],
                canonical_slug="jinzhou",
                attributes={"country": "Huanglong"},
            ),
            EntityRecord(
                entity_id="ashinohara",
                canonical_name="Ashinohara",
                entity_type="REGION",
                aliases=["Ashinohara Region"],
                canonical_slug="ashinohara",
                attributes={},
            ),
            EntityRecord(
                entity_id="septimont",
                canonical_name="Septimont",
                entity_type="REGION",
                aliases=["Septimont Region"],
                canonical_slug="septimont",
                attributes={},
            ),
            EntityRecord(
                entity_id="rinascita",
                canonical_name="Rinascita",
                entity_type="REGION",
                aliases=["Rinascita Region"],
                canonical_slug="rinascita",
                attributes={},
            ),
        ]

        for record in defaults:
            self.register_entity(record)

    def register_entity(self, record: EntityRecord) -> None:
        """Register a new canonical entity or update existing."""
        self._entities[record.entity_id] = record

        # Map canonical name
        norm_canonical = self._normalize_name(record.canonical_name)
        self._alias_map[norm_canonical] = record.entity_id

        # Map aliases
        for alias in record.aliases:
            norm_alias = self._normalize_name(alias)
            self._alias_map[norm_alias] = record.entity_id

    def resolve_alias(self, name_or_alias: str) -> Optional[str]:
        """Resolve any name or alias to canonical entity name."""
        norm = self._normalize_name(name_or_alias)
        entity_id = self._alias_map.get(norm)
        if entity_id and entity_id in self._entities:
            return self._entities[entity_id].canonical_name
        return None

    def get_entity(self, name_or_alias: str) -> Optional[EntityRecord]:
        """Fetch EntityRecord by canonical name or alias."""
        norm = self._normalize_name(name_or_alias)
        entity_id = self._alias_map.get(norm)
        if entity_id:
            return self._entities.get(entity_id)
        return None

    def register_relationship(
        self,
        source: str,
        relation: str,
        target: str,
        confidence: float = 1.0,
        evidence_section: Optional[str] = None,
    ) -> RelationshipRecord:
        """Register a directed relationship between two entities."""
        # Resolve aliases to canonical names if possible
        canonical_source = self.resolve_alias(source) or source
        canonical_target = self.resolve_alias(target) or target

        rel = RelationshipRecord(
            source_entity=canonical_source,
            relation=relation,
            target_entity=canonical_target,
            confidence=confidence,
            evidence_section=evidence_section,
        )

        # Avoid exact duplicates
        for existing in self._relationships:
            if (
                existing.source_entity == rel.source_entity
                and existing.relation == rel.relation
                and existing.target_entity == rel.target_entity
            ):
                return existing

        self._relationships.append(rel)
        return rel

    def get_relationships_for_entity(self, entity_name: str) -> List[RelationshipRecord]:
        """Find all relationships involving specified entity."""
        canonical = self.resolve_alias(entity_name) or entity_name
        return [
            r for r in self._relationships
            if r.source_entity == canonical or r.target_entity == canonical
        ]

    def export_summary(self) -> Dict[str, Any]:
        """Export state summary of the registry."""
        return {
            "total_entities": len(self._entities),
            "total_aliases": len(self._alias_map),
            "total_relationships": len(self._relationships),
            "entity_types": sorted(list({e.entity_type for e in self._entities.values()})),
        }
