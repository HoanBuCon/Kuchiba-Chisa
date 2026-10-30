"""A-01/A-02: e-mail verification, password reset/change and the e-mail-squat path."""

from __future__ import annotations

import pytest
from account_fakes import Clock, InMemoryAccountRepository, make_service

from app.application.security.accounts import (
    AccountLinkRequiredError,
    AccountTokenInvalidError,
    EmailClaimRequiredError,
    EmailNotVerifiedError,
    InvalidCredentialsError,
    SessionInvalidError,
    hash_account_token,
)
from app.domain.models.account import AccountPolicyError, VerifiedExternalIdentity

PASSWORD = "correct horse battery"
NEW_PASSWORD = "brand new passphrase"
SESSION = object()
EMAIL = "senpai@example.com"


def _setup(clock: Clock | None = None):
    clock = clock or Clock()
    repo = InMemoryAccountRepository()
    return repo, make_service(repo, clock), clock


async def _verified(service, email: str = EMAIL, password: str = PASSWORD):
    outbound = await service.register(SESSION, email, password)
    await service.verify_email(SESSION, outbound.token)
    return await service.login(SESSION, email, password)


# ── E-mail verification ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unverified_account_cannot_sign_in_until_verified() -> None:
    repo, service, _ = _setup()
    outbound = await service.register(SESSION, EMAIL, PASSWORD)

    with pytest.raises(EmailNotVerifiedError):
        await service.login(SESSION, EMAIL, PASSWORD)
    # A wrong password on an unverified account still looks like any other failure.
    with pytest.raises(InvalidCredentialsError):
        await service.login(SESSION, EMAIL, "wrong password!!")
    assert repo.sessions == {}

    await service.verify_email(SESSION, outbound.token)
    issued = await service.login(SESSION, EMAIL, PASSWORD)
    assert issued.account.email_verified is True


@pytest.mark.asyncio
async def test_verification_token_is_single_use_and_expires() -> None:
    _, service, clock = _setup()
    first = await service.register(SESSION, EMAIL, PASSWORD)
    await service.verify_email(SESSION, first.token)
    with pytest.raises(AccountTokenInvalidError):
        await service.verify_email(SESSION, first.token)

    other = await service.register(SESSION, "kohai@example.com", PASSWORD)
    clock.advance(hours=24, seconds=1)
    with pytest.raises(AccountTokenInvalidError):
        await service.verify_email(SESSION, other.token)
    with pytest.raises(AccountTokenInvalidError):
        await service.verify_email(SESSION, "forged-token-value-1234567890")


@pytest.mark.asyncio
async def test_tokens_are_random_and_stored_only_as_hashes() -> None:
    repo, service, _ = _setup()
    outbound = await service.register(SESSION, EMAIL, PASSWORD)

    assert len(outbound.token) >= 43  # 32 random bytes, URL-safe
    assert outbound.token not in str(repo.tokens)
    assert hash_account_token(outbound.token) in repo.tokens


@pytest.mark.asyncio
async def test_reset_token_cannot_be_used_as_verification_token() -> None:
    _, service, _ = _setup()
    await _verified(service)
    reset = await service.request_password_reset(SESSION, EMAIL)
    with pytest.raises(AccountTokenInvalidError):
        await service.verify_email(SESSION, reset.token)


@pytest.mark.asyncio
async def test_resend_verification_has_cooldown_and_daily_limit() -> None:
    _, service, clock = _setup()
    await service.register(SESSION, EMAIL, PASSWORD)

    assert await service.resend_verification(SESSION, EMAIL) is None  # within cooldown
    sent = 1
    for _ in range(10):
        clock.advance(seconds=61)
        if await service.resend_verification(SESSION, EMAIL) is not None:
            sent += 1
    assert sent == 5  # ACCOUNT_EMAIL_DAILY_LIMIT default

    clock.advance(days=1)
    assert await service.resend_verification(SESSION, EMAIL) is not None


@pytest.mark.asyncio
async def test_resend_is_silent_for_unknown_or_verified_addresses() -> None:
    _, service, clock = _setup()
    assert await service.resend_verification(SESSION, "nobody@example.com") is None
    await _verified(service)
    clock.advance(minutes=5)
    assert await service.resend_verification(SESSION, EMAIL) is None


# ── Password reset ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_forgot_password_is_silent_for_unknown_address() -> None:
    repo, service, _ = _setup()
    assert await service.request_password_reset(SESSION, "nobody@example.com") is None
    assert await service.request_password_reset(SESSION, "not an email") is None
    assert repo.tokens == {}


@pytest.mark.asyncio
async def test_password_reset_replaces_password_and_revokes_every_session() -> None:
    repo, service, clock = _setup()
    browser_a = await _verified(service)
    browser_b = await service.login(SESSION, EMAIL, PASSWORD)

    clock.advance(minutes=2)
    outbound = await service.request_password_reset(SESSION, EMAIL)
    assert outbound.kind == "password_reset"
    await service.reset_password(SESSION, outbound.token, NEW_PASSWORD)

    for session in (browser_a, browser_b):
        with pytest.raises(SessionInvalidError):
            await service.refresh(SESSION, session.refresh_token)
    assert all(s["revoked_at"] is not None for s in repo.sessions.values())
    with pytest.raises(InvalidCredentialsError):
        await service.login(SESSION, EMAIL, PASSWORD)
    assert (await service.login(SESSION, EMAIL, NEW_PASSWORD)).account.email == EMAIL


@pytest.mark.asyncio
async def test_reset_token_is_single_use_and_expires_after_30_minutes() -> None:
    _, service, clock = _setup()
    await _verified(service)
    first = await service.request_password_reset(SESSION, EMAIL)
    await service.reset_password(SESSION, first.token, NEW_PASSWORD)
    with pytest.raises(AccountTokenInvalidError):
        await service.reset_password(SESSION, first.token, "another passphrase")

    clock.advance(minutes=2)
    second = await service.request_password_reset(SESSION, EMAIL)
    clock.advance(minutes=30, seconds=1)
    with pytest.raises(AccountTokenInvalidError):
        await service.reset_password(SESSION, second.token, "another passphrase")


@pytest.mark.asyncio
async def test_weak_new_password_does_not_consume_the_reset_token() -> None:
    _, service, _ = _setup()
    await _verified(service)
    outbound = await service.request_password_reset(SESSION, EMAIL)

    with pytest.raises(AccountPolicyError):
        await service.reset_password(SESSION, outbound.token, "short")
    await service.reset_password(SESSION, outbound.token, NEW_PASSWORD)


@pytest.mark.asyncio
async def test_newer_reset_invalidates_older_outstanding_links() -> None:
    _, service, clock = _setup()
    await _verified(service)
    older = await service.request_password_reset(SESSION, EMAIL)
    clock.advance(minutes=2)
    newer = await service.request_password_reset(SESSION, EMAIL)

    await service.reset_password(SESSION, newer.token, NEW_PASSWORD)
    with pytest.raises(AccountTokenInvalidError):
        await service.reset_password(SESSION, older.token, "another passphrase")


@pytest.mark.asyncio
async def test_forgot_password_rate_limit_per_account() -> None:
    _, service, clock = _setup()
    await _verified(service)
    assert await service.request_password_reset(SESSION, EMAIL) is not None
    assert await service.request_password_reset(SESSION, EMAIL) is None  # cooldown
    clock.advance(seconds=61)
    assert await service.request_password_reset(SESSION, EMAIL) is not None


# ── Password change ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_password_change_requires_current_password_and_revokes_other_sessions() -> None:
    _, service, _ = _setup()
    current = await _verified(service)
    other_browser = await service.login(SESSION, EMAIL, PASSWORD)

    with pytest.raises(InvalidCredentialsError):
        await service.change_password(
            SESSION, current.account.id, "wrong password!!", NEW_PASSWORD
        )
    fresh = await service.change_password(SESSION, current.account.id, PASSWORD, NEW_PASSWORD)

    for old in (current, other_browser):
        with pytest.raises(SessionInvalidError):
            await service.refresh(SESSION, old.refresh_token)
    await service.refresh(SESSION, fresh.refresh_token)
    assert (await service.login(SESSION, EMAIL, NEW_PASSWORD)).account.id == current.account.id


@pytest.mark.asyncio
async def test_password_change_enforces_policy() -> None:
    _, service, _ = _setup()
    current = await _verified(service)
    with pytest.raises(AccountPolicyError):
        await service.change_password(SESSION, current.account.id, PASSWORD, "x" * 73)


# ── E-mail squat ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_squatted_address_is_reclaimed_by_mailbox_owner_via_reset() -> None:
    repo, service, clock = _setup()
    # Attacker registers the victim's address with a password the attacker knows.
    squat = await service.register(SESSION, EMAIL, "attacker password!")
    assert squat.kind == "verify_email" and squat.to == EMAIL  # goes to the victim

    # Victim later tries to register: no error, no new account, a *claim* link.
    clock.advance(minutes=2)
    claim = await service.register(SESSION, EMAIL, PASSWORD)
    assert claim.kind == "claim_account" and claim.to == EMAIL
    assert len(repo.accounts) == 1

    await service.reset_password(SESSION, claim.token, PASSWORD)

    with pytest.raises(InvalidCredentialsError):
        await service.login(SESSION, EMAIL, "attacker password!")
    issued = await service.login(SESSION, EMAIL, PASSWORD)
    assert issued.account.email_verified is True
    # The squatter's never-used verification link is dead after the reclaim.
    with pytest.raises(AccountTokenInvalidError):
        await service.verify_email(SESSION, squat.token)


@pytest.mark.asyncio
async def test_forgot_password_on_unverified_address_sends_claim_link() -> None:
    _, service, clock = _setup()
    await service.register(SESSION, EMAIL, "attacker password!")
    clock.advance(minutes=2)
    outbound = await service.request_password_reset(SESSION, EMAIL)
    assert outbound.kind == "claim_account"


@pytest.mark.asyncio
async def test_google_with_address_held_by_unverified_account_requires_claim() -> None:
    repo, service, _ = _setup()
    await service.register(SESSION, "senpai@gmail.com", "attacker password!")
    google = VerifiedExternalIdentity(
        provider="google", subject="g-1", email="senpai@gmail.com", email_verified=True
    )

    with pytest.raises(EmailClaimRequiredError):
        await service.sign_in_with_external_identity(SESSION, google)
    # Never merged, never deleted.
    assert repo.identities == {}
    assert len(repo.accounts) == 1


@pytest.mark.asyncio
async def test_google_with_address_of_verified_account_requires_explicit_link() -> None:
    repo, service, _ = _setup()
    await _verified(service, "senpai@gmail.com")
    google = VerifiedExternalIdentity(
        provider="google", subject="g-1", email="senpai@gmail.com", email_verified=True
    )
    with pytest.raises(AccountLinkRequiredError):
        await service.sign_in_with_external_identity(SESSION, google)
    assert repo.identities == {}
