"""Account service policy: registration, login, sessions and external-identity linking."""

from __future__ import annotations

import uuid

import pytest
from account_fakes import Clock, InMemoryAccountRepository, make_service

from app.application.security.accounts import (
    AccountLinkRequiredError,
    ExternalIdentityRejectedError,
    InvalidCredentialsError,
    SessionInvalidError,
    hash_refresh_token,
)
from app.domain.models.account import AccountPolicyError, VerifiedExternalIdentity
from app.infrastructure.security.jwt_authenticator import jwt_authenticator

PASSWORD = "correct horse battery"
SESSION = object()


async def signup(service, email: str = "senpai@example.com", password: str = PASSWORD):
    """Register, verify through the e-mailed token, then sign in (the only path)."""
    outbound = await service.register(SESSION, email, password)
    assert outbound is not None and outbound.kind == "verify_email"
    await service.verify_email(SESSION, outbound.token)
    return await service.login(SESSION, email, password)


def google(subject: str = "google-sub-1", email: str | None = "senpai@gmail.com", verified=True):
    return VerifiedExternalIdentity(
        provider="google", subject=subject, email=email, email_verified=verified
    )


@pytest.mark.asyncio
async def test_register_hashes_password_and_issues_server_derived_identity() -> None:
    repo = InMemoryAccountRepository()
    service = make_service(repo)
    outbound = await service.register(SESSION, "  Senpai@Example.COM ", PASSWORD)
    # Registration never signs in: the account is unverified and an e-mail is queued.
    (row,) = repo.accounts.values()
    assert row.email_verified is False
    assert outbound is not None and outbound.to == "senpai@example.com"
    await service.verify_email(SESSION, outbound.token)
    issued = await service.login(SESSION, "senpai@example.com", PASSWORD)

    assert row.email == "senpai@example.com"
    assert row.password_hash and row.password_hash.startswith("$2")
    assert PASSWORD not in row.password_hash

    principal = jwt_authenticator.authenticate_bearer(f"Bearer {issued.access_token}")
    assert principal.subject_id == str(issued.account.id)
    assert principal.authentication == "account"
    assert principal.session_id == str(issued.session_id)
    assert principal.scopes == frozenset({"chat:clear", "chat:read", "chat:write"})
    # Only the hash of the refresh secret is persisted.
    stored = repo.sessions[issued.session_id]["token_hash"]
    assert stored == hash_refresh_token(issued.refresh_token)
    assert issued.refresh_token not in str(repo.sessions)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("email", "password"),
    (("not-an-email", PASSWORD), ("a@b.co", "short"), ("a@b.co", "x" * 73), ("a@b.co", " " * 12)),
)
async def test_register_validates_email_and_password(email: str, password: str) -> None:
    with pytest.raises(AccountPolicyError):
        await make_service(InMemoryAccountRepository()).register(SESSION, email, password)


@pytest.mark.asyncio
async def test_duplicate_registration_emails_owner_without_new_account() -> None:
    repo = InMemoryAccountRepository()
    service = make_service(repo)
    await signup(service, "senpai@example.com")

    outbound = await service.register(SESSION, "SENPAI@example.com", "another password!")
    # No error (no enumeration) and no second account: the owner gets a reset link,
    # and the registrant's password is discarded.
    assert outbound is not None and outbound.kind == "existing_account"
    assert len(repo.accounts) == 1
    with pytest.raises(InvalidCredentialsError):
        await service.login(SESSION, "senpai@example.com", "another password!")


@pytest.mark.asyncio
async def test_login_succeeds_only_with_the_right_password() -> None:
    repo = InMemoryAccountRepository()
    service = make_service(repo)
    created = await signup(service, "senpai@example.com")

    issued = await service.login(SESSION, "SENPAI@example.com", PASSWORD)
    assert issued.account.id == created.account.id

    with pytest.raises(InvalidCredentialsError) as wrong:
        await service.login(SESSION, "senpai@example.com", "wrong password!!")
    with pytest.raises(InvalidCredentialsError) as unknown:
        await service.login(SESSION, "nobody@example.com", PASSWORD)
    with pytest.raises(InvalidCredentialsError) as malformed:
        await service.login(SESSION, "not an email", PASSWORD)
    # Identical, reason-free errors: login never reveals whether an account exists.
    assert str(wrong.value) == str(unknown.value) == str(malformed.value) == ""


@pytest.mark.asyncio
async def test_google_only_account_cannot_be_used_with_password_login() -> None:
    repo = InMemoryAccountRepository()
    service = make_service(repo)
    await service.sign_in_with_external_identity(SESSION, google())

    with pytest.raises(InvalidCredentialsError):
        await service.login(SESSION, "senpai@gmail.com", PASSWORD)


@pytest.mark.asyncio
async def test_refresh_rotates_secret_and_old_secret_is_rejected() -> None:
    repo = InMemoryAccountRepository()
    service = make_service(repo)
    issued = await signup(service, "senpai@example.com")

    refreshed = await service.refresh(SESSION, issued.refresh_token)
    assert refreshed.refresh_token != issued.refresh_token
    assert refreshed.session_id == issued.session_id

    with pytest.raises(SessionInvalidError):
        await service.refresh(SESSION, issued.refresh_token)
    await service.refresh(SESSION, refreshed.refresh_token)


@pytest.mark.asyncio
async def test_logout_revokes_session_and_expiry_is_enforced() -> None:
    clock = Clock()
    repo = InMemoryAccountRepository()
    service = make_service(repo, clock)
    issued = await signup(service, "senpai@example.com")

    await service.logout(SESSION, issued.refresh_token)
    with pytest.raises(SessionInvalidError):
        await service.refresh(SESSION, issued.refresh_token)

    second = await service.login(SESSION, "senpai@example.com", PASSWORD)
    clock.advance(days=8)
    with pytest.raises(SessionInvalidError):
        await service.refresh(SESSION, second.refresh_token)


@pytest.mark.asyncio
async def test_new_google_identity_creates_account_keyed_by_subject() -> None:
    repo = InMemoryAccountRepository()
    service = make_service(repo)
    first = await service.sign_in_with_external_identity(SESSION, google())
    again = await service.sign_in_with_external_identity(
        SESSION, google(email="changed@gmail.com")
    )

    assert again.account.id == first.account.id
    assert first.account.linked_providers == ("google",)
    assert first.account.has_password is False


@pytest.mark.asyncio
async def test_google_email_collision_never_merges_into_existing_account() -> None:
    repo = InMemoryAccountRepository()
    service = make_service(repo)
    victim = await signup(service, "senpai@gmail.com")

    with pytest.raises(AccountLinkRequiredError):
        await service.sign_in_with_external_identity(SESSION, google(email="Senpai@gmail.com"))
    assert repo.identities == {}
    assert len(repo.accounts) == 1
    assert (await repo.get_by_id(victim.account.id)).linked_providers == ()


@pytest.mark.asyncio
async def test_unverified_google_email_cannot_create_an_account() -> None:
    with pytest.raises(ExternalIdentityRejectedError):
        await make_service(InMemoryAccountRepository()).sign_in_with_external_identity(
            SESSION, google(verified=False)
        )


@pytest.mark.asyncio
async def test_authenticated_account_can_link_google_explicitly() -> None:
    repo = InMemoryAccountRepository()
    service = make_service(repo)
    owner = await signup(service, "senpai@gmail.com")

    linked = await service.sign_in_with_external_identity(
        SESSION, google(), link_to_account_id=owner.account.id
    )
    assert linked.account.id == owner.account.id
    assert linked.account.linked_providers == ("google",)

    via_google = await service.sign_in_with_external_identity(SESSION, google())
    assert via_google.account.id == owner.account.id
    via_password = await service.login(SESSION, "senpai@gmail.com", PASSWORD)
    assert via_password.account.id == owner.account.id


@pytest.mark.asyncio
async def test_google_identity_linked_elsewhere_cannot_be_stolen() -> None:
    repo = InMemoryAccountRepository()
    service = make_service(repo)
    google_owner = await service.sign_in_with_external_identity(SESSION, google())
    attacker = await signup(service, "attacker@example.com")

    with pytest.raises(ExternalIdentityRejectedError):
        await service.sign_in_with_external_identity(
            SESSION, google(), link_to_account_id=attacker.account.id
        )
    assert (await repo.get_by_external_identity("google", "google-sub-1")).id == (
        google_owner.account.id
    )


@pytest.mark.asyncio
async def test_second_google_identity_cannot_be_linked_to_same_account() -> None:
    repo = InMemoryAccountRepository()
    service = make_service(repo)
    owner = await signup(service, "senpai@gmail.com")
    await service.sign_in_with_external_identity(
        SESSION, google(), link_to_account_id=owner.account.id
    )

    with pytest.raises(ExternalIdentityRejectedError):
        await service.sign_in_with_external_identity(
            SESSION, google(subject="other-sub"), link_to_account_id=owner.account.id
        )


@pytest.mark.asyncio
async def test_link_to_unknown_account_is_refused() -> None:
    with pytest.raises(SessionInvalidError):
        await make_service(InMemoryAccountRepository()).sign_in_with_external_identity(
            SESSION, google(), link_to_account_id=uuid.uuid4()
        )


@pytest.mark.asyncio
async def test_account_identity_is_distinct_from_anonymous_web_identity() -> None:
    from app.application.security.anonymous_session import AnonymousWebSessionService

    anonymous = AnonymousWebSessionService(jwt_authenticator, 60).issue()
    issued = await signup(make_service(InMemoryAccountRepository()), "senpai@example.com")

    anon_principal = jwt_authenticator.authenticate_bearer(f"Bearer {anonymous.access_token}")
    account_principal = jwt_authenticator.authenticate_bearer(f"Bearer {issued.access_token}")
    assert anon_principal.authentication == "anonymous"
    assert account_principal.authentication == "account"
    assert anon_principal.subject_id != account_principal.subject_id
