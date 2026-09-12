"""Read-only port for the authoritative active lore corpus identity."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class LoreCorpusIdentity:
    """Immutable snapshot of logical lore aliases and their physical targets."""

    alias_targets: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        canonical = tuple(sorted(self.alias_targets))
        if not canonical or any(not logical or not target for logical, target in canonical):
            raise ValueError("lore corpus identity requires non-empty alias targets")
        if len({logical for logical, _ in canonical}) != len(canonical):
            raise ValueError("lore corpus identity contains duplicate logical aliases")
        object.__setattr__(self, "alias_targets", canonical)


class ILoreCorpusIdentityProvider(Protocol):
    async def active_lore_corpus_identity(self) -> LoreCorpusIdentity | None:
        """Return one authoritative alias snapshot, or ``None`` when incomplete."""
        ...
