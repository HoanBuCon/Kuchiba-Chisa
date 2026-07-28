"""
Unit tests for Offline LLM Enrichment Module.
"""

from __future__ import annotations
from unittest.mock import MagicMock
import pytest
from app.infrastructure.ingestion.models import CanonicalPage, CanonicalIdentity, CanonicalSection, PageTypeEnum
from app.infrastructure.ingestion.enrichment.models import QuestLoreSummary, EntityRelationshipExtract
from app.infrastructure.ingestion.enrichment.enricher import enrich_canonical_page


def test_enrichment_models():
    summary = QuestLoreSummary(
        summary="Sanhua guards Jinzhou City Hall.",
        key_events=["Awakened resonance", "Joined City Hall"],
        characters_involved=["Sanhua", "Jiyan"],
        lore_significance="Important Jinzhou lore",
    )
    assert summary.summary == "Sanhua guards Jinzhou City Hall."
    assert "Sanhua" in summary.characters_involved

    rel = EntityRelationshipExtract(
        source_entity="Sanhua",
        target_entity="Jinzhou City Hall",
        relationship_type="Affiliation",
        description="Chief Guard",
    )
    assert rel.source_entity == "Sanhua"


def test_enrich_canonical_page_no_client():
    page = CanonicalPage(
        identity=CanonicalIdentity(
            page_id=101,
            title="Test Story",
            canonical_slug="test_story",
            page_type=PageTypeEnum.QUEST,
        ),
        sections=[
            CanonicalSection(
                section_id="sec_01",
                title="Overview",
                level=2,
                content="This is a test quest content line for Sanhua and Jiyan in Jinzhou city hall.",
            )
        ],
    )
    enriched = enrich_canonical_page(page, client=None)
    assert enriched.identity.page_id == 101


def test_enrich_canonical_page_mock_client():
    mock_client = MagicMock()
    mock_summary = QuestLoreSummary(
        summary="Mocked quest summary",
        key_events=["Event A"],
        characters_involved=["Chixia"],
    )
    mock_client.chat.completions.create.return_value = mock_summary

    page = CanonicalPage(
        identity=CanonicalIdentity(
            page_id=102,
            title="Chixia Story",
            canonical_slug="chixia_story",
            page_type=PageTypeEnum.QUEST,
        ),
        sections=[
            CanonicalSection(
                section_id="sec_02",
                title="Backstory",
                level=2,
                content="Chixia patrols Huanglong city with her dual pistols, protecting citizens.",
            )
        ],
    )

    enriched = enrich_canonical_page(page, client=mock_client)
    assert "EnrichedLore" in enriched.document_metadata.categories
