"""Admin TOTP, recovery codes and the step-up gate (SEC-ADM-002/006/010, ROLE-004)."""

from __future__ import annotations

import sys
import uuid
from datetime import timedelta

import pyotp
import pytest
from authz_fakes import NOW, FakeRepo, MemoryCache, RecordingAudit
from fastapi import FastAPI
from fastapi.testclient import TestClient
from mfa_fakes import FakeMfaRepo, FakeSession

from app.application.dependencies import get_admin_mfa_service, get_authz_service
from app.application.security.admin_mfa_service import (
    AdminMfaService,
    InvalidMfaCodeError,
    MfaAlreadyEnrolledError,
    MfaLockedError,
)
from app.application.security.authz_service import AuthzService, RoleChangeRejectedError
from app.domain.models.admin_mfa import MAX_FAILED_ATTEMPTS, STEP_UP_WINDOW
from app.domain.models.rbac import ROLE_PERMISSIONS, Role
from app.domain.value_objects.principal import PrincipalContext
from app.infrastructure.database.engine import get_db_session
from app.infrastructure.security.totp_engine import DerivedKeyMfaSecretVault, PyOtpTotpEngine
from app.interface.api.dependencies.security import (
    get_current_principal,
    get_effective_permissions,
)
from app.interface.api.routes import admin_mfa, admin_roles
from app.ops import admin_role_cli

ACCOUNT = uuid.uuid4()
SESSION_ID = uuid.uuid4()
TARGET = uuid.uuid4()
SERVER_SECRET = "x" * 40
GRANT_URL = f"/api/v2/admin/accounts/{TARGET}/roles/chia-con/grant"
REVOKE_URL = f"/api/v2/admin/accounts/{TARGET}/roles/chia-con/revoke"
MFA_URL = "/api/v2/admin/mfa"


class Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self):
        return self.now


def _service(repo: FakeMfaRepo, clock: Clock) -> AdminMfaService:
    return AdminMfaService(
        repo_factory=lambda session: repo,
        totp=PyOtpTotpEngine(),
        vault=DerivedKeyMfaSecretVault(SERVER_SECRET),
        clock=clock,
    )


def _code(secret: str, clock: Clock, offset_steps: int = 0) -> str:
    return pyotp.TOTP(secret).at(clock.now + timedelta(seconds=30 * offset_steps))


async def _enrolled(repo: FakeMfaRepo, clock: Clock):
    service = _service(repo, clock)
    enrollment = await service.begin_enrollment(FakeSession(), ACCOUNT)
    codes = await service.confirm_enrollment(
        FakeSession(), ACCOUNT, SESSION_ID, _code(enrollment.secret, clock)
    )
    return service, enrollment.secret, codes


@pytest.mark.asyncio
async def test_enrollment_confirms_with_a_code_and_issues_recovery_codes() -> None:
    repo, clock = FakeMfaRepo(), Clock()

    service, secret, codes = await _enrolled(repo, clock)

    assert repo.factors[ACCOUNT].is_confirmed
    assert len(codes) == 10 and len(set(codes)) == 10
    assert await service.has_fresh_step_up(FakeSession(), ACCOUNT, SESSION_ID)
    assert secret not in repo.factors[ACCOUNT].secret_sealed
    assert all(code not in str(repo.recovery[ACCOUNT]) for code in codes)


@pytest.mark.asyncio
async def test_provisioning_uri_names_the_issuer_and_carries_the_secret() -> None:
    enrollment = await _service(FakeMfaRepo(), Clock()).begin_enrollment(FakeSession(), ACCOUNT)

    assert enrollment.provisioning_uri.startswith("otpauth://totp/")
    assert "Kuchiba%20Chisa" in enrollment.provisioning_uri
    assert f"secret={enrollment.secret}" in enrollment.provisioning_uri


@pytest.mark.asyncio
async def test_enrolling_again_after_confirmation_is_refused() -> None:
    service, _, _ = await _enrolled(FakeMfaRepo(), Clock())

    with pytest.raises(MfaAlreadyEnrolledError):
        await service.begin_enrollment(FakeSession(), ACCOUNT)


@pytest.mark.asyncio
async def test_a_wrong_code_does_not_confirm_enrollment() -> None:
    repo, clock = FakeMfaRepo(), Clock()
    service = _service(repo, clock)
    await service.begin_enrollment(FakeSession(), ACCOUNT)
    session = FakeSession()

    with pytest.raises(InvalidMfaCodeError):
        await service.confirm_enrollment(session, ACCOUNT, SESSION_ID, "abcdef")

    assert not repo.factors[ACCOUNT].is_confirmed
    assert session.commits == 1


@pytest.mark.asyncio
async def test_verify_accepts_a_neighbouring_step_and_rejects_a_far_one() -> None:
    repo, clock = FakeMfaRepo(), Clock()
    service, secret, _ = await _enrolled(repo, clock)
    clock.now += timedelta(seconds=90)

    await service.verify(FakeSession(), ACCOUNT, SESSION_ID, _code(secret, clock, 1))
    with pytest.raises(InvalidMfaCodeError):
        await service.verify(FakeSession(), ACCOUNT, SESSION_ID, _code(secret, clock, 3))


@pytest.mark.asyncio
async def test_a_replayed_code_is_rejected_within_its_window() -> None:
    repo, clock = FakeMfaRepo(), Clock()
    service, secret, _ = await _enrolled(repo, clock)
    clock.now += timedelta(seconds=60)
    code = _code(secret, clock)

    await service.verify(FakeSession(), ACCOUNT, SESSION_ID, code)
    with pytest.raises(InvalidMfaCodeError):
        await service.verify(FakeSession(), ACCOUNT, SESSION_ID, code)


@pytest.mark.parametrize("bad", ["", " ", "abcdef", "12345", "1234567", "١٢٣٤٥٦"])
@pytest.mark.asyncio
async def test_malformed_codes_are_rejected(bad) -> None:
    service, _, _ = await _enrolled(FakeMfaRepo(), Clock())

    with pytest.raises(InvalidMfaCodeError):
        await service.verify(FakeSession(), ACCOUNT, SESSION_ID, bad)


@pytest.mark.asyncio
async def test_repeated_wrong_codes_lock_the_factor_even_for_a_right_code() -> None:
    repo, clock = FakeMfaRepo(), Clock()
    service, secret, _ = await _enrolled(repo, clock)
    clock.now += timedelta(seconds=60)

    for _ in range(MAX_FAILED_ATTEMPTS):
        with pytest.raises(InvalidMfaCodeError):
            await service.verify(FakeSession(), ACCOUNT, SESSION_ID, "abcdef")

    with pytest.raises(MfaLockedError):
        await service.verify(FakeSession(), ACCOUNT, SESSION_ID, _code(secret, clock))
    clock.now += timedelta(minutes=16)
    await service.verify(FakeSession(), ACCOUNT, SESSION_ID, _code(secret, clock))


@pytest.mark.asyncio
async def test_a_recovery_code_works_once_and_is_stored_hashed() -> None:
    service, _, codes = await _enrolled(FakeMfaRepo(), Clock())
    other_session = uuid.uuid4()

    await service.verify_recovery_code(FakeSession(), ACCOUNT, other_session, codes[0])
    assert await service.has_fresh_step_up(FakeSession(), ACCOUNT, other_session)
    with pytest.raises(InvalidMfaCodeError):
        await service.verify_recovery_code(FakeSession(), ACCOUNT, other_session, codes[0])
    await service.verify_recovery_code(FakeSession(), ACCOUNT, other_session, codes[1].upper())


@pytest.mark.asyncio
async def test_step_up_expires_after_the_window_and_is_bound_to_its_session() -> None:
    repo, clock = FakeMfaRepo(), Clock()
    service, _, _ = await _enrolled(repo, clock)

    assert not await service.has_fresh_step_up(FakeSession(), ACCOUNT, uuid.uuid4())
    clock.now += STEP_UP_WINDOW
    assert await service.has_fresh_step_up(FakeSession(), ACCOUNT, SESSION_ID)
    clock.now += timedelta(seconds=1)
    assert not await service.has_fresh_step_up(FakeSession(), ACCOUNT, SESSION_ID)


def _client(mfa: AdminMfaService, role: Role = Role.ADMIN):
    repo, audit = FakeRepo(), RecordingAudit()
    authz = AuthzService(
        repo_factory=lambda session: repo, cache=MemoryCache(), audit=audit, clock=lambda: NOW
    )
    principal = PrincipalContext(
        subject_id=str(ACCOUNT),
        tenant_id=None,
        channel_id=None,
        source="web",
        kind="user",
        scopes=frozenset({"chat:write"}),
        authentication="account",
        session_id=str(SESSION_ID),
        authz_ver=1,
    )

    async def fake_session():
        yield FakeSession()

    app = FastAPI()
    app.include_router(admin_roles.router, prefix="/api/v2")
    app.include_router(admin_mfa.router, prefix="/api/v2")
    app.dependency_overrides[get_current_principal] = lambda: principal
    app.dependency_overrides[get_effective_permissions] = lambda: ROLE_PERMISSIONS[role]
    app.dependency_overrides[get_authz_service] = lambda: authz
    app.dependency_overrides[get_admin_mfa_service] = lambda: mfa
    app.dependency_overrides[get_db_session] = fake_session
    return TestClient(app), repo, audit


@pytest.mark.parametrize("url", [GRANT_URL, REVOKE_URL])
@pytest.mark.asyncio
async def test_role_change_without_a_fresh_step_up_is_401(url) -> None:
    repo, clock = FakeMfaRepo(), Clock()
    service, _, _ = await _enrolled(repo, clock)
    clock.now += STEP_UP_WINDOW + timedelta(seconds=1)
    client, authz_repo, audit = _client(service)

    response = client.post(url, json={"reason": "trusted tester"})

    assert response.status_code == 401
    assert response.json()["detail"] == {"code": "step_up_required"}
    assert authz_repo.assignments == [] and audit.events == []


@pytest.mark.asyncio
async def test_role_change_with_a_fresh_step_up_succeeds() -> None:
    service, _, _ = await _enrolled(FakeMfaRepo(), Clock())
    client, authz_repo, _ = _client(service)

    response = client.post(GRANT_URL, json={"reason": "trusted tester"})

    assert response.status_code == 200
    assert len(authz_repo.assignments) == 1


@pytest.mark.asyncio
async def test_verify_route_refreshes_a_stale_step_up() -> None:
    repo, clock = FakeMfaRepo(), Clock()
    service, secret, _ = await _enrolled(repo, clock)
    clock.now += timedelta(minutes=10)
    client, _, _ = _client(service)
    assert client.post(GRANT_URL, json={"reason": "r"}).status_code == 401

    wrong = client.post(f"{MFA_URL}/verify", json={"code": "abcdef"})
    ok = client.post(f"{MFA_URL}/verify", json={"code": _code(secret, clock)})

    assert wrong.status_code == 401 and wrong.json()["detail"] == {"code": "invalid_mfa_code"}
    assert ok.status_code == 200
    assert client.post(GRANT_URL, json={"reason": "r"}).status_code == 200


def test_enroll_route_is_admin_only_and_returns_the_secret_once() -> None:
    service = _service(FakeMfaRepo(), Clock())
    member, _, _ = _client(service, Role.CHIA_CON)
    admin, _, _ = _client(service)

    assert member.post(f"{MFA_URL}/enroll").status_code == 403
    body = admin.post(f"{MFA_URL}/enroll").json()
    assert body["provisioning_uri"].startswith("otpauth://totp/")
    confirm = admin.post(
        f"{MFA_URL}/enroll/confirm", json={"code": pyotp.TOTP(body["secret"]).at(NOW)}
    )
    assert confirm.status_code == 200 and len(confirm.json()["recovery_codes"]) == 10
    assert admin.post(f"{MFA_URL}/enroll").status_code == 409


def _authz(repo: FakeRepo) -> AuthzService:
    return AuthzService(
        repo_factory=lambda session: repo,
        cache=MemoryCache(),
        audit=RecordingAudit(),
        clock=lambda: NOW,
    )


@pytest.mark.asyncio
async def test_cli_grant_makes_an_admin_and_bumps_authz_ver() -> None:
    repo = FakeRepo()
    authz = _authz(repo)

    message = await admin_role_cli.run_command(authz, None, "grant", TARGET, "bootstrap")

    assert "granted admin" in message
    assert repo.assignments[0].role is Role.ADMIN
    assert repo.assignments[0].granted_by.startswith("cli:")
    assert repo.authz_ver == 2
    await admin_role_cli.run_command(authz, None, "revoke", TARGET, "offboarding")
    assert repo.authz_ver == 3 and repo.assignments[0].revoked_at is not None


@pytest.mark.parametrize("reason", ["", "   "])
@pytest.mark.asyncio
async def test_cli_without_a_reason_is_refused(reason) -> None:
    repo = FakeRepo()

    with pytest.raises(RoleChangeRejectedError):
        await admin_role_cli.run_command(_authz(repo), None, "grant", TARGET, reason)

    assert repo.assignments == [] and repo.authz_ver == 1


def test_cli_requires_a_reason_argument() -> None:
    with pytest.raises(SystemExit) as exit_info:
        admin_role_cli.build_parser().parse_args(["grant", "--account-id", str(TARGET)])

    assert exit_info.value.code == 2


def test_cli_refuses_to_run_inside_the_api_process(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "app.main", object())

    with pytest.raises(admin_role_cli.ApiProcessError):
        admin_role_cli.main(["grant", "--account-id", str(TARGET), "--reason", "x"])


def test_no_api_route_changes_the_admin_role() -> None:
    for router in (admin_roles.router, admin_mfa.router):
        assert not [r.path for r in router.routes if "roles/admin" in getattr(r, "path", "")]
