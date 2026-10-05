"""Account persistence against isolated PostgreSQL (Alembic head schema)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, func, select

from app.domain.interfaces.accounts import (
    EmailAlreadyRegisteredError,
    ExternalIdentityAlreadyLinkedError,
)
from app.domain.models.account import VerifiedExternalIdentity
from app.infrastructure.database.engine import AsyncSessionFactory
from app.infrastructure.database.models.account import AccountModel, AuthSessionModel
from app.infrastructure.database.repositories.account_repository import (
    SqlAlchemyAccountRepository,
)


def _email() -> str:
    return f"it-{uuid.uuid4().hex[:12]}@example.test"


async def _cleanup(*emails: str) -> None:
    async with AsyncSessionFactory() as session:
        await session.execute(delete(AccountModel).where(AccountModel.email.in_(emails)))
        await session.commit()


@pytest.mark.asyncio
async def test_migration_creates_no_default_accounts() -> None:
    async with AsyncSessionFactory() as session:
        seeded = await session.scalar(
            select(func.count()).select_from(AccountModel).where(
                AccountModel.email.not_like("it-%@example.test")
            )
        )
    assert seeded == 0


@pytest.mark.asyncio
async def test_unique_email_is_enforced_by_the_database() -> None:
    email = _email()
    try:
        async with AsyncSessionFactory() as session:
            repo = SqlAlchemyAccountRepository(session)
            created = await repo.create_password_account(email, "$2b$12$hash")
            with pytest.raises(EmailAlreadyRegisteredError):
                await repo.create_password_account(email, "$2b$12$other")
            await session.commit()
        async with AsyncSessionFactory() as session:
            credentials = await SqlAlchemyAccountRepository(session).get_credentials_by_email(email)
        assert credentials is not None and credentials.account.id == created.id
        assert credentials.password_hash == "$2b$12$hash"
    finally:
        await _cleanup(email)


@pytest.mark.asyncio
async def test_external_identity_is_unique_per_subject_and_per_account() -> None:
    first, second = _email(), _email()
    subject = f"sub-{uuid.uuid4().hex}"
    identity = VerifiedExternalIdentity("google", subject, first, True)
    try:
        async with AsyncSessionFactory() as session:
            repo = SqlAlchemyAccountRepository(session)
            google_account = await repo.create_external_account(identity)
            other = await repo.create_password_account(second, "$2b$12$hash")
            with pytest.raises(ExternalIdentityAlreadyLinkedError):
                await repo.link_external_identity(other.id, identity)
            with pytest.raises(ExternalIdentityAlreadyLinkedError):
                await repo.link_external_identity(
                    google_account.id,
                    VerifiedExternalIdentity("google", f"sub-{uuid.uuid4().hex}", first, True),
                )
            await session.commit()
        async with AsyncSessionFactory() as session:
            found = await SqlAlchemyAccountRepository(session).get_by_external_identity(
                "google", subject
            )
        assert found is not None and found.id == google_account.id
        assert found.linked_providers == ("google",)
    finally:
        await _cleanup(first, second)


@pytest.mark.asyncio
async def test_refresh_session_rotation_and_revocation_are_atomic() -> None:
    email = _email()
    now = datetime.now(UTC)
    try:
        async with AsyncSessionFactory() as session:
            repo = SqlAlchemyAccountRepository(session)
            account = await repo.create_password_account(email, "$2b$12$hash")
            record = await repo.create_session(
                account.id, "a" * 64, now + timedelta(days=7), "password"
            )
            assert await repo.rotate_session_token(record.id, "a" * 64, "b" * 64, now)
            assert not await repo.rotate_session_token(record.id, "a" * 64, "c" * 64, now)
            await repo.revoke_session(record.id, now)
            assert not await repo.rotate_session_token(record.id, "b" * 64, "d" * 64, now)
            await session.commit()
        async with AsyncSessionFactory() as session:
            stored = await session.get(AuthSessionModel, record.id)
        assert stored is not None
        assert stored.token_hash == "b" * 64
        assert stored.revoked_at is not None
    finally:
        await _cleanup(email)


@pytest.mark.asyncio
async def test_account_tokens_are_single_use_expiring_and_hash_only() -> None:
    email = _email()
    now = datetime.now(UTC)
    try:
        async with AsyncSessionFactory() as session:
            repo = SqlAlchemyAccountRepository(session)
            account = await repo.create_password_account(email, "$2b$12$hash")
            await repo.create_account_token(
                account.id, "password_reset", "a" * 64, now + timedelta(minutes=30), now
            )
            await repo.create_account_token(
                account.id, "password_reset", "b" * 64, now - timedelta(seconds=1), now
            )
            await session.commit()

        async with AsyncSessionFactory() as session:
            repo = SqlAlchemyAccountRepository(session)
            # Wrong purpose, expired, then the valid one exactly once.
            assert await repo.consume_account_token("verify_email", "a" * 64, now) is None
            assert await repo.consume_account_token("password_reset", "b" * 64, now) is None
            assert await repo.consume_account_token("password_reset", "a" * 64, now) == account.id
            assert await repo.consume_account_token("password_reset", "a" * 64, now) is None
            count, latest = await repo.account_token_activity(
                account.id, "password_reset", now - timedelta(days=1)
            )
            assert count == 2 and latest is not None
            await session.commit()
    finally:
        await _cleanup(email)


@pytest.mark.asyncio
async def test_revoke_all_sessions_and_mark_verified() -> None:
    email = _email()
    now = datetime.now(UTC)
    try:
        async with AsyncSessionFactory() as session:
            repo = SqlAlchemyAccountRepository(session)
            account = await repo.create_password_account(email, "$2b$12$hash")
            for marker in "cd":
                await repo.create_session(
                    account.id, marker * 64, now + timedelta(days=7), "password"
                )
            assert await repo.revoke_all_sessions(account.id, now) == 2
            assert await repo.revoke_all_sessions(account.id, now) == 0
            await repo.mark_email_verified(account.id)
            assert await repo.account_exists(account.id) is True
            assert await repo.account_exists(uuid.uuid4()) is False
            credentials = await repo.get_credentials_by_id(account.id)
            assert credentials is not None and credentials.account.email_verified is True
            await session.commit()
    finally:
        await _cleanup(email)
