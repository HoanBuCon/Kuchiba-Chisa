"""Application policy for curator-controlled ingestion source transitions."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.application.security.authorization import AuthorizationError, AuthorizationPolicy
from app.domain.interfaces.repositories import (
    IIngestionSourceAuditRepository,
    IIngestionSourceRepository,
)
from app.domain.models.ingestion_source import (
    IngestionSource,
    IngestionSourceAuditAction,
    IngestionSourceAuditEvent,
    SourceAccessPolicy,
    SourceStatus,
    SourceTrustTier,
)
from app.domain.value_objects.principal import PrincipalContext


class IngestionSourceNotFoundError(LookupError):
    """The caller referenced no registered ingestion source."""


@dataclass(frozen=True)
class RegisterIngestionSourceCommand:
    """Untrusted registration fields after transport validation."""

    uri: str
    license_identifier: str
    access_policy: SourceAccessPolicy
    trust_tier: SourceTrustTier
    checksum: str
    crawl_schedule: str


class IngestionSourceGovernanceService:
    """Centralizes RBAC, scope ownership, and immutable source audit records."""

    _WRITE_SCOPE = "ingestion:source:write"
    _WRITE_ANY_SCOPE = "ingestion:source:write:any"
    _READ_SCOPE = "ingestion:source:read"
    _READ_ANY_SCOPE = "ingestion:source:read:any"
    _APPROVE_SCOPE = "ingestion:source:approve"
    _APPROVE_ANY_SCOPE = "ingestion:source:approve:any"

    def __init__(
        self,
        source_repository: IIngestionSourceRepository,
        audit_repository: IIngestionSourceAuditRepository,
    ) -> None:
        self._source_repository = source_repository
        self._audit_repository = audit_repository

    async def register(
        self,
        principal: PrincipalContext,
        command: RegisterIngestionSourceCommand,
    ) -> IngestionSource:
        self._require_human_curator(principal)
        AuthorizationPolicy.require_any_scope(
            principal, self._WRITE_SCOPE, self._WRITE_ANY_SCOPE
        )
        self._require_access_assignment(principal, command.access_policy)

        source = IngestionSource(
            uri=command.uri,
            owner_id=principal.subject_id,
            license_identifier=command.license_identifier,
            access_policy=command.access_policy,
            trust_tier=command.trust_tier,
            checksum=command.checksum,
            crawl_schedule=command.crawl_schedule,
        )
        await self._source_repository.save_source(source)
        await self._audit_repository.record(
            IngestionSourceAuditEvent(
                source_id=source.source_id,
                actor_id=principal.subject_id,
                action=IngestionSourceAuditAction.REGISTERED,
                new_status=source.status,
                new_checksum=source.checksum,
            )
        )
        return source

    async def get(self, principal: PrincipalContext, source_id: uuid.UUID) -> IngestionSource:
        self._require_human_curator(principal)
        source = await self._get_source(source_id)
        AuthorizationPolicy.require_subject_access(
            principal,
            source.owner_id,
            own_scope=self._READ_SCOPE,
            elevated_scope=self._READ_ANY_SCOPE,
        )
        return source

    async def approve(
        self, principal: PrincipalContext, source_id: uuid.UUID
    ) -> IngestionSource:
        self._require_human_curator(principal)
        source = await self._get_source(source_id)
        AuthorizationPolicy.require_subject_access(
            principal,
            source.owner_id,
            own_scope=self._APPROVE_SCOPE,
            elevated_scope=self._APPROVE_ANY_SCOPE,
        )

        approved = source.approve(principal.subject_id)
        await self._source_repository.save_source(approved)
        await self._audit_repository.record(
            IngestionSourceAuditEvent(
                source_id=approved.source_id,
                actor_id=principal.subject_id,
                action=IngestionSourceAuditAction.APPROVED,
                old_status=source.status,
                new_status=approved.status,
                old_checksum=source.checksum,
                new_checksum=approved.checksum,
            )
        )
        return approved

    async def _get_source(self, source_id: uuid.UUID) -> IngestionSource:
        source = await self._source_repository.get_source(source_id)
        if source is None:
            raise IngestionSourceNotFoundError("ingestion source was not found")
        return source

    @staticmethod
    def _require_human_curator(principal: PrincipalContext) -> None:
        if principal.kind != "user" or principal.source != "web":
            raise AuthorizationError("interactive curator credential is required")

    def _require_access_assignment(
        self, principal: PrincipalContext, access_policy: SourceAccessPolicy
    ) -> None:
        access = access_policy.access
        if access.scope == "tenant":
            assert access.tenant_id is not None
            AuthorizationPolicy.require_tenant(principal, access.tenant_id)
        elif access.scope == "user":
            assert access.subject_id is not None
            AuthorizationPolicy.require_subject_access(
                principal,
                access.subject_id,
                own_scope=self._WRITE_SCOPE,
                elevated_scope=self._WRITE_ANY_SCOPE,
            )
        if access.channel_id is not None:
            AuthorizationPolicy.require_channel(principal, access.channel_id)
