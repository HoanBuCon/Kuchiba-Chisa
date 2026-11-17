"""In-memory MFA repository for Admin MFA tests."""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import datetime

from app.domain.interfaces.admin_mfa import IMfaRepository
from app.domain.models.admin_mfa import MfaFactor


class FakeMfaRepo(IMfaRepository):
    def __init__(self) -> None:
        self.factors: dict[uuid.UUID, MfaFactor] = {}
        self.recovery: dict[uuid.UUID, dict[str, bool]] = {}
        self.step_ups: dict[uuid.UUID, tuple[uuid.UUID, datetime]] = {}

    async def get_factor(self, account_id):
        return self.factors.get(account_id)

    async def save_pending_factor(self, account_id, secret_sealed, now):
        self.factors[account_id] = MfaFactor(account_id, secret_sealed, None, None, 0, None)

    async def confirm_factor(self, account_id, now):
        self._update(account_id, confirmed_at=now)

    async def claim_step(self, account_id, step):
        used = self.factors[account_id].last_used_step
        if used is not None and used >= step:
            return False
        self._update(account_id, last_used_step=step)
        return True

    async def add_failure(self, account_id):
        count = self.factors[account_id].failed_attempts + 1
        self._update(account_id, failed_attempts=count)
        return count

    async def lock(self, account_id, until):
        self._update(account_id, locked_until=until, failed_attempts=0)

    async def reset_failures(self, account_id):
        self._update(account_id, failed_attempts=0)

    async def replace_recovery_codes(self, account_id, digests, now):
        self.recovery[account_id] = dict.fromkeys(digests, False)

    async def consume_recovery_code(self, account_id, digest, now):
        codes = self.recovery.get(account_id, {})
        if codes.get(digest) is False:
            codes[digest] = True
            return True
        return False

    async def mark_step_up(self, session_id, account_id, now):
        self.step_ups[session_id] = (account_id, now)

    async def step_up_verified_at(self, session_id, account_id):
        owner, verified_at = self.step_ups.get(session_id, (None, None))
        return verified_at if owner == account_id else None

    def _update(self, account_id, **changes) -> None:
        self.factors[account_id] = replace(self.factors[account_id], **changes)


class FakeSession:
    """Stands in for the DB session; counts the commits the service makes on failure."""

    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1
