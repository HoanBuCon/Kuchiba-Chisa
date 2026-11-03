"""Threads and turns of the v2 chat (CONV-001, MODE-006)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID


class ChatMode(StrEnum):
    ADVANCED = "advanced"
    AGENTIC = "agentic"


class DowngradeReason(StrEnum):
    NOT_ENTITLED = "not_entitled"


@dataclass(frozen=True)
class ModeDecision:
    requested: ChatMode
    effective: ChatMode
    downgrade_reason: DowngradeReason | None = None


@dataclass(frozen=True)
class Thread:
    id: UUID
    owner_principal: str
    channel: str
    mode: ChatMode
    title: str | None
    created_at: datetime
    archived_at: datetime | None = None


@dataclass(frozen=True)
class TurnRecord:
    """One exchange, with what it cost and the citations as they were (MODE-006, GRD-005)."""

    thread_id: UUID
    turn_id: UUID
    question: str
    answer: str
    mode_requested: ChatMode
    mode_effective: ChatMode
    lane: str
    status: str
    downgrade_reason: DowngradeReason | None = None
    llm_calls: int = 0
    citations: tuple[dict[str, Any], ...] = field(default=())
    degraded: tuple[str, ...] = ()


def resolve_mode(
    *,
    override: ChatMode | None,
    thread_mode: ChatMode | None,
    account_default: ChatMode | None,
    can_use_agentic: bool,
) -> ModeDecision:
    """Message, then thread, then account, then clamped by permission (MODE-002, MODE-007)."""
    requested = override or thread_mode or account_default or ChatMode.ADVANCED
    if requested is ChatMode.AGENTIC and not can_use_agentic:
        return ModeDecision(requested, ChatMode.ADVANCED, DowngradeReason.NOT_ENTITLED)
    return ModeDecision(requested, requested)
