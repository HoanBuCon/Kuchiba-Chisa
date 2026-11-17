"""SQLAlchemy persistence for Admin MFA factors, recovery codes and step-ups."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import delete, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.interfaces.admin_mfa import IMfaRepository
from app.domain.models.admin_mfa import MfaFactor
from app.infrastructure.database.models.admin_mfa import (
    AdminMfaFactorModel,
    AdminRecoveryCodeModel,
    AdminStepUpModel,
)


class SqlAlchemyMfaRepository(IMfaRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_factor(self, account_id: uuid.UUID) -> MfaFactor | None:
        row = await self.session.get(AdminMfaFactorModel, account_id)
        if row is None:
            return None
        return MfaFactor(
            account_id=account_id,
            secret_sealed=row.secret_sealed,
            confirmed_at=row.confirmed_at,
            last_used_step=row.last_used_step,
            failed_attempts=row.failed_attempts,
            locked_until=row.locked_until,
        )

    async def save_pending_factor(
        self, account_id: uuid.UUID, secret_sealed: str, now: datetime
    ) -> None:
        statement = insert(AdminMfaFactorModel).values(
            account_id=account_id, secret_sealed=secret_sealed
        )
        # Only an unconfirmed factor may be replaced; confirmed ones are guarded by the service.
        await self.session.execute(
            statement.on_conflict_do_update(
                index_elements=[AdminMfaFactorModel.account_id],
                set_={"secret_sealed": secret_sealed, "last_used_step": None},
                where=AdminMfaFactorModel.confirmed_at.is_(None),
            )
        )

    async def confirm_factor(self, account_id: uuid.UUID, now: datetime) -> None:
        await self.session.execute(
            update(AdminMfaFactorModel)
            .where(AdminMfaFactorModel.account_id == account_id)
            .values(confirmed_at=now)
        )

    async def claim_step(self, account_id: uuid.UUID, step: int) -> bool:
        result = await self.session.execute(
            update(AdminMfaFactorModel)
            .where(
                AdminMfaFactorModel.account_id == account_id,
                or_(
                    AdminMfaFactorModel.last_used_step.is_(None),
                    AdminMfaFactorModel.last_used_step < step,
                ),
            )
            .values(last_used_step=step)
        )
        return result.rowcount == 1  # type: ignore[attr-defined]

    async def add_failure(self, account_id: uuid.UUID) -> int:
        result = await self.session.execute(
            update(AdminMfaFactorModel)
            .where(AdminMfaFactorModel.account_id == account_id)
            .values(failed_attempts=AdminMfaFactorModel.failed_attempts + 1)
            .returning(AdminMfaFactorModel.failed_attempts)
        )
        return int(result.scalar_one())

    async def lock(self, account_id: uuid.UUID, until: datetime) -> None:
        await self.session.execute(
            update(AdminMfaFactorModel)
            .where(AdminMfaFactorModel.account_id == account_id)
            .values(locked_until=until, failed_attempts=0)
        )

    async def reset_failures(self, account_id: uuid.UUID) -> None:
        await self.session.execute(
            update(AdminMfaFactorModel)
            .where(AdminMfaFactorModel.account_id == account_id)
            .values(failed_attempts=0)
        )

    async def replace_recovery_codes(
        self, account_id: uuid.UUID, digests: list[str], now: datetime
    ) -> None:
        await self.session.execute(
            delete(AdminRecoveryCodeModel).where(AdminRecoveryCodeModel.account_id == account_id)
        )
        self.session.add_all(
            AdminRecoveryCodeModel(account_id=account_id, code_digest=digest) for digest in digests
        )

    async def consume_recovery_code(
        self, account_id: uuid.UUID, digest: str, now: datetime
    ) -> bool:
        result = await self.session.execute(
            update(AdminRecoveryCodeModel)
            .where(
                AdminRecoveryCodeModel.account_id == account_id,
                AdminRecoveryCodeModel.code_digest == digest,
                AdminRecoveryCodeModel.used_at.is_(None),
            )
            .values(used_at=now)
        )
        return result.rowcount == 1  # type: ignore[attr-defined]

    async def mark_step_up(
        self, session_id: uuid.UUID, account_id: uuid.UUID, now: datetime
    ) -> None:
        statement = insert(AdminStepUpModel).values(
            session_id=session_id, account_id=account_id, verified_at=now
        )
        await self.session.execute(
            statement.on_conflict_do_update(
                index_elements=[AdminStepUpModel.session_id],
                set_={"account_id": account_id, "verified_at": now},
            )
        )

    async def step_up_verified_at(
        self, session_id: uuid.UUID, account_id: uuid.UUID
    ) -> datetime | None:
        return await self.session.scalar(
            select(AdminStepUpModel.verified_at).where(
                AdminStepUpModel.session_id == session_id,
                AdminStepUpModel.account_id == account_id,
            )
        )
