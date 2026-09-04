"""Stable lore collection routing vocabulary shared by ingestion and retrieval."""

from __future__ import annotations

import re
from enum import StrEnum


class LoreCollection(StrEnum):
    """The three logical lore indexes defined by the SRS."""

    CHARACTER = "character_lore"
    WORLD = "world_lore"
    STORY = "story_lore"


_CORPUS_VERSION_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def validate_lore_staging_collection(value: str) -> str:
    """Accept only a physical version of one declared lore collection.

    Runtime readers use aliases; ingestion may write only to a non-active,
    versioned physical collection.  This pure domain policy deliberately has no
    dependency on Qdrant or an adapter-specific collection implementation.
    """
    target = value.strip()
    logical_collection, separator, corpus_version = target.partition("__")
    if not separator:
        raise ValueError("ingestion requires a physical versioned staging collection")
    try:
        LoreCollection(logical_collection)
    except ValueError as exc:
        raise ValueError("ingestion target is not a configured lore collection") from exc
    if corpus_version == "active" or not _CORPUS_VERSION_PATTERN.fullmatch(corpus_version):
        raise ValueError("ingestion requires a non-active valid corpus version")
    return target


def corpus_version_from_staging_collection(value: str) -> str:
    """Return the validated corpus version encoded in a physical lore target."""
    validated = validate_lore_staging_collection(value)
    return validated.partition("__")[2]


def logical_collection_from_staging_collection(value: str) -> LoreCollection:
    """Return the declared logical lore route encoded in a physical target."""
    validated = validate_lore_staging_collection(value)
    logical_collection, _, _ = validated.partition("__")
    return LoreCollection(logical_collection)
