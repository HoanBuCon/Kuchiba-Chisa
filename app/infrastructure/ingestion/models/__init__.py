"""
Pydantic v2 Data Schemas for the Ingestion Pipeline.

Three-layer model hierarchy:
    1. RawPage       — Unprocessed wiki page metadata from crawl
    2. CanonicalPage — Fully parsed, normalized, enriched "golden" record
    3. Chunk         — Retrieval-ready text segment with inherited metadata
"""

from app.infrastructure.ingestion.models.raw_page import (
    RawPage,
    RawPageMeta,
)
from app.infrastructure.ingestion.models.canonical_page import (
    PageTypeEnum,
    ContentTypeEnum,
    ProvenanceRecord,
    CanonicalSection,
    CanonicalIdentity,
    DocumentMetadata,
    ExtractedEntity,
    EntityRelationship,
    QualityIssue,
    QualityReport,
    CanonicalMeta,
    CanonicalPage,
)
from app.infrastructure.ingestion.models.chunk_model import (
    ChunkStrategyEnum,
    Chunk,
)

__all__ = [
    # Raw layer
    "RawPage",
    "RawPageMeta",
    # Canonical layer
    "PageTypeEnum",
    "ContentTypeEnum",
    "ProvenanceRecord",
    "CanonicalSection",
    "CanonicalIdentity",
    "DocumentMetadata",
    "ExtractedEntity",
    "EntityRelationship",
    "QualityIssue",
    "QualityReport",
    "CanonicalMeta",
    "CanonicalPage",
    # Chunk layer
    "ChunkStrategyEnum",
    "Chunk",
]
