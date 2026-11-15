"""Short-term context cut by tokens, and when a rolling summary is due (CONV-002, CONV-003)."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from app.domain.models.thread import TurnRecord

TokenCounter = Callable[[str], int]
# Chat formats add role markers around each message, so a turn costs more than its text.
MESSAGE_OVERHEAD_TOKENS = 4
MESSAGES_PER_TURN = 2
# Fetching stops here; reaching it means the summary is far behind, so one is due regardless.
UNCOVERED_FETCH_LIMIT = 40
# The newest turns stay verbatim after a summary, so "what did I just say" is answered exactly.
SUMMARY_KEEP_RECENT_TURNS = 2


def turn_tokens(turn: TurnRecord, count: TokenCounter) -> int:
    overhead = MESSAGE_OVERHEAD_TOKENS * MESSAGES_PER_TURN
    return count(turn.question) + count(turn.answer) + overhead


def window_turns(turns: Sequence[TurnRecord], budget: int, count: TokenCounter) -> list[TurnRecord]:
    """The newest turns that fit the budget, oldest first; the latest turn is always kept."""
    kept: list[TurnRecord] = []
    used = 0
    for turn in reversed(turns):
        cost = turn_tokens(turn, count)
        if kept and used + cost > budget:
            break
        kept.append(turn)
        used += cost
    kept.reverse()
    return kept


def summary_due(
    uncovered: Sequence[TurnRecord], latest: TurnRecord, trigger_tokens: int, count: TokenCounter
) -> bool:
    """True when the turns the summary does not cover yet, with `latest`, exceed the threshold."""
    if len(uncovered) >= UNCOVERED_FETCH_LIMIT:
        return True
    pending = sum(turn_tokens(turn, count) for turn in (*uncovered, latest))
    return pending > trigger_tokens
