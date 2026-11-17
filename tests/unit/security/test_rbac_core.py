"""RBAC core: permission matrix, server-computed authority, stale tokens (IAM-001..010)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from authz_fakes import FakeRepo, MemoryCache, RecordingAudit
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.application.security.authz_service import (
    AccountNotFoundError,
    AuthzService,
    RoleChangeRejectedError,
    StaleAuthzVersionError,
)
from app.config.settings import settings
from app.domain.models.rbac import (
    ROLE_PERMISSIONS,
    AccountStatus,
    AuthzSnapshot,
    Permission,
    Role,
    RoleAssignment,
    effective_permissions,
    guest_permissions,
)
from app.domain.value_objects.principal import PrincipalContext
from app.infrastructure.cache.redis.authz_snapshot_cache import RedisAuthzSnapshotCache
from app.infrastructure.security.jwt_authenticator import JwtAuthenticator
from app.interface.api.dependencies.security import (
    get_current_principal,
    get_effective_permissions,
    require_permission,
)

NOW = datetime(2026, 11, 17, 12, 0, tzinfo=UTC)
ACCOUNT_ID = uuid.uuid4()
ADMIN_ID = str(uuid.uuid4())


def _assignment(**changes) -> RoleAssignment:
    values = {
        "account_id": ACCOUNT_ID,
        "role": Role.CHIA_CON,
        "granted_by": ADMIN_ID,
        "granted_at": NOW - timedelta(days=1),
        "reason": "trusted tester",
        **changes,
    }
    return RoleAssignment(**values)


def _service(repo: FakeRepo, cache: MemoryCache | None = None) -> AuthzService:
    return AuthzService(
        repo_factory=lambda session: repo,
        cache=cache or MemoryCache(),
        audit=RecordingAudit(),
        clock=lambda: NOW,
    )


def test_matrix_is_nested_and_agentic_starts_at_chia_con() -> None:
    assert (
        ROLE_PERMISSIONS[Role.GUEST]
        < ROLE_PERMISSIONS[Role.MEMBER]
        < ROLE_PERMISSIONS[Role.CHIA_CON]
        < ROLE_PERMISSIONS[Role.ADMIN]
    )
    for role in (Role.GUEST, Role.MEMBER):
        assert Permission.CHAT_AGENTIC not in ROLE_PERMISSIONS[role]
    assert Permission.CHAT_AGENTIC in ROLE_PERMISSIONS[Role.ADMIN]


def test_only_admin_holds_role_management_and_console() -> None:
    admin_only = {
        Permission.ROLE_CHIA_CON_GRANT,
        Permission.ROLE_CHIA_CON_REVOKE,
        Permission.ADMIN_CONSOLE,
    }
    assert admin_only <= ROLE_PERMISSIONS[Role.ADMIN]
    assert not admin_only & ROLE_PERMISSIONS[Role.CHIA_CON]


@pytest.mark.parametrize("status", [AccountStatus.SUSPENDED, AccountStatus.DELETED])
def test_suspended_or_deleted_account_has_no_permissions(status) -> None:
    assert effective_permissions(status, (_assignment(),), NOW) == frozenset()


def test_active_account_is_a_member_without_assignments() -> None:
    permissions = effective_permissions(AccountStatus.ACTIVE, (), NOW)

    assert permissions == ROLE_PERMISSIONS[Role.MEMBER]


def test_live_chia_con_assignment_adds_agentic() -> None:
    permissions = effective_permissions(AccountStatus.ACTIVE, (_assignment(),), NOW)

    assert Permission.CHAT_AGENTIC in permissions


def test_expired_assignment_grants_nothing() -> None:
    expired = _assignment(expires_at=NOW - timedelta(seconds=1))

    assert Permission.CHAT_AGENTIC not in effective_permissions(
        AccountStatus.ACTIVE, (expired,), NOW
    )


def test_revoked_assignment_grants_nothing() -> None:
    revoked = _assignment(revoked_at=NOW - timedelta(hours=1), revoked_by=ADMIN_ID)

    assert Permission.CHAT_AGENTIC not in effective_permissions(
        AccountStatus.ACTIVE, (revoked,), NOW
    )


@pytest.mark.asyncio
async def test_stale_token_version_is_rejected() -> None:
    repo = FakeRepo()
    repo.authz_ver = 3

    with pytest.raises(StaleAuthzVersionError):
        await _service(repo).permissions_for_token(None, ACCOUNT_ID, 2)


@pytest.mark.asyncio
async def test_token_without_a_version_is_stale() -> None:
    with pytest.raises(StaleAuthzVersionError):
        await _service(FakeRepo()).permissions_for_token(None, ACCOUNT_ID, None)


@pytest.mark.asyncio
async def test_current_token_gets_permissions_from_the_database() -> None:
    repo = FakeRepo()
    repo.assignments.append(_assignment())

    permissions = await _service(repo).permissions_for_token(None, ACCOUNT_ID, 1)

    assert Permission.CHAT_AGENTIC in permissions


@pytest.mark.asyncio
async def test_suspended_account_with_a_current_token_has_no_permissions() -> None:
    repo = FakeRepo(AccountStatus.SUSPENDED)

    assert await _service(repo).permissions_for_token(None, ACCOUNT_ID, 1) == frozenset()


@pytest.mark.asyncio
async def test_unknown_account_is_rejected() -> None:
    repo = FakeRepo()
    repo.known = False

    with pytest.raises(AccountNotFoundError):
        await _service(repo).permissions_for_token(None, ACCOUNT_ID, 1)


@pytest.mark.asyncio
async def test_grant_bumps_the_version_and_drops_the_cached_snapshot() -> None:
    repo, cache = FakeRepo(), MemoryCache()
    service = _service(repo, cache)
    await service.permissions_for_token(None, ACCOUNT_ID, 1)
    assert ACCOUNT_ID in cache.items

    await service.grant_chia_con(None, account_id=ACCOUNT_ID, granted_by=ADMIN_ID, reason="beta")

    assert repo.authz_ver == 2
    assert ACCOUNT_ID not in cache.items
    with pytest.raises(StaleAuthzVersionError):
        await service.permissions_for_token(None, ACCOUNT_ID, 1)
    assert Permission.CHAT_AGENTIC in await service.permissions_for_token(None, ACCOUNT_ID, 2)


@pytest.mark.asyncio
async def test_revoke_takes_agentic_away_from_the_next_token() -> None:
    repo = FakeRepo()
    service = _service(repo)
    await service.grant_chia_con(None, account_id=ACCOUNT_ID, granted_by=ADMIN_ID, reason="beta")

    revoked = await service.revoke_chia_con(
        None, account_id=ACCOUNT_ID, revoked_by=ADMIN_ID, reason="abuse"
    )

    assert revoked is True
    assert repo.authz_ver == 3
    assert Permission.CHAT_AGENTIC not in await service.permissions_for_token(None, ACCOUNT_ID, 3)


@pytest.mark.asyncio
async def test_revoking_nothing_leaves_the_version_alone() -> None:
    repo = FakeRepo()

    revoked = await _service(repo).revoke_chia_con(
        None, account_id=ACCOUNT_ID, revoked_by=ADMIN_ID, reason="cleanup"
    )

    assert revoked is False
    assert repo.authz_ver == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["", "   "])
async def test_role_changes_need_a_reason(reason) -> None:
    service = _service(FakeRepo())

    with pytest.raises(RoleChangeRejectedError):
        await service.grant_chia_con(
            None, account_id=ACCOUNT_ID, granted_by=ADMIN_ID, reason=reason
        )
    with pytest.raises(RoleChangeRejectedError):
        await service.revoke_chia_con(
            None, account_id=ACCOUNT_ID, revoked_by=ADMIN_ID, reason=reason
        )


@pytest.mark.asyncio
async def test_grant_with_a_past_expiry_is_rejected() -> None:
    with pytest.raises(RoleChangeRejectedError):
        await _service(FakeRepo()).grant_chia_con(
            None,
            account_id=ACCOUNT_ID,
            granted_by=ADMIN_ID,
            reason="beta",
            expires_at=NOW - timedelta(minutes=1),
        )


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.ttls: dict[str, int | None] = {}
        self.broken = False

    async def get(self, key):
        if self.broken:
            raise ConnectionError
        return self.values.get(key)

    async def set(self, key, value, ttl=None):
        if self.broken:
            raise ConnectionError
        self.values[key] = value
        self.ttls[key] = ttl

    async def delete(self, key):
        self.values.pop(key, None)


@pytest.mark.asyncio
async def test_redis_snapshot_round_trips_with_a_ttl_under_the_revocation_bound() -> None:
    redis = FakeRedis()
    cache = RedisAuthzSnapshotCache(redis)
    snapshot = AuthzSnapshot(4, ROLE_PERMISSIONS[Role.CHIA_CON])

    await cache.set(ACCOUNT_ID, snapshot)

    assert await cache.get(ACCOUNT_ID) == snapshot
    assert 0 < next(iter(redis.ttls.values())) <= 60
    await cache.invalidate(ACCOUNT_ID)
    assert await cache.get(ACCOUNT_ID) is None


@pytest.mark.asyncio
async def test_redis_failure_and_garbage_read_as_a_miss() -> None:
    redis = FakeRedis()
    cache = RedisAuthzSnapshotCache(redis)
    redis.values[f"authz:snapshot:{ACCOUNT_ID}"] = "not json"
    assert await cache.get(ACCOUNT_ID) is None

    redis.broken = True
    assert await cache.get(ACCOUNT_ID) is None
    await cache.set(ACCOUNT_ID, AuthzSnapshot(1, frozenset()))
    await cache.invalidate(ACCOUNT_ID)


def _forged_token(**extra_claims) -> str:
    authenticator = JwtAuthenticator()
    token, _ = authenticator.issue_account_access_token(ACCOUNT_ID, uuid.uuid4(), 1)
    claims = jwt.decode(token, options={"verify_signature": False})
    claims.update(extra_claims)
    return jwt.encode(claims, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def test_access_token_carries_the_authz_version() -> None:
    principal = JwtAuthenticator().authenticate_token(_forged_token())

    assert principal.authz_ver == 1
    assert principal.authentication == "account"


def test_forged_roles_claim_is_ignored() -> None:
    token = _forged_token(roles=["admin"], role="admin", permissions=["chat:agentic"])

    principal = JwtAuthenticator().authenticate_token(token)

    assert not hasattr(principal, "roles")
    assert "chat:agentic" not in principal.scopes


@pytest.mark.asyncio
async def test_forged_roles_claim_does_not_change_computed_permissions() -> None:
    principal = JwtAuthenticator().authenticate_token(_forged_token(roles=["admin"]))

    permissions = await _service(FakeRepo()).permissions_for_token(
        None, uuid.UUID(principal.subject_id), principal.authz_ver
    )

    assert Permission.CHAT_AGENTIC not in permissions
    assert Permission.ADMIN_CONSOLE not in permissions


def test_account_token_without_a_version_parses_as_unversioned() -> None:
    claims = jwt.decode(_forged_token(), options={"verify_signature": False})
    del claims["authz_ver"]
    token = jwt.encode(claims, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)

    assert JwtAuthenticator().authenticate_token(token).authz_ver is None


def _principal(authentication: str, authz_ver: int | None = None) -> PrincipalContext:
    return PrincipalContext(
        subject_id=str(ACCOUNT_ID) if authentication == "account" else "device-1",
        tenant_id=None,
        channel_id=None,
        source="web",
        kind="user",
        scopes=frozenset({"chat:write"}),
        authentication=authentication,  # type: ignore[arg-type]
        authz_ver=authz_ver,
    )


def _guarded_client(principal: PrincipalContext, permissions: frozenset[Permission]) -> TestClient:
    app = FastAPI()

    @app.get("/member")
    def member(_: frozenset = Depends(require_permission(Permission.THREAD_MANAGE))) -> dict:
        return {"ok": True}

    app.dependency_overrides[get_current_principal] = lambda: principal
    app.dependency_overrides[get_effective_permissions] = lambda: permissions
    return TestClient(app)


def test_guest_cannot_reach_a_member_permission() -> None:
    client = _guarded_client(_principal("anonymous"), guest_permissions())

    assert client.get("/member").status_code == 403


def test_member_reaches_a_member_permission() -> None:
    client = _guarded_client(_principal("account", 1), ROLE_PERMISSIONS[Role.MEMBER])

    assert client.get("/member").status_code == 200


@pytest.mark.asyncio
async def test_anonymous_principal_only_gets_guest() -> None:
    permissions = await get_effective_permissions(_principal("anonymous"), None, None)  # type: ignore[arg-type]

    assert permissions == guest_permissions()


def _workload(discord_user_id: str = "1234567890") -> PrincipalContext:
    return PrincipalContext(
        subject_id=discord_user_id,
        tenant_id="guild-1",
        channel_id="channel-1",
        source="discord",
        kind="workload",
        scopes=frozenset({"chat:write"}),
        authentication="workload",
    )


@pytest.mark.asyncio
async def test_workload_with_an_unlinked_discord_user_gets_guest() -> None:
    service = _service(FakeRepo())

    permissions = await get_effective_permissions(_workload(), service, None)  # type: ignore[arg-type]

    assert permissions == guest_permissions()


@pytest.mark.asyncio
async def test_workload_with_a_linked_discord_user_resolves_to_the_account() -> None:
    repo = FakeRepo()
    repo.identities[("discord", "1234567890")] = ACCOUNT_ID
    service = _service(repo)

    permissions = await get_effective_permissions(_workload(), service, None)  # type: ignore[arg-type]

    assert permissions == ROLE_PERMISSIONS[Role.MEMBER]
    assert Permission.CHAT_AGENTIC not in permissions


@pytest.mark.asyncio
async def test_linked_discord_user_inherits_a_chia_con_grant_from_the_database() -> None:
    repo = FakeRepo()
    repo.identities[("discord", "1234567890")] = ACCOUNT_ID
    repo.assignments.append(_assignment())

    permissions = await get_effective_permissions(_workload(), _service(repo), None)  # type: ignore[arg-type]

    assert Permission.CHAT_AGENTIC in permissions


@pytest.mark.asyncio
async def test_linked_but_suspended_account_gives_the_discord_user_nothing() -> None:
    repo = FakeRepo(AccountStatus.SUSPENDED)
    repo.identities[("discord", "1234567890")] = ACCOUNT_ID

    permissions = await get_effective_permissions(_workload(), _service(repo), None)  # type: ignore[arg-type]

    assert permissions == frozenset()

