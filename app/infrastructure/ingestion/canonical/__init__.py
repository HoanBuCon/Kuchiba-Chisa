"""
Canonical Layer Package.

Implements §4A (Canonical Dataset) & §10 Stages 5 & 5A of the Architecture Document.

Modules:
    builder — Assembles RawPage (EN crawl) + Curated VI lore into CanonicalPage
    writer  — Streaming JSONL reader/writer for data/canonical/canonical.jsonl
"""

from app.infrastructure.ingestion.canonical.builder import build_canonical_page
from app.infrastructure.ingestion.canonical.entity_registry import (
    EntityRecord,
    EntityRegistry,
    RelationshipRecord,
)
from app.infrastructure.ingestion.canonical.writer import (
    CanonicalWriter,
    read_canonical_stream,
    write_canonical_stream,
)

__all__ = [
    "build_canonical_page",
    "EntityRegistry",
    "EntityRecord",
    "RelationshipRecord",
    "CanonicalWriter",
    "write_canonical_stream",
    "read_canonical_stream",
]
