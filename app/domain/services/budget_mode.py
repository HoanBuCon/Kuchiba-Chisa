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
