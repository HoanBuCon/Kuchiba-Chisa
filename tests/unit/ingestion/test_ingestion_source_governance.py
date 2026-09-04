"""ING-03 unit tests for governed source registration and approval."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.domain.models.evidence import EvidenceAccess
from app.domain.models.ingestion_source import (
    IngestionSource,
    SourceAccessPolicy,
    SourceStatus,
    SourceTrustTier,
)
from app.application.ingestion.source_resolver import (
    ApprovedIngestionSourceResolver,
    IngestionSourceUnavailableError,
)


def _source(**overrides: object) -> IngestionSource:
    values: dict[str, object] = {
        "uri": "https://wutheringwaves.fandom.com/api.php",
        "owner_id": "lore-curator",
        "license_identifier": "Fandom-terms-reviewed",
        "access_policy": SourceAccessPolicy(access=EvidenceAccess(scope="public")),
        "trust_tier": SourceTrustTier.REVIEWED,
        "checksum": "a" * 64,
        "crawl_schedule": "0 3 * * *",
    }
    values.update(overrides)
    return IngestionSource(**values)


def test_source_is_quarantined_by_default_and_cannot_be_used_before_approval() -> None:
    source = _source()

    assert source.status is SourceStatus.QUARANTINED
    with pytest.raises(ValueError, match="not approved"):
        source.require_approved_for_ingestion()


def test_reviewed_source_requires_curator_identity_and_timestamp_for_approval() -> None:
    source = _source()

    approved = source.approve("curator-a", approved_at=datetime(2026, 9, 5, tzinfo=UTC))

    assert approved.status is SourceStatus.APPROVED
    assert approved.approved_by == "curator-a"
    approved.require_approved_for_ingestion()

    with pytest.raises(ValidationError, match="must include a timezone"):
        _source(
            status=SourceStatus.APPROVED,
            approved_by="curator-a",
            approved_at=datetime(2026, 9, 5),
        )


def test_untrusted_or_non_https_source_never_becomes_ingestable() -> None:
    with pytest.raises(ValueError, match="untrusted source"):
        _source(trust_tier=SourceTrustTier.UNTRUSTED).approve("curator-a")
    with pytest.raises(ValidationError, match="absolute HTTPS"):
        _source(uri="file:///private/corpus.txt")


def test_source_access_policy_requires_tenant_identity_for_tenant_data() -> None:
    with pytest.raises(ValidationError, match="tenant evidence requires"):
        SourceAccessPolicy(access=EvidenceAccess(scope="tenant"))

    policy = SourceAccessPolicy(
        access=EvidenceAccess(scope="tenant", tenant_id="tenant-a")
    )
    assert policy.access.tenant_id == "tenant-a"


class _SourceRepository:
    def __init__(self, source: IngestionSource | None) -> None:
        self._source = source

    async def get_source(self, _: object) -> IngestionSource | None:
        return self._source


@pytest.mark.asyncio
async def test_resolver_fails_closed_for_missing_or_quarantined_sources() -> None:
    with pytest.raises(IngestionSourceUnavailableError, match="not registered"):
        await ApprovedIngestionSourceResolver(_SourceRepository(None)).resolve(_source().source_id)
    with pytest.raises(IngestionSourceUnavailableError, match="not approved"):
        await ApprovedIngestionSourceResolver(_SourceRepository(_source())).resolve(_source().source_id)


@pytest.mark.asyncio
async def test_resolver_allows_only_a_registered_approved_source() -> None:
    approved = _source().approve("curator-a")

    assert await ApprovedIngestionSourceResolver(_SourceRepository(approved)).resolve(approved.source_id) == approved
