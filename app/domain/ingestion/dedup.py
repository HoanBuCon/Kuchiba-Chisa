"""Cross-page dedup by owning page (ING-011, E2): a repeated passage is kept once, on its owner."""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, TypeVar

from app.domain.ingestion.units import PROFILE, Unit

_FINGERPRINT_SPACE = re.compile(r"\s+")


class _Owned(Protocol):
    @property
    def family(self) -> str | None: ...

    @property
    def page_id(self) -> int: ...

    @property
    def text(self) -> str: ...


OwnedT = TypeVar("OwnedT", bound=_Owned)
SceneKey = tuple[int, str, int]


def fingerprint(text: str) -> str:
    """Case and spacing differences between pages do not make a passage new."""
    canonical = _FINGERPRINT_SPACE.sub(" ", text).strip().casefold()
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class OwnerPolicy:
    """Earlier families own shared text: specific pages beat aggregate ones (ING-011)."""

    family_priority: tuple[str, ...]
    # Short lines ("Hello.", "Yes.") repeat legitimately and only dedup as whole chunks.
    min_chars: int = 80

    def rank(self, item: _Owned) -> tuple[int, int]:
        family = item.family or ""
        priority = self.family_priority
        position = priority.index(family) if family in priority else len(priority)
        return position, item.page_id


@dataclass(frozen=True)
class DedupResult:
    units: tuple[Unit, ...]
    # Removed passage fingerprint -> owning page id, kept for `duplicate_of` references.
    duplicate_of: dict[str, int]


def _is_candidate(unit: Unit, policy: OwnerPolicy) -> bool:
    return unit.kind != PROFILE and not unit.is_turn and len(unit.text) >= policy.min_chars


def _scene_key(unit: Unit) -> SceneKey:
    return unit.page_id, unit.group, unit.scene


def deduplicate(units: Sequence[Unit], policy: OwnerPolicy) -> DedupResult:
    """Prose-like units dedup one by one; dialogue dedups whole scenes so no half scene survives."""
    owners: dict[str, Unit] = {}
    for unit in units:
        if _is_candidate(unit, policy):
            key = fingerprint(unit.text)
            if key not in owners or policy.rank(unit) < policy.rank(owners[key]):
                owners[key] = unit
    duplicated_scenes = _duplicated_scenes(units, policy)
    kept: list[Unit] = []
    duplicate_of: dict[str, int] = {}
    for unit in units:
        if unit.is_turn and _scene_key(unit) in duplicated_scenes:
            duplicate_of[fingerprint(unit.text)] = duplicated_scenes[_scene_key(unit)]
        elif _is_candidate(unit, policy) and owners[fingerprint(unit.text)] is not unit:
            duplicate_of[fingerprint(unit.text)] = owners[fingerprint(unit.text)].page_id
        else:
            kept.append(unit)
    return DedupResult(tuple(kept), duplicate_of)


def _duplicated_scenes(units: Sequence[Unit], policy: OwnerPolicy) -> dict[SceneKey, int]:
    """Map each non-owner copy of a scene to the page that owns the same scene text."""
    scenes: dict[SceneKey, list[Unit]] = defaultdict(list)
    for unit in units:
        if unit.is_turn:
            scenes[_scene_key(unit)].append(unit)
    by_text: dict[str, list[SceneKey]] = defaultdict(list)
    for key, turns in scenes.items():
        text = "\n".join(turn.text for turn in turns)
        if len(text) >= policy.min_chars:
            by_text[fingerprint(text)].append(key)
    duplicated: dict[SceneKey, int] = {}
    for keys in by_text.values():
        owner = min(keys, key=lambda key: policy.rank(scenes[key][0]))
        duplicated.update({key: owner[0] for key in keys if key != owner})
    return duplicated


def drop_duplicate_bodies(items: Sequence[OwnedT], policy: OwnerPolicy) -> list[OwnedT]:
    """Guarantee 0 exact duplicates per release (ING-011), whatever size the passage is."""
    owners: dict[str, OwnedT] = {}
    for item in items:
        key = fingerprint(item.text)
        if key not in owners or policy.rank(item) < policy.rank(owners[key]):
            owners[key] = item
    return [item for item in items if owners[fingerprint(item.text)] is item]
