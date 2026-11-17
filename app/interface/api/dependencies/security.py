"""FastAPI adapters for the centralized authentication and authorization policy."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.dependencies import get_authz_service
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
DbSession = Annotated[AsyncSession, Depends(get_db_session)]


async def get_effective_permissions(
    principal: CurrentPrincipal, service: AuthzServiceDep, session: DbSession
) -> frozenset[Permission]:
    """Authority comes from the database; the token only names the account (IAM-002)."""
    if principal.authentication == "workload":
        # The bot only names a Discord user; authority comes from a linked account (IAM-009).
        return await service.permissions_for_discord_user(session, principal.subject_id)
    if principal.authentication != "account":
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
