"""Ports for Admin TOTP factors, recovery codes and step-up records (SEC-ADM-002/006)."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from datetime import datetime

from app.domain.models.admin_mfa import MfaFactor


class IMfaRepository(ABC):
    @abstractmethod
    async def get_factor(self, account_id: uuid.UUID) -> MfaFactor | None: ...

    @abstractmethod
    async def save_pending_factor(
        self, account_id: uuid.UUID, secret_sealed: str, now: datetime
    ) -> None:
        """Store an unconfirmed factor, replacing any earlier unconfirmed one."""

    @abstractmethod
    async def confirm_factor(self, account_id: uuid.UUID, now: datetime) -> None: ...

    @abstractmethod
    async def claim_step(self, account_id: uuid.UUID, step: int) -> bool:
        """Atomically record ``step`` as used; False when it was already used or is older."""

    @abstractmethod
    async def add_failure(self, account_id: uuid.UUID) -> int:
        """Increment and return the consecutive failure count."""

    @abstractmethod
    async def lock(self, account_id: uuid.UUID, until: datetime) -> None:
        """Lock the factor until ``until`` and reset the failure count."""

    @abstractmethod
    async def reset_failures(self, account_id: uuid.UUID) -> None: ...

    @abstractmethod
    async def replace_recovery_codes(
        self, account_id: uuid.UUID, digests: list[str], now: datetime
    ) -> None: ...

    @abstractmethod
    async def consume_recovery_code(
        self, account_id: uuid.UUID, digest: str, now: datetime
    ) -> bool:
        """Atomically mark an unused code as used; False when unknown or already used."""

    @abstractmethod
    async def mark_step_up(
        self, session_id: uuid.UUID, account_id: uuid.UUID, now: datetime
    ) -> None: ...

    @abstractmethod
    async def step_up_verified_at(
        self, session_id: uuid.UUID, account_id: uuid.UUID
    ) -> datetime | None: ...


class ITotpEngine(ABC):
    @abstractmethod
    def new_secret(self) -> str: ...

    @abstractmethod
    def provisioning_uri(self, secret: str, account_label: str, issuer: str) -> str: ...

    @abstractmethod
    def matching_step(self, secret: str, code: str, now: datetime, drift_steps: int) -> int | None:
        """Return the TOTP time-step the code belongs to within the drift window, else None."""


class IMfaSecretVault(ABC):
    @abstractmethod
    def seal(self, plaintext: str) -> str: ...

    @abstractmethod
    def unseal(self, sealed: str) -> str: ...

    @abstractmethod
    def digest(self, code: str) -> str:
        """Keyed one-way digest used to store recovery codes."""
