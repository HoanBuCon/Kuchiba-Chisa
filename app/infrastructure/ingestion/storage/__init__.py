"""
Ingestion Storage & Sync Package.

Implements Stage 9 (INDEX & State Management) & Orphan Cleanup from §1.1 & §10 of Architecture Doc.

Modules:
    state_db    — SQLite incremental tracker for change detection & orphan page identification
    qdrant_sync — Qdrant Vector Store batch upsert & atomic page deletion
"""

from app.infrastructure.ingestion.storage.state_db import IngestionStateDB, PageStateRecord
from app.infrastructure.ingestion.storage.qdrant_sync import QdrantSyncManager, map_page_type_to_collection

__all__ = [
    "IngestionStateDB",
    "PageStateRecord",
    "QdrantSyncManager",
    "map_page_type_to_collection",
]
