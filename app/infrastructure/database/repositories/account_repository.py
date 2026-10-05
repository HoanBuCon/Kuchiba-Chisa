"""SQLAlchemy persistence for accounts, identities, refresh sessions and e-mail tokens."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.interfaces.accounts import (
    EmailAlreadyRegisteredError,
    ExternalIdentityAlreadyLinkedError,
    IAccountRepository,
)
from app.domain.models.account import (
    Account,
    AccountCredentials,
    AccountTokenPurpose,
    AuthMethod,
    AuthSessionRecord,
    ExternalProvider,
    VerifiedExternalIdentity,
)
from app.infrastructure.database.models.account import (
    AccountIdentityModel,
    AccountModel,
    AccountTokenModel,
    AuthSessionModel,
)


class SqlAlchemyAccountRepository(IAccountRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _providers(self, account_id: uuid.UUID) -> tuple[ExternalProvider, ...]:
        rows = await self.session.scalars(
            select(AccountIdentityModel.provider).where(
                AccountIdentityModel.account_id == account_id
            )
        )
        return tuple(sorted(rows.all()))  # type: ignore[arg-type]

    async def _to_account(self, row: AccountModel) -> Account:
        return Account(
            id=row.id,
            email=row.email,
            email_verified=row.email_verified,
            has_password=row.password_hash is not None,
            linked_providers=await self._providers(row.id),
            is_active=row.is_active,
        )

    async def get_by_id(self, account_id: uuid.UUID) -> Account | None:
        row = await self.session.get(AccountModel, account_id)
        return await self._to_account(row) if row is not None else None

    async def get_credentials_by_email(self, email: str) -> AccountCredentials | None:
        row = await self.session.scalar(select(AccountModel).where(AccountModel.email == email))
        if row is None:
            return None
        return AccountCredentials(
            account=await self._to_account(row), password_hash=row.password_hash
        )

    async def email_exists(self, email: str) -> bool:
        found = await self.session.scalar(
            select(AccountModel.id).where(AccountModel.email == email)
        )
        return found is not None

    async def get_by_external_identity(
        self, provider: ExternalProvider, subject: str
    ) -> Account | None:
        row = await self.session.scalar(
            select(AccountModel)
            .join(AccountIdentityModel, AccountIdentityModel.account_id == AccountModel.id)
            .where(
                AccountIdentityModel.provider == provider,
                AccountIdentityModel.provider_subject == subject,
            )
        )
        return await self._to_account(row) if row is not None else None

    async def create_password_account(self, email: str, password_hash: str) -> Account:
        row = AccountModel(email=email, email_verified=False, password_hash=password_hash)
        try:
            async with self.session.begin_nested():
                self.session.add(row)
                await self.session.flush()
        except IntegrityError as error:
            raise EmailAlreadyRegisteredError from error
        return await self._to_account(row)

    async def create_external_account(self, identity: VerifiedExternalIdentity) -> Account:
        row = AccountModel(
            email=identity.email,
            email_verified=identity.email_verified,
            password_hash=None,
        )
        try:
            async with self.session.begin_nested():
                self.session.add(row)
                await self.session.flush()
                self.session.add(
                    AccountIdentityModel(
                        account_id=row.id,
                        provider=identity.provider,
                        provider_subject=identity.subject,
                        provider_email=identity.email,
                    )
                )
                await self.session.flush()
        except IntegrityError as error:
            raise EmailAlreadyRegisteredError from error
        return await self._to_account(row)

    async def link_external_identity(
        self, account_id: uuid.UUID, identity: VerifiedExternalIdentity
    ) -> Account:
        try:
            async with self.session.begin_nested():
                self.session.add(
                    AccountIdentityModel(
                        account_id=account_id,
                        provider=identity.provider,
                        provider_subject=identity.subject,
                        provider_email=identity.email,
                    )
                )
                await self.session.flush()
        except IntegrityError as error:
            raise ExternalIdentityAlreadyLinkedError from error
        account = await self.get_by_id(account_id)
        if account is None:  # pragma: no cover - FK guarantees existence
            raise ExternalIdentityAlreadyLinkedError
        return account

    async def update_password_hash(self, account_id: uuid.UUID, password_hash: str) -> None:
        await self.session.execute(
            update(AccountModel)
            .where(AccountModel.id == account_id)
            .values(password_hash=password_hash)
        )

    async def create_session(
        self,
        account_id: uuid.UUID,
        token_hash: str,
        expires_at: datetime,
        auth_method: AuthMethod,
    ) -> AuthSessionRecord:
        row = AuthSessionModel(
            account_id=account_id,
            token_hash=token_hash,
            expires_at=expires_at,
            auth_method=auth_method,
        )
        self.session.add(row)
        await self.session.execute(
            update(AccountModel)
            .where(AccountModel.id == account_id)
            .values(last_login_at=func.now())
        )
        await self.session.flush()
        return _record(row)

    async def get_session_by_token_hash(self, token_hash: str) -> AuthSessionRecord | None:
        row = await self.session.scalar(
            select(AuthSessionModel).where(AuthSessionModel.token_hash == token_hash)
        )
        return _record(row) if row is not None else None

    async def rotate_session_token(
        self, session_id: uuid.UUID, old_token_hash: str, new_token_hash: str, now: datetime
    ) -> bool:
        result = await self.session.execute(
            update(AuthSessionModel)
            .where(
                AuthSessionModel.id == session_id,
                AuthSessionModel.token_hash == old_token_hash,
                AuthSessionModel.revoked_at.is_(None),
            )
            .values(token_hash=new_token_hash, last_used_at=now)
        )
        return bool(result.rowcount)  # type: ignore[attr-defined]

    async def revoke_session(self, session_id: uuid.UUID, now: datetime) -> None:
        await self.session.execute(
            update(AuthSessionModel)
            .where(AuthSessionModel.id == session_id, AuthSessionModel.revoked_at.is_(None))
            .values(revoked_at=now)
        )

    async def revoke_all_sessions(self, account_id: uuid.UUID, now: datetime) -> int:
        result = await self.session.execute(
            update(AuthSessionModel)
            .where(AuthSessionModel.account_id == account_id, AuthSessionModel.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        return int(result.rowcount or 0)  # type: ignore[attr-defined]

    async def account_exists(self, account_id: uuid.UUID) -> bool:
        found = await self.session.scalar(
            select(AccountModel.id).where(AccountModel.id == account_id)
        )
        return found is not None

    async def get_credentials_by_id(self, account_id: uuid.UUID) -> AccountCredentials | None:
        row = await self.session.get(AccountModel, account_id)
        if row is None:
            return None
        return AccountCredentials(
            account=await self._to_account(row), password_hash=row.password_hash
        )

    async def mark_email_verified(self, account_id: uuid.UUID) -> None:
        await self.session.execute(
            update(AccountModel).where(AccountModel.id == account_id).values(email_verified=True)
        )

    async def create_account_token(
        self,
        account_id: uuid.UUID,
        purpose: AccountTokenPurpose,
        token_hash: str,
        expires_at: datetime,
        now: datetime,
    ) -> None:
        self.session.add(
            AccountTokenModel(
                account_id=account_id,
                purpose=purpose,
                token_hash=token_hash,
                created_at=now,
                expires_at=expires_at,
            )
        )
        await self.session.flush()

    async def consume_account_token(
        self, purpose: AccountTokenPurpose, token_hash: str, now: datetime
    ) -> uuid.UUID | None:
        # Single statement: concurrent redemptions cannot both succeed.
        return await self.session.scalar(
            update(AccountTokenModel)
            .where(
                AccountTokenModel.token_hash == token_hash,
                AccountTokenModel.purpose == purpose,
                AccountTokenModel.used_at.is_(None),
                AccountTokenModel.expires_at > now,
            )
            .values(used_at=now)
            .returning(AccountTokenModel.account_id)
        )

    async def invalidate_account_tokens(
        self, account_id: uuid.UUID, purpose: AccountTokenPurpose, now: datetime
    ) -> None:
        await self.session.execute(
            update(AccountTokenModel)
            .where(
                AccountTokenModel.account_id == account_id,
                AccountTokenModel.purpose == purpose,
                AccountTokenModel.used_at.is_(None),
            )
            .values(used_at=now)
        )

    async def account_token_activity(
        self, account_id: uuid.UUID, purpose: AccountTokenPurpose, since: datetime
    ) -> tuple[int, datetime | None]:
        row = (
            await self.session.execute(
                select(
                    func.count(AccountTokenModel.id).filter(AccountTokenModel.created_at >= since),
                    func.max(AccountTokenModel.created_at),
                ).where(
                    AccountTokenModel.account_id == account_id,
                    AccountTokenModel.purpose == purpose,
                )
            )
        ).one()
        return int(row[0] or 0), row[1]


def _record(row: AuthSessionModel) -> AuthSessionRecord:
    return AuthSessionRecord(
        id=row.id,
        account_id=row.account_id,
        expires_at=row.expires_at,
        revoked_at=row.revoked_at,
        auth_method=row.auth_method,  # type: ignore[arg-type]
    )
