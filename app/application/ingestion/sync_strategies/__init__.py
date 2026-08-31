"""Application policies for selecting wiki pages to ingest."""

from app.application.ingestion.sync_strategies.all_pages_sync import AllPagesSyncStrategy

__all__ = ["AllPagesSyncStrategy"]
