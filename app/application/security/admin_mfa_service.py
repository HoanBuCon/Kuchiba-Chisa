"""Admin TOTP enrollment, verification and step-up freshness (SEC-ADM-002/006/010)."""

from __future__ import annotations

import secrets
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, NoReturn

from app.domain.interfaces.admin_mfa import IMfaRepository, IMfaSecretVault, ITotpEngine
from app.domain.models.admin_mfa import (
    ISSUER,
    LOCKOUT_DURATION,
    MAX_FAILED_ATTEMPTS,
    RECOVERY_CODE_COUNT,
    TOTP_DRIFT_STEPS,
    MfaFactor,
    is_step_up_fresh,
)

RECOVERY_CODE_BYTES = 8


class MfaAlreadyEnrolledError(Exception):
    """A confirmed factor exists; changing it is a separate, reviewed flow."""


class MfaNotEnrolledError(Exception):
    """The account has no confirmed factor to verify against."""


class MfaEnrollmentNotPendingError(Exception):
    """There is no unconfirmed factor to confirm."""


class MfaLockedError(Exception):
    """Too many wrong codes; try again after the lock expires."""


class InvalidMfaCodeError(Exception):
    """Wrong, replayed or malformed code. Deliberately carries no detail."""


@dataclass(frozen=True, slots=True)
class Enrollment:
    secret: str
    provisioning_uri: str


class AdminMfaService:
    def __init__(
        self,
        *,
        repo_factory: Callable[[Any], IMfaRepository],
        totp: ITotpEngine,
        vault: IMfaSecretVault,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._repo_factory = repo_factory
        self._totp = totp
        self._vault = vault
        self._clock = clock

    async def begin_enrollment(self, session: Any, account_id: uuid.UUID) -> Enrollment:
        repo = self._repo_factory(session)
        factor = await repo.get_factor(account_id)
        if factor is not None and factor.is_confirmed:
            raise MfaAlreadyEnrolledError
        secret = self._totp.new_secret()
        await repo.save_pending_factor(account_id, self._vault.seal(secret), self._clock())
        return Enrollment(secret, self._totp.provisioning_uri(secret, str(account_id), ISSUER))

    async def confirm_enrollment(
        self, session: Any, account_id: uuid.UUID, session_id: uuid.UUID, code: str
    ) -> list[str]:
        """Confirm with a first valid code; returns the one-time recovery codes, shown once."""
        repo = self._repo_factory(session)
        factor = await repo.get_factor(account_id)
        if factor is None or factor.is_confirmed:
            raise MfaEnrollmentNotPendingError
        now = self._clock()
        await self._check_totp(session, repo, factor, code, now)
        await repo.confirm_factor(account_id, now)
        codes = [secrets.token_hex(RECOVERY_CODE_BYTES) for _ in range(RECOVERY_CODE_COUNT)]
        await repo.replace_recovery_codes(account_id, [self._vault.digest(c) for c in codes], now)
        await repo.mark_step_up(session_id, account_id, now)
        return codes

    async def verify(
        self, session: Any, account_id: uuid.UUID, session_id: uuid.UUID, code: str
    ) -> None:
        repo = self._repo_factory(session)
        factor = await self._confirmed_factor(repo, account_id)
        now = self._clock()
        await self._check_totp(session, repo, factor, code, now)
        await repo.mark_step_up(session_id, account_id, now)

    async def verify_recovery_code(
        self, session: Any, account_id: uuid.UUID, session_id: uuid.UUID, recovery_code: str
    ) -> None:
        repo = self._repo_factory(session)
        factor = await self._confirmed_factor(repo, account_id)
        now = self._clock()
        self._require_unlocked(factor, now)
        digest = self._vault.digest(_normalise_recovery_code(recovery_code))
        if not await repo.consume_recovery_code(account_id, digest, now):
            await self._reject(session, repo, account_id, now)
        await repo.reset_failures(account_id)
        await repo.mark_step_up(session_id, account_id, now)

    async def has_fresh_step_up(
        self, session: Any, account_id: uuid.UUID, session_id: uuid.UUID
    ) -> bool:
        verified_at = await self._repo_factory(session).step_up_verified_at(
            session_id, account_id
        )
        return is_step_up_fresh(verified_at, self._clock())

    async def _check_totp(
        self, session: Any, repo: IMfaRepository, factor: MfaFactor, code: str, now: datetime
    ) -> None:
        self._require_unlocked(factor, now)
        step = self._totp.matching_step(
            self._vault.unseal(factor.secret_sealed), code.strip(), now, TOTP_DRIFT_STEPS
        )
        if step is None or not await repo.claim_step(factor.account_id, step):
            await self._reject(session, repo, factor.account_id, now)
        await repo.reset_failures(factor.account_id)

    async def _reject(
        self, session: Any, repo: IMfaRepository, account_id: uuid.UUID, now: datetime
    ) -> NoReturn:
        if await repo.add_failure(account_id) >= MAX_FAILED_ATTEMPTS:
            await repo.lock(account_id, now + LOCKOUT_DURATION)
        # The request dependency rolls back on error, which would erase the failure count.
        await session.commit()
        raise InvalidMfaCodeError

    @staticmethod
    def _require_unlocked(factor: MfaFactor, now: datetime) -> None:
        if factor.is_locked(now):
            raise MfaLockedError

    @staticmethod
    async def _confirmed_factor(repo: IMfaRepository, account_id: uuid.UUID) -> MfaFactor:
        factor = await repo.get_factor(account_id)
        if factor is None or not factor.is_confirmed:
            raise MfaNotEnrolledError
        return factor


def _normalise_recovery_code(code: str) -> str:
    return code.replace("-", "").replace(" ", "").lower()
