"""Port for the external, atomic corpus-alias operation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.domain.models.corpus_release import CorpusRelease


@dataclass(frozen=True)
class CorpusPublication:
    """Verified result of a completed alias swap, not a planned change."""

    previous_active_collection: str | None
    active_collection: str


class ICorpusPublisher(Protocol):
    """Publish or rollback only a receipt whose manifests were already verified."""

    async def promote(self, release: CorpusRelease) -> CorpusPublication:
        ...

    async def active_target(self, logical_collection: str) -> str | None:
        """Read the current alias target for a deterministic reconciliation decision."""
        ...
