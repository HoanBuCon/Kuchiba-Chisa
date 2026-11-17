"""Admin API to grant and revoke Chia-con by account ID (ROLE-001..004)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.application.security.authz_service import (
    AccountNotFoundError,
    GrantIneligibleError,
    RoleChangeRejectedError,
)
from app.domain.models.rbac import AccountStatus, AccountSummary, Permission
from app.interface.api.dependencies.security import (
    AuthzServiceDep,
    CurrentPrincipal,
    DbSession,
    require_permission,
    require_step_up_mfa,
)

router = APIRouter(prefix="/admin/accounts", tags=["Admin roles"])
MAX_REASON_CHARS = 1000
UNPROCESSABLE = 422


class GrantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=MAX_REASON_CHARS)
    expires_at: AwareDatetime | None = None


class RevokeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=MAX_REASON_CHARS)


class AccountSummaryView(BaseModel):
    account_id: UUID
    masked_email: str | None
    created_at: datetime
    status: AccountStatus
    email_verified: bool
    linked_providers: list[str]

    @classmethod
    def of(cls, summary: AccountSummary) -> AccountSummaryView:
        return cls(
            account_id=summary.account_id,
            masked_email=summary.masked_email,
            created_at=summary.created_at,
            status=summary.status,
            email_verified=summary.email_verified,
            linked_providers=list(summary.linked_providers),
        )


class GrantResult(BaseModel):
    account_id: UUID
    role: str
    expires_at: datetime | None


class RevokeResult(BaseModel):
    account_id: UUID
    revoked: bool


def _error(status_code: int, code: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code})


@router.get(
    "/{account_id}/summary",
    dependencies=[Depends(require_permission(Permission.ACCOUNT_READ_METADATA))],
)
async def read_account_summary(
    account_id: UUID, service: AuthzServiceDep, session: DbSession
) -> AccountSummaryView:
    try:
        return AccountSummaryView.of(await service.account_summary(session, account_id))
    except AccountNotFoundError as error:
        raise _error(status.HTTP_404_NOT_FOUND, "account_not_found") from error


@router.post(
    "/{account_id}/roles/chia-con/grant",
    dependencies=[
        Depends(require_permission(Permission.ROLE_CHIA_CON_GRANT)),
        Depends(require_step_up_mfa),
    ],
)
async def grant_chia_con(
    account_id: UUID,
    body: GrantRequest,
    principal: CurrentPrincipal,
    service: AuthzServiceDep,
    session: DbSession,
) -> GrantResult:
    try:
        await service.grant_chia_con(
            session,
            account_id=account_id,
            granted_by=principal.subject_id,
            reason=body.reason,
            expires_at=body.expires_at,
        )
    except AccountNotFoundError as error:
        raise _error(status.HTTP_404_NOT_FOUND, "account_not_found") from error
    except GrantIneligibleError as error:
        raise _error(status.HTTP_409_CONFLICT, error.rejection.value) from error
    except RoleChangeRejectedError as error:
        raise _error(UNPROCESSABLE, "invalid_role_change") from error
    return GrantResult(account_id=account_id, role="chia_con", expires_at=body.expires_at)


@router.post(
    "/{account_id}/roles/chia-con/revoke",
    dependencies=[
        Depends(require_permission(Permission.ROLE_CHIA_CON_REVOKE)),
        Depends(require_step_up_mfa),
    ],
)
async def revoke_chia_con(
    account_id: UUID,
    body: RevokeRequest,
    principal: CurrentPrincipal,
    service: AuthzServiceDep,
    session: DbSession,
) -> RevokeResult:
    try:
        revoked = await service.revoke_chia_con(
            session, account_id=account_id, revoked_by=principal.subject_id, reason=body.reason
        )
    except AccountNotFoundError as error:
        raise _error(status.HTTP_404_NOT_FOUND, "account_not_found") from error
    except RoleChangeRejectedError as error:
        raise _error(UNPROCESSABLE, "invalid_role_change") from error
    return RevokeResult(account_id=account_id, revoked=revoked)
