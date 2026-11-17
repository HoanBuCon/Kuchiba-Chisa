"""FastAPI adapters for the centralized authentication and authorization policy."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.dependencies import get_admin_mfa_service, get_authz_service
from app.application.security.admin_mfa_service import AdminMfaService
from app.application.security.authorization import AuthorizationError, AuthorizationPolicy
from app.application.security.authz_service import (
    AccountNotFoundError,
    AuthzService,
    StaleAuthzVersionError,
)
from app.domain.models.rbac import Permission, guest_permissions
from app.domain.value_objects.principal import PrincipalContext
from app.infrastructure.database.engine import get_db_session
from app.infrastructure.security.jwt_authenticator import AuthenticationError, jwt_authenticator


def get_current_principal(request: Request) -> PrincipalContext:
    principal = getattr(request.state, "principal", None)
    if isinstance(principal, PrincipalContext):
        return principal
    try:
        principal = jwt_authenticator.authenticate_bearer(request.headers.get("Authorization"))
    except AuthenticationError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error
    request.state.principal = principal
    return principal


CurrentPrincipal = Annotated[PrincipalContext, Depends(get_current_principal)]


AuthzServiceDep = Annotated[AuthzService, Depends(get_authz_service)]
AdminMfaServiceDep = Annotated[AdminMfaService, Depends(get_admin_mfa_service)]
DbSession = Annotated[AsyncSession, Depends(get_db_session)]


async def get_effective_permissions(
    principal: CurrentPrincipal, service: AuthzServiceDep, session: DbSession
) -> frozenset[Permission]:
    """Authority comes from the database; the token only names the account (IAM-002)."""
    if principal.authentication != "account":
        # Anonymous and Discord workload callers never hold more than guest (IAM-007).
        return guest_permissions()
    try:
        return await service.permissions_for_token(
            session, UUID(principal.subject_id), principal.authz_ver
        )
    except (StaleAuthzVersionError, AccountNotFoundError) as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error


EffectivePermissions = Annotated[frozenset[Permission], Depends(get_effective_permissions)]


def require_permission(
    permission: Permission,
) -> Callable[[EffectivePermissions], frozenset[Permission]]:
    def dependency(permissions: EffectivePermissions) -> frozenset[Permission]:
        if permission not in permissions:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
        return permissions

    return dependency


async def require_step_up_mfa(
    principal: CurrentPrincipal, service: AdminMfaServiceDep, session: DbSession
) -> None:
    """Reject with 401 `step_up_required` unless this session passed MFA recently (SEC-ADM-006)."""
    session_id = admin_session_id(principal)
    if session_id is None or not await service.has_fresh_step_up(
        session, UUID(principal.subject_id), session_id
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail={"code": "step_up_required"}
        )


def admin_session_id(principal: PrincipalContext) -> UUID | None:
    """The server-side session an account token is bound to; None for any other caller."""
    if principal.authentication != "account" or principal.session_id is None:
        return None
    try:
        return UUID(principal.session_id)
    except ValueError:
        return None


def require_scope(scope: str) -> Callable[[PrincipalContext], PrincipalContext]:
    def dependency(principal: CurrentPrincipal) -> PrincipalContext:
        try:
            AuthorizationPolicy.require_scope(principal, scope)
        except AuthorizationError as error:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Access denied"
            ) from error
        return principal

    return dependency
