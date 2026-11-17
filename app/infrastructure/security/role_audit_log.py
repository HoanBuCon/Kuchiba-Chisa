"""Role-change audit as a structured log event until the append-only store exists (SEC-ADM-007)."""

from __future__ import annotations

from app.domain.interfaces.authz import IRoleAuditSink
from app.domain.models.rbac import RoleAuditEvent
from app.infrastructure.logging.logger import get_logger

log = get_logger(__name__)


class LoggingRoleAuditSink(IRoleAuditSink):
    async def record(self, event: RoleAuditEvent) -> None:
        log.info(
            "role_audit",
            action=event.action.value,
            actor=event.actor,
            account_id=str(event.account_id),
            role=event.role.value,
            reason=event.reason,
            at=event.at.isoformat(),
            expires_at=event.expires_at.isoformat() if event.expires_at else None,
            authz_ver_after=event.authz_ver_after,
        )
