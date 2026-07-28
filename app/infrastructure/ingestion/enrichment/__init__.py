"""
Offline Enrichment Module — Structured LLM/SLM output extraction via instructor (§6).
"""

from app.infrastructure.ingestion.enrichment.models import (
    QuestLoreSummary,
    EntityRelationshipExtract,
)
from app.infrastructure.ingestion.enrichment.enricher import (
    enrich_canonical_page,
)

__all__ = [
    "QuestLoreSummary",
    "EntityRelationshipExtract",
    "enrich_canonical_page",
]
