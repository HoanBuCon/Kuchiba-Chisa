"""Governed source-registration contract for trusted corpus ingestion."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from enum import StrEnum
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.models.evidence import EvidenceAccess


class SourceTrustTier(StrEnum):
    UNTRUSTED = "untrusted"
    REVIEWED = "reviewed"
    TRUSTED = "trusted"


class SourceStatus(StrEnum):
    QUARANTINED = "quarantined"
    APPROVED = "approved"
    DISABLED = "disabled"


class IngestionSourceAuditAction(StrEnum):
    """State-changing source-registry actions retained for curator audit."""

    REGISTERED = "registered"
    APPROVED = "approved"


class SourceAccessPolicy(BaseModel):
    """Document access labels that must later reach parent and vector payloads."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    access: EvidenceAccess

    @model_validator(mode="after")
    def require_scope_identifiers(self) -> "SourceAccessPolicy":
        if self.access.scope == "public":
            if any((self.access.subject_id, self.access.tenant_id, self.access.channel_id)):
                raise ValueError("public source access cannot carry private identifiers")
        elif self.access.scope == "user" and not self.access.subject_id:
            raise ValueError("user source access requires a subject identifier")
        elif self.access.scope == "tenant" and not self.access.tenant_id:
            raise ValueError("tenant source access requires a tenant identifier")
        return self


class IngestionSource(BaseModel):
    """A versioned source registration that fails closed until curator approval."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    uri: str = Field(min_length=12, max_length=2_048)
    owner_id: str = Field(min_length=1, max_length=128)
    license_identifier: str = Field(min_length=1, max_length=128)
    access_policy: SourceAccessPolicy
    trust_tier: SourceTrustTier
    checksum: str = Field(min_length=64, max_length=64)
    crawl_schedule: str = Field(min_length=9, max_length=256)
    status: SourceStatus = SourceStatus.QUARANTINED
    approved_by: str | None = Field(default=None, min_length=1, max_length=128)
    approved_at: datetime | None = None

    @field_validator("uri")
    @classmethod
    def require_https_source_uri(cls, value: str) -> str:
        uri = value.strip()
        parsed = urlparse(uri)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("ingestion source URI must be an absolute HTTPS URL")
        return uri

    @field_validator("checksum")
    @classmethod
    def require_sha256_checksum(cls, value: str) -> str:
        checksum = value.lower()
        if re.fullmatch(r"[0-9a-f]{64}", checksum) is None:
            raise ValueError("source checksum must be a SHA-256 hexadecimal digest")
        return checksum

    @field_validator("crawl_schedule")
    @classmethod
    def require_five_field_cron(cls, value: str) -> str:
        schedule = " ".join(value.split())
        if len(schedule.split(" ")) != 5:
            raise ValueError("crawl schedule must contain five cron fields")
        return schedule

    @field_validator("approved_at")
    @classmethod
    def require_timezone_aware_approval_time(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("approved source timestamp must include a timezone")
        return value.astimezone(UTC) if value is not None else None

    @model_validator(mode="after")
    def require_consistent_approval(self) -> "IngestionSource":
        if self.status is SourceStatus.APPROVED:
            if self.trust_tier is SourceTrustTier.UNTRUSTED:
                raise ValueError("untrusted source cannot be approved")
            if not self.approved_by or self.approved_at is None:
                raise ValueError("approved source requires curator identity and timestamp")
        elif self.approved_by is not None or self.approved_at is not None:
            raise ValueError("non-approved source cannot carry approval metadata")
        return self

    def approve(self, curator_id: str, *, approved_at: datetime | None = None) -> "IngestionSource":
        """Create the approved state only for a reviewed or trusted quarantined source."""
        curator = curator_id.strip()
        if not curator:
            raise ValueError("curator identity is required")
        if self.status is not SourceStatus.QUARANTINED:
            raise ValueError("only quarantined sources can be approved")
        if self.trust_tier is SourceTrustTier.UNTRUSTED:
            raise ValueError("untrusted source cannot be approved")
        return IngestionSource.model_validate(
            {
                **self.model_dump(),
                "status": SourceStatus.APPROVED,
                "approved_by": curator,
                "approved_at": approved_at or datetime.now(UTC),
            }
        )

    def require_approved_for_ingestion(self) -> None:
        """Reject every source not explicitly approved before a crawler reads it."""
        if self.status is not SourceStatus.APPROVED:
            raise ValueError("source is not approved for ingestion")


class IngestionSourceAuditEvent(BaseModel):
    """Minimal, non-content audit record for source governance transitions."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    source_id: uuid.UUID
    actor_id: str = Field(min_length=1, max_length=128)
    action: IngestionSourceAuditAction
    old_status: SourceStatus | None = None
    new_status: SourceStatus
    old_checksum: str | None = Field(default=None, min_length=64, max_length=64)
    new_checksum: str = Field(min_length=64, max_length=64)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("old_checksum", "new_checksum")
    @classmethod
    def require_audit_sha256_checksum(cls, value: str | None) -> str | None:
        if value is not None and re.fullmatch(r"[0-9a-f]{64}", value.lower()) is None:
            raise ValueError("audit checksum must be a SHA-256 hexadecimal digest")
        return value.lower() if value is not None else None

    @field_validator("occurred_at")
    @classmethod
    def require_timezone_aware_occurrence_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("source audit timestamp must include a timezone")
        return value.astimezone(UTC)
