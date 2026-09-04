"""Pure authorization policies for authenticated principals."""

from __future__ import annotations

from app.domain.value_objects.principal import PrincipalContext, PrincipalSource
from app.shared.utils.user_identity import normalize_user_id_str


class AuthorizationError(Exception):
    """Raised when a verified principal lacks authority for a resource."""


class AuthorizationPolicy:
    """Centralizes scope, object, tenant, and channel authorization."""

    @staticmethod
    def require_scope(principal: PrincipalContext, scope: str) -> None:
        if not principal.has_scope(scope):
            raise AuthorizationError("required scope is missing")

    @classmethod
    def require_any_scope(cls, principal: PrincipalContext, *scopes: str) -> None:
        if not any(principal.has_scope(scope) for scope in scopes):
            raise AuthorizationError("no permitted scope is present")

    @classmethod
    def require_subject_access(
        cls,
        principal: PrincipalContext,
        requested_user_id: str,
        *,
        own_scope: str,
        elevated_scope: str,
    ) -> None:
        cls.require_any_scope(principal, own_scope, elevated_scope)
        if principal.has_scope(elevated_scope):
            return
        if normalize_user_id_str(requested_user_id) != normalize_user_id_str(principal.subject_id):
            raise AuthorizationError("principal does not own the requested user resource")

    @staticmethod
    def require_tenant(principal: PrincipalContext, requested_tenant_id: str) -> None:
        if principal.tenant_id is None or principal.tenant_id != requested_tenant_id:
            raise AuthorizationError("principal does not belong to the requested tenant")

    @staticmethod
    def tenant_id_or_deny(principal: PrincipalContext) -> str:
        if principal.tenant_id is None:
            raise AuthorizationError("credential has no tenant context")
        return principal.tenant_id

    @staticmethod
    def require_channel(principal: PrincipalContext, requested_channel_id: str) -> None:
        if principal.channel_id is None or principal.channel_id != requested_channel_id:
            raise AuthorizationError("principal does not belong to the requested channel")

    @staticmethod
    def channel_id_or_deny(principal: PrincipalContext) -> str:
        if principal.channel_id is None:
            raise AuthorizationError("credential has no channel context")
        return principal.channel_id

    @staticmethod
    def require_source(principal: PrincipalContext, source: PrincipalSource) -> None:
        if principal.source != source:
            raise AuthorizationError("credential source is not permitted for this route")
