"""TOTP factor state and the step-up freshness rule for Admin actions (SEC-ADM-002/006/010)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

# A step-up stays valid for at most this long after the last successful MFA (SEC-ADM-006).
STEP_UP_WINDOW = timedelta(minutes=5)
TOTP_PERIOD_SECONDS = 30
# One neighbouring step on each side absorbs clock drift without widening the guess window much.
TOTP_DRIFT_STEPS = 1
TOTP_DIGITS = 6
# Five wrong codes lock the factor (SEC-ADM-010); the lock duration is fixed for now.
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_DURATION = timedelta(minutes=15)
RECOVERY_CODE_COUNT = 10
ISSUER = "Kuchiba Chisa"


@dataclass(frozen=True, slots=True)
class MfaFactor:
    account_id: uuid.UUID
    secret_sealed: str
    confirmed_at: datetime | None
    # Highest TOTP time-step already accepted; a code for a step at or below it is a replay.
    last_used_step: int | None
    failed_attempts: int
    locked_until: datetime | None

    @property
    def is_confirmed(self) -> bool:
        return self.confirmed_at is not None

    def is_locked(self, now: datetime) -> bool:
        return self.locked_until is not None and self.locked_until > now


def is_step_up_fresh(verified_at: datetime | None, now: datetime) -> bool:
    return verified_at is not None and now - verified_at <= STEP_UP_WINDOW
