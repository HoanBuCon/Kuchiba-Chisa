"""Admin grant/revoke of Chia-con, its expiry and the mode downgrade (ROLE-001..003, 006)."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from authz_fakes import NOW, FakeRepo, MemoryCache, RecordingAudit
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.application.dependencies import get_authz_service
from app.application.security.authz_service import AuthzService
from app.application.security.role_expiry import RoleExpirySweeper
from app.domain.models.rbac import (
    EXPIRY_ACTOR,
    ROLE_PERMISSIONS,
    AccountStatus,
    Role,
    RoleAssignment,
    RoleAuditAction,
)
from app.domain.value_objects.principal import PrincipalContext
from app.infrastructure.database.engine import get_db_session
from app.interface.api.dependencies.security import (
    get_current_principal,
    get_effective_permissions,
    require_step_up_mfa,
)
from app.interface.api.routes import admin_roles

TARGET = uuid.uuid4()
ADMIN_ID = str(uuid.uuid4())
BASE = f"/api/v2/admin/accounts/{TARGET}"
GRANT = {"reason": "trusted tester"}


def _service(repo: FakeRepo, audit: RecordingAudit, cache: MemoryCache | None = None):
    return AuthzService(
        repo_factory=lambda session: repo,
        cache=cache or MemoryCache(),
        audit=audit,
        clock=lambda: NOW,
    )


def _client(role: Role, repo: FakeRepo, audit: RecordingAudit) -> TestClient:
    app = FastAPI()
    app.include_router(admin_roles.router, prefix="/api/v2")
    principal = PrincipalContext(
        subject_id=ADMIN_ID,
        tenant_id=None,
        channel_id=None,
        source="web",
        kind="user",
        scopes=frozenset({"chat:write"}),
        authentication="account",
        authz_ver=1,
    )

    async def no_session():
        yield None

    app.dependency_overrides[get_current_principal] = lambda: principal
    app.dependency_overrides[get_effective_permissions] = lambda: ROLE_PERMISSIONS[role]
    app.dependency_overrides[get_authz_service] = lambda: _service(repo, audit)
    app.dependency_overrides[get_db_session] = no_session
    # Step-up behaviour has its own tests in test_admin_mfa.py.
    app.dependency_overrides[require_step_up_mfa] = lambda: None
    return TestClient(app)


@pytest.mark.parametrize("role", [Role.MEMBER, Role.CHIA_CON])
@pytest.mark.parametrize("action", ["grant", "revoke"])
def test_member_and_chia_con_get_403_on_role_changes(role, action) -> None:
    repo, audit = FakeRepo(), RecordingAudit()

    response = _client(role, repo, audit).post(f"{BASE}/roles/chia-con/{action}", json=GRANT)

    assert response.status_code == 403
    assert repo.assignments == []
    assert audit.events == []


def test_member_cannot_read_the_account_summary() -> None:
    client = _client(Role.MEMBER, FakeRepo(), RecordingAudit())

    assert client.get(f"{BASE}/summary").status_code == 403


def test_admin_grant_records_the_assignment_and_an_audit_event() -> None:
    repo, audit = FakeRepo(), RecordingAudit()
    expires = (NOW + timedelta(days=7)).isoformat()

    response = _client(Role.ADMIN, repo, audit).post(
        f"{BASE}/roles/chia-con/grant", json={**GRANT, "expires_at": expires}
    )

    assert response.status_code == 200
    assert repo.assignments[0].granted_by == ADMIN_ID
    assert repo.authz_ver == 2
    assert [e.action for e in audit.events] == [RoleAuditAction.GRANT]
    assert audit.events[0].reason == "trusted tester"


@pytest.mark.parametrize("body", [{}, {"reason": ""}, {"reason": "   "}])
def test_grant_without_a_reason_is_rejected(body) -> None:
    repo = FakeRepo()

    response = _client(Role.ADMIN, repo, RecordingAudit()).post(
        f"{BASE}/roles/chia-con/grant", json=body
    )

    assert response.status_code == 422
    assert repo.assignments == []


def test_revoke_without_a_reason_is_rejected() -> None:
    response = _client(Role.ADMIN, FakeRepo(), RecordingAudit()).post(
        f"{BASE}/roles/chia-con/revoke", json={}
    )

    assert response.status_code == 422


def test_grant_with_a_naive_expiry_is_rejected() -> None:
    response = _client(Role.ADMIN, FakeRepo(), RecordingAudit()).post(
        f"{BASE}/roles/chia-con/grant", json={**GRANT, "expires_at": "2030-01-01T00:00:00"}
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("repo", "code"),
    [
        (FakeRepo(AccountStatus.SUSPENDED), "account_not_active"),
        (FakeRepo(email_verified=False), "identity_not_verified"),
    ],
)
def test_ineligible_account_is_rejected_with_a_reason_code(repo, code) -> None:
    audit = RecordingAudit()

    response = _client(Role.ADMIN, repo, audit).post(f"{BASE}/roles/chia-con/grant", json=GRANT)

    assert response.status_code == 409
    assert response.json()["detail"] == {"code": code}
    assert repo.assignments == [] and audit.events == []


def test_a_linked_provider_counts_as_a_verified_identity() -> None:
    repo = FakeRepo(email_verified=False)
    repo.providers = ("google",)

    response = _client(Role.ADMIN, repo, RecordingAudit()).post(
        f"{BASE}/roles/chia-con/grant", json=GRANT
    )

    assert response.status_code == 200


def test_unknown_account_is_not_found() -> None:
    repo = FakeRepo()
    repo.known = False
    client = _client(Role.ADMIN, repo, RecordingAudit())

    assert client.post(f"{BASE}/roles/chia-con/grant", json=GRANT).status_code == 404
    assert client.get(f"{BASE}/summary").status_code == 404


def test_summary_shows_a_masked_email_and_no_secrets() -> None:
    repo = FakeRepo()
    repo.providers = ("google",)

    body = _client(Role.ADMIN, repo, RecordingAudit()).get(f"{BASE}/summary").json()

    assert body["masked_email"] == "s***@example.com"
    assert body["linked_providers"] == ["google"]
    assert body["email_verified"] is True
    assert "senpai@example.com" not in str(body)


def test_revoke_removes_the_role_and_audits_it() -> None:
    repo, audit = FakeRepo(), RecordingAudit()
    client = _client(Role.ADMIN, repo, audit)
    client.post(f"{BASE}/roles/chia-con/grant", json=GRANT)

    response = client.post(f"{BASE}/roles/chia-con/revoke", json={"reason": "abuse"})

    assert response.json()["revoked"] is True
    assert repo.assignments[0].revoked_by == ADMIN_ID
    assert [e.action for e in audit.events] == [RoleAuditAction.GRANT, RoleAuditAction.REVOKE]


def _assignment(account_id: uuid.UUID, expires_at) -> RoleAssignment:
    return RoleAssignment(
        account_id=account_id,
        role=Role.CHIA_CON,
        granted_by=ADMIN_ID,
        granted_at=NOW - timedelta(days=2),
        reason="beta",
        expires_at=expires_at,
    )


class _Session:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None

    async def commit(self):
        return None


@pytest.mark.asyncio
async def test_expiry_job_revokes_bumps_the_version_and_audits() -> None:
    repo, audit = FakeRepo(), RecordingAudit()
    repo.assignments = [
        _assignment(TARGET, NOW - timedelta(minutes=1)),
        _assignment(uuid.uuid4(), NOW + timedelta(days=1)),
    ]

    swept = await RoleExpirySweeper(_service(repo, audit), _Session).sweep_once()

    assert swept == 1
    assert repo.assignments[0].revoked_by == EXPIRY_ACTOR
    assert repo.assignments[1].revoked_at is None
    assert repo.authz_ver == 2
    assert [(e.action, e.actor, e.account_id) for e in audit.events] == [
        (RoleAuditAction.EXPIRE, EXPIRY_ACTOR, TARGET)
    ]


@pytest.mark.asyncio
async def test_expiry_job_with_nothing_expired_changes_nothing() -> None:
    repo, audit = FakeRepo(), RecordingAudit()

    assert await _service(repo, audit).expire_assignments(None) == 0
    assert repo.authz_ver == 1 and audit.events == []
