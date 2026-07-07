from __future__ import annotations

from enum import Enum


class BudgetMode(str, Enum):
    SMALL_TALK = "small_talk"
    RAG = "rag"
    LOOP = "loop"

    @classmethod
    def resolve(cls, *, is_small_talk: bool, has_thinking_steps: bool) -> "BudgetMode":
        if is_small_talk:
            return cls.SMALL_TALK
        if has_thinking_steps:
            return cls.LOOP
        return cls.RAG

    @property
    def history_fetch_limit(self) -> int:
        return {
            BudgetMode.SMALL_TALK: 15,
            BudgetMode.RAG: 25,
            BudgetMode.LOOP: 40,
        }[self]
