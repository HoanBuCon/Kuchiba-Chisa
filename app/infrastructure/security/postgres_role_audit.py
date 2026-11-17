"""Role-change audit written to the append-only hash chain (SEC-ADM-007)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.interfaces.authz import IRoleAuditSink
from app.domain.models.rbac import RoleAuditEvent
from app.domain.services.audit_chain import (
    GENESIS_HASH,
    AuditRecord,
    ChainVerification,
    canonical_payload,
    compute_hash,
    verify_chain,
)
from app.infrastructure.database.models.admin_audit_event import AdminAuditEventModel

# Serializes appenders so two writers never extend the same previous hash.
CHAIN_LOCK_KEY = 7_304_100_007
TARGET_PREFIX = "account:"


class PostgresRoleAuditSink(IRoleAuditSink):
    async def record(self, session: Any, event: RoleAuditEvent) -> None:
        if not isinstance(session, AsyncSession):
            raise TypeError("PostgresRoleAuditSink requires a SQLAlchemy AsyncSession.")
        await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": CHAIN_LOCK_KEY})
        last_hash = await session.scalar(
            select(AdminAuditEventModel.hash).order_by(AdminAuditEventModel.seq.desc()).limit(1)
        )
        prev_hash = last_hash or GENESIS_HASH
        target = f"{TARGET_PREFIX}{event.account_id}"
        detail = _detail_of(event)
        payload = canonical_payload(
            actor=event.actor,
            action=event.action.value,
            target=target,
            reason=event.reason,
            request_id=event.request_id,
            created_at=event.at,
            detail=detail,
        )
        session.add(
            AdminAuditEventModel(
                actor=event.actor,
                action=event.action.value,
                target=target,
                reason=event.reason,
                request_id=event.request_id,
                created_at=event.at,
                detail=detail,
                prev_hash=prev_hash,
                hash=compute_hash(prev_hash, payload),
            )
        )
        await session.flush()


async def verify_admin_audit_chain(session: AsyncSession) -> ChainVerification:
    """Report the first row whose link or hash no longer matches (SEC-ADM-007)."""
    rows = await session.scalars(select(AdminAuditEventModel).order_by(AdminAuditEventModel.seq))
    return verify_chain(_to_record(row) for row in rows)


def _detail_of(event: RoleAuditEvent) -> dict[str, Any]:
    return {
        "role": event.role.value,
        "expires_at": event.expires_at.isoformat() if event.expires_at else None,
        "authz_ver_after": event.authz_ver_after,
    }


def _to_record(row: AdminAuditEventModel) -> AuditRecord:
    return AuditRecord(
        seq=row.seq,
        actor=row.actor,
        action=row.action,
        target=row.target,
        reason=row.reason,
        request_id=row.request_id,
        created_at=row.created_at,
        detail=row.detail,
        prev_hash=row.prev_hash,
        hash=row.hash,
    )
