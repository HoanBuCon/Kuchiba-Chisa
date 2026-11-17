"""SQLAlchemy persistence for role assignments and the account authorization version."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.interfaces.authz import IAuthzRepository
from app.domain.models.rbac import AccountAuthzState, AccountStatus, Role, RoleAssignment
from app.infrastructure.database.models.account import AccountIdentityModel, AccountModel
from app.infrastructure.database.models.role_assignment import RoleAssignmentModel


class SqlAlchemyAuthzRepository(IAuthzRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_state(self, account_id: uuid.UUID) -> AccountAuthzState | None:
        account = await self.session.get(AccountModel, account_id)
        if account is None:
            return None
        rows = await self.session.scalars(
            select(RoleAssignmentModel).where(RoleAssignmentModel.account_id == account_id)
        )
        # Until a status column exists, a deactivated account is the suspended state (IAM-010).
        status = AccountStatus.ACTIVE if account.is_active else AccountStatus.SUSPENDED
        return AccountAuthzState(
            account_id=account_id,
            status=status,
            authz_ver=account.authz_ver,
            assignments=tuple(_to_assignment(row) for row in rows.all()),
        )

    async def get_account_id_by_identity(self, provider: str, subject: str) -> uuid.UUID | None:
        return await self.session.scalar(
            select(AccountIdentityModel.account_id).where(
                AccountIdentityModel.provider == provider,
                AccountIdentityModel.provider_subject == subject,
            )
        )

    async def add_assignment(self, assignment: RoleAssignment) -> None:
        self.session.add(
            RoleAssignmentModel(
                account_id=assignment.account_id,
                role=assignment.role.value,
                granted_by=assignment.granted_by,
                granted_at=assignment.granted_at,
                reason=assignment.reason,
                expires_at=assignment.expires_at,
            )
        )
        await self.session.flush()

    async def revoke_active(
        self, account_id: uuid.UUID, role: Role, revoked_by: str, reason: str, now: datetime
    ) -> int:
        result = await self.session.execute(
            update(RoleAssignmentModel)
            .where(
                RoleAssignmentModel.account_id == account_id,
                RoleAssignmentModel.role == role.value,
                RoleAssignmentModel.revoked_at.is_(None),
            )
            .values(revoked_at=now, revoked_by=revoked_by, revoke_reason=reason)
        )
        return int(result.rowcount or 0)  # type: ignore[attr-defined]

    async def bump_authz_ver(self, account_id: uuid.UUID) -> int:
        new_version = await self.session.scalar(
            update(AccountModel)
            .where(AccountModel.id == account_id)
            .values(authz_ver=AccountModel.authz_ver + 1)
            .returning(AccountModel.authz_ver)
        )
        return int(new_version or 0)


def _to_assignment(row: RoleAssignmentModel) -> RoleAssignment:
    return RoleAssignment(
        account_id=row.account_id,
        role=Role(row.role),
        granted_by=row.granted_by,
        granted_at=row.granted_at,
        reason=row.reason,
        expires_at=row.expires_at,
        revoked_at=row.revoked_at,
        revoked_by=row.revoked_by,
        revoke_reason=row.revoke_reason,
    )
