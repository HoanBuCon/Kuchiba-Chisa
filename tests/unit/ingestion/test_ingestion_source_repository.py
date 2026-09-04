"""Persistence mapping regressions for ING-03 source governance."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.models.evidence import EvidenceAccess
from app.domain.models.ingestion_source import (
    IngestionSource,
    IngestionSourceAuditAction,
    IngestionSourceAuditEvent,
    SourceAccessPolicy,
    SourceTrustTier,
)
from app.infrastructure.database.repositories.ingestion_source import (
    IngestionSourceAuditRepository,
    IngestionSourceRepository,
)


def _approved_source() -> IngestionSource:
    return IngestionSource(
        uri="https://wutheringwaves.fandom.com/api.php",
        owner_id="lore-curator",
        license_identifier="Fandom-terms-reviewed",
        access_policy=SourceAccessPolicy(
            access=EvidenceAccess(scope="tenant", tenant_id="tenant-a")
        ),
        trust_tier=SourceTrustTier.REVIEWED,
        checksum="b" * 64,
        crawl_schedule="0 3 * * *",
    ).approve("curator-a")


@pytest.mark.asyncio
async def test_source_repository_persists_approved_acl_and_audit_fields() -> None:
    session = AsyncMock()
    source = _approved_source()

    await IngestionSourceRepository(session).save_source(source)

    model = session.merge.await_args.args[0]
    assert model.id == source.source_id
    assert model.access_scope == "tenant"
    assert model.tenant_id == "tenant-a"
    assert model.status == "approved"
    assert model.approved_by == "curator-a"
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_source_audit_repository_persists_actor_and_version_transition() -> None:
    session = MagicMock()
    session.flush = AsyncMock()
    source = _approved_source()
    event = IngestionSourceAuditEvent(
        source_id=source.source_id,
        actor_id="curator-a",
        action=IngestionSourceAuditAction.APPROVED,
        old_status="quarantined",
        new_status="approved",
        old_checksum="b" * 64,
        new_checksum="b" * 64,
    )

    await IngestionSourceAuditRepository(session).record(event)

    model = session.add.call_args.args[0]
    assert model.source_id == source.source_id
    assert model.actor_id == "curator-a"
    assert model.old_status == "quarantined"
    assert model.new_status == "approved"
    assert model.old_checksum == model.new_checksum == "b" * 64
    session.flush.assert_awaited_once()
