"""Core memory: a small structured profile present in every Composer prompt (MEM-001)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

MAX_ITEMS = 12
MAX_ITEM_CHARS = 160
MAX_NAME_CHARS = 64


class CoreMemory(BaseModel):
    """The limits keep it near the 300-600 tokens MEM-001 allows, whoever writes it."""

    model_config = ConfigDict(extra="forbid")

    nickname: str | None = Field(default=None, max_length=MAX_NAME_CHARS)
    milestones: list[str] = Field(default_factory=list, max_length=MAX_ITEMS)
    preferences: list[str] = Field(default_factory=list, max_length=MAX_ITEMS)
    promises: list[str] = Field(default_factory=list, max_length=MAX_ITEMS)


def _lines(label: str, items: list[str]) -> list[str]:
    kept = [item[:MAX_ITEM_CHARS] for item in items if item.strip()]
    return [f"{label}: {'; '.join(kept)}"] if kept else []


def render_core_memory(content: Mapping[str, Any] | None) -> str | None:
    """One memory line for the prompt, or nothing when there is nothing to say."""
    if not content:
        return None
    memory = CoreMemory.model_validate(content)
    lines = [f"Nickname: {memory.nickname}"] if memory.nickname else []
    lines += _lines("Relationship milestones", memory.milestones)
    lines += _lines("Preferences", memory.preferences)
    lines += _lines("Promises still open", memory.promises)
    return "\n".join(lines) or None
