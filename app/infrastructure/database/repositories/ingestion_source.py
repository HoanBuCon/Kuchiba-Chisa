"""SQLAlchemy persistence adapter for governed ingestion sources."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.evidence import EvidenceAccess
from app.domain.models.ingestion_source import (
    IngestionSource,
    IngestionSourceAuditEvent,
    SourceAccessPolicy,
    SourceStatus,
    SourceTrustTier,
)
from app.infrastructure.database.models.ingestion import (
    IngestionSourceAuditEventModel,
    IngestionSourceModel,
)


class IngestionSourceRepository:
    """Store source registration and curator state without exposing raw corpus content."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_source(self, source_id: uuid.UUID) -> IngestionSource | None:
        result = await self._session.execute(
            select(IngestionSourceModel).where(IngestionSourceModel.id == source_id)
        )
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model is not None else None

    async def save_source(self, source: IngestionSource) -> None:
        await self._session.merge(self._from_domain(source))
        await self._session.flush()

    @staticmethod
    def _to_domain(model: IngestionSourceModel) -> IngestionSource:
        return IngestionSource(
            source_id=model.id,
            uri=model.uri,
            owner_id=model.owner_id,
            license_identifier=model.license_identifier,
            access_policy=SourceAccessPolicy(
                access=EvidenceAccess(
                    scope=model.access_scope,
                    subject_id=model.subject_id,
                    tenant_id=model.tenant_id,
                    channel_id=model.channel_id,
                )
            ),
            trust_tier=SourceTrustTier(model.trust_tier),
            checksum=model.checksum,
            crawl_schedule=model.crawl_schedule,
            status=SourceStatus(model.status),
            approved_by=model.approved_by,
            approved_at=model.approved_at,
        )

    @staticmethod
    def _from_domain(source: IngestionSource) -> IngestionSourceModel:
        access = source.access_policy.access
        return IngestionSourceModel(
            id=source.source_id,
            uri=source.uri,
            owner_id=source.owner_id,
            license_identifier=source.license_identifier,
            access_scope=access.scope,
            subject_id=access.subject_id,
            tenant_id=access.tenant_id,
            channel_id=access.channel_id,
            trust_tier=source.trust_tier.value,
            checksum=source.checksum,
            crawl_schedule=source.crawl_schedule,
            status=source.status.value,
            approved_by=source.approved_by,
            approved_at=source.approved_at,
        )


class IngestionSourceAuditRepository:
    """Append source status transitions inside the caller's DB transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(self, event: IngestionSourceAuditEvent) -> None:
        self._session.add(
            IngestionSourceAuditEventModel(
                id=event.event_id,
                source_id=event.source_id,
                actor_id=event.actor_id,
                action=event.action.value,
                old_status=event.old_status.value if event.old_status is not None else None,
                new_status=event.new_status.value,
                old_checksum=event.old_checksum,
                new_checksum=event.new_checksum,
                occurred_at=event.occurred_at,
            )
        )
        await self._session.flush()
