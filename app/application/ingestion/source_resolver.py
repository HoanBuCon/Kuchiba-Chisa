"""Application guard that resolves only approved registered ingestion sources."""

from __future__ import annotations

import uuid

from app.domain.interfaces.repositories import IIngestionSourceRepository
from app.domain.models.ingestion_source import IngestionSource


class IngestionSourceUnavailableError(RuntimeError):
    """No approved source is available for a requested canonical DAG run."""


class ApprovedIngestionSourceResolver:
    """Enforces the source registry trust boundary before crawler construction."""

    def __init__(self, source_repository: IIngestionSourceRepository) -> None:
        self._source_repository = source_repository

    async def resolve(self, source_id: uuid.UUID) -> IngestionSource:
        source = await self._source_repository.get_source(source_id)
        if source is None:
            raise IngestionSourceUnavailableError("ingestion source is not registered")
        try:
            source.require_approved_for_ingestion()
        except ValueError as exc:
            raise IngestionSourceUnavailableError("ingestion source is not approved") from exc
        return source
