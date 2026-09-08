"""Typed contracts for atomic community shared-state mutations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CommunityTurn:
    event_id: str
    user_message: dict[str, Any]
    assistant_message: dict[str, Any]
    ambient_delta: dict[str, float]


@dataclass(frozen=True)
class CommunityMutationResult:
    applied: bool
    state_revision: int
    message_count: int


@dataclass(frozen=True)
class CommunityStateSnapshot:
    state_revision: int
    message_count: int
    messages: list[dict[str, Any]]
    topic_summary: str | None
    topic_summary_revision: int
