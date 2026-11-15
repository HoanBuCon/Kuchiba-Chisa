"""One call that picks the lane and writes a standalone English question (ADV-003, ADV-010)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from app.domain.interfaces.llm_provider import LLMCallBudget
from app.domain.services.knowledge.lane_router import Lane


class UnderstandingError(RuntimeError):
    """The understander could not answer; the turn falls back to the deterministic lane."""


@dataclass(frozen=True)
class PriorTurn:
    question: str
    answer: str


@dataclass(frozen=True)
class Understanding:
    lane: Lane
    # Standalone English question; empty for the companion lane.
    query: str


class IQuestionUnderstander(Protocol):
    async def understand(
        self,
        message: str,
        previous: Sequence[PriorTurn],
        budget: LLMCallBudget | None = None,
    ) -> Understanding: ...
