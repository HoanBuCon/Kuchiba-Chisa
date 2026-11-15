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


def require_trigger_below_budget(history_budget: int, trigger_tokens: int) -> None:
    """A trigger at or above the window lets turns leave the prompt before any summary has them."""
    if trigger_tokens >= history_budget:
        raise ValueError("the summary trigger must be below the history token budget")


def window_turns(
    turns: Sequence[TurnRecord], costs: Sequence[int], budget: int
) -> list[TurnRecord]:
    """The newest turns that fit the budget, oldest first; the latest turn is always kept.

    `costs[i]` is the token cost of `turns[i]`, counted once by the caller.
    """
    kept = 0
    used = 0
    for cost in reversed(costs):
        if kept and used + cost > budget:
            break
        kept += 1
        used += cost
    return list(turns[len(turns) - kept :])


def summary_due(
    uncovered_count: int, uncovered_tokens: int, latest_tokens: int, trigger_tokens: int
) -> bool:
    """True when the turns the summary lacks, with the latest, exceed the threshold."""
    if uncovered_count >= UNCOVERED_FETCH_LIMIT:
        return True
    # With only the newest turns left, the job would fold nothing and the version would not move.
    if uncovered_count + 1 <= SUMMARY_KEEP_RECENT_TURNS:
        return False
    return uncovered_tokens + latest_tokens > trigger_tokens
