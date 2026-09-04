"""Security and state-transition tests for ING-03 source governance."""

from __future__ import annotations

import uuid

import pytest

from app.application.ingestion.source_governance import (
    IngestionSourceGovernanceService,
    RegisterIngestionSourceCommand,
)
from app.application.security.authorization import AuthorizationError
from app.domain.models.evidence import EvidenceAccess
from app.domain.models.ingestion_source import (
    IngestionSource,
    IngestionSourceAuditEvent,
    SourceAccessPolicy,
    SourceStatus,
    SourceTrustTier,
)
from app.domain.value_objects.principal import PrincipalContext
from app.domain.value_objects.principal import PrincipalKind, PrincipalSource


class SourceRepository:
    def __init__(self) -> None:
        self.sources: dict[uuid.UUID, IngestionSource] = {}

    async def get_source(self, source_id: uuid.UUID) -> IngestionSource | None:
        return self.sources.get(source_id)

    async def save_source(self, source: IngestionSource) -> None:
        self.sources[source.source_id] = source


class AuditRepository:
    def __init__(self) -> None:
        self.events: list[IngestionSourceAuditEvent] = []

    async def record(self, event: IngestionSourceAuditEvent) -> None:
        self.events.append(event)


def _principal(
    subject_id: str = "curator-a",
    *,
    tenant_id: str | None = "tenant-a",
    scopes: frozenset[str] | None = None,
    kind: PrincipalKind = "user",
    source: PrincipalSource = "web",
) -> PrincipalContext:
    return PrincipalContext(
        subject_id=subject_id,
        tenant_id=tenant_id,
        channel_id=None,
        source=source,
        kind=kind,
        scopes=scopes or frozenset({"ingestion:source:write"}),
    )


def _command(access: EvidenceAccess | None = None) -> RegisterIngestionSourceCommand:
    return RegisterIngestionSourceCommand(
        uri="https://wutheringwaves.fandom.com/api.php",
        license_identifier="Fandom-terms-reviewed",
        access_policy=SourceAccessPolicy(access=access or EvidenceAccess(scope="public")),
        trust_tier=SourceTrustTier.REVIEWED,
        checksum="c" * 64,
        crawl_schedule="0 3 * * *",
    )


@pytest.mark.asyncio
async def test_registration_uses_verified_curator_as_owner_and_writes_quarantine_audit() -> None:
    sources = SourceRepository()
    audits = AuditRepository()
    service = IngestionSourceGovernanceService(sources, audits)

    source = await service.register(_principal(), _command())

    assert source.owner_id == "curator-a"
    assert source.status is SourceStatus.QUARANTINED
    assert sources.sources[source.source_id] == source
    assert len(audits.events) == 1
    assert audits.events[0].actor_id == "curator-a"
    assert audits.events[0].old_status is None
    assert audits.events[0].new_status is SourceStatus.QUARANTINED


@pytest.mark.asyncio
async def test_tenant_source_registration_rejects_client_declared_foreign_tenant() -> None:
    sources = SourceRepository()
    service = IngestionSourceGovernanceService(sources, AuditRepository())
    foreign_tenant = _command(EvidenceAccess(scope="tenant", tenant_id="tenant-b"))

    with pytest.raises(AuthorizationError):
        await service.register(_principal(), foreign_tenant)

    assert not sources.sources


@pytest.mark.asyncio
async def test_curator_cannot_read_or_approve_another_curators_source_without_elevated_scope() -> None:
    sources = SourceRepository()
    audits = AuditRepository()
    service = IngestionSourceGovernanceService(sources, audits)
    owned = await service.register(_principal("curator-a"), _command())
    other = _principal(
        "curator-b",
        scopes=frozenset({"ingestion:source:read", "ingestion:source:approve"}),
    )

    with pytest.raises(AuthorizationError):
        await service.get(other, owned.source_id)
    with pytest.raises(AuthorizationError):
        await service.approve(other, owned.source_id)

    assert owned.status is SourceStatus.QUARANTINED
    assert len(audits.events) == 1


@pytest.mark.asyncio
async def test_approved_transition_has_verified_actor_and_old_new_status_audit() -> None:
    sources = SourceRepository()
    audits = AuditRepository()
    service = IngestionSourceGovernanceService(sources, audits)
    owner = _principal(
        scopes=frozenset({"ingestion:source:write", "ingestion:source:approve"})
    )
    registered = await service.register(owner, _command())

    approved = await service.approve(owner, registered.source_id)

    assert approved.status is SourceStatus.APPROVED
    assert approved.approved_by == "curator-a"
    approval_event = audits.events[-1]
    assert approval_event.actor_id == "curator-a"
    assert approval_event.old_status is SourceStatus.QUARANTINED
    assert approval_event.new_status is SourceStatus.APPROVED
    assert approval_event.old_checksum == approval_event.new_checksum == "c" * 64


@pytest.mark.asyncio
async def test_workload_credential_cannot_operate_curator_source_registry() -> None:
    service = IngestionSourceGovernanceService(SourceRepository(), AuditRepository())
    workload = _principal(
        scopes=frozenset({"ingestion:source:write:any"}),
        kind="workload",
        source="discord",
    )

    with pytest.raises(AuthorizationError):
        await service.register(workload, _command())
