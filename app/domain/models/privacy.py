"""Privacy policy value objects used at application trust boundaries (SAFE-02)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


@dataclass(frozen=True)
class MemoryPrivacyPolicy:
    """A verified user's durable long-term-memory preference.

    Conversation persistence is deliberately not governed by this value object;
    it governs derived long-term text, image, and community memory only.
    """

    long_term_memory_enabled: bool = False
    retention_days: int | None = None
    consented_at: datetime | None = None

    @property
    def allows_long_term_memory(self) -> bool:
        return self.long_term_memory_enabled and self.retention_days is not None

    def retention_expiry_epoch(self, *, now: datetime | None = None) -> int | None:
        if not self.allows_long_term_memory or self.retention_days is None:
            return None
        current = now or datetime.now(UTC)
        return int((current + timedelta(days=self.retention_days)).timestamp())
