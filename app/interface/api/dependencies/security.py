"""FastAPI adapters for the centralized authentication and authorization policy."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from app.application.security.authorization import AuthorizationError, AuthorizationPolicy
from app.domain.value_objects.principal import PrincipalContext
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
