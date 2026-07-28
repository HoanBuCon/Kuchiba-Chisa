"""
Unit tests for Entity Registry (Stage 5 - Metadata & Entity Extraction).
"""

import sys
from pathlib import Path

# Force UTF-8 on Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.infrastructure.ingestion.canonical.entity_registry import (
    EntityRecord,
    EntityRegistry,
    RelationshipRecord,
)


def test_entity_registry_default_seeding():
    registry = EntityRegistry()
    summary = registry.export_summary()

    assert summary["total_entities"] >= 9
    assert summary["total_aliases"] >= 15
    assert "CHARACTER" in summary["entity_types"]
    assert "FACTION" in summary["entity_types"]
    assert "REGION" in summary["entity_types"]


def test_alias_resolution():
    registry = EntityRegistry()

    # Direct canonical lookup
    assert registry.resolve_alias("Aalto") == "Aalto"
    assert registry.resolve_alias("aalto") == "Aalto"

    # Alias lookup
    assert registry.resolve_alias("Aalto Information Broker") == "Aalto"
    assert registry.resolve_alias("Startorch") == "Startorch Academy"
    assert registry.resolve_alias("Academy of Lahai-Roi") == "Startorch Academy"
    assert registry.resolve_alias("Lahai Roi") == "Lahai-Roi"


def test_register_custom_entity():
    registry = EntityRegistry()
    custom = EntityRecord(
        entity_id="jiyan",
        canonical_name="Jiyan",
        entity_type="CHARACTER",
        aliases=["General Jiyan", "Midnight Ranger General"],
        canonical_slug="jiyan",
        attributes={"element": "Aero", "weapon": "Broadblade", "rarity": 5},
    )

    registry.register_entity(custom)

    assert registry.resolve_alias("General Jiyan") == "Jiyan"
    assert registry.resolve_alias("Midnight Ranger General") == "Jiyan"

    rec = registry.get_entity("General Jiyan")
    assert rec is not None
    assert rec.canonical_name == "Jiyan"
    assert rec.attributes["weapon"] == "Broadblade"


def test_relationship_registration():
    registry = EntityRegistry()

    rel1 = registry.register_relationship(
        source="General Jiyan",
        relation="COMMANDS",
        target="Midnight Rangers",
        confidence=0.95,
    )

    assert rel1.source_entity == "General Jiyan"
    assert rel1.relation == "COMMANDS"
    assert rel1.target_entity == "Midnight Rangers"

    # Test alias resolution in relationship registration
    rel2 = registry.register_relationship(
        source="Aalto Information Broker",
        relation="OPERATES_IN",
        target="Lahai Roi",
    )

    assert rel2.source_entity == "Aalto"
    assert rel2.target_entity == "Lahai-Roi"

    # Query relationships for entity
    rels = registry.get_relationships_for_entity("Aalto")
    assert len(rels) >= 1
    assert rels[0].target_entity == "Lahai-Roi"


if __name__ == "__main__":
    test_entity_registry_default_seeding()
    test_alias_resolution()
    test_register_custom_entity()
    test_relationship_registration()
    print("=" * 55)
    print("ALL ENTITY REGISTRY TESTS PASSED")
    print("=" * 55)
