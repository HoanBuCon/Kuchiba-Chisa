"""Token window and summary trigger of the v2 short-term context (CONV-002, CONV-003)."""

from uuid import uuid4

import pytest

from app.domain.models.thread import ChatMode, TurnRecord
from app.domain.services.conversation_window import (
    MESSAGE_OVERHEAD_TOKENS,
    SUMMARY_KEEP_RECENT_TURNS,
    UNCOVERED_FETCH_LIMIT,
    require_trigger_below_budget,
    summary_due,
    turn_tokens,
    window_turns,
)

# One character is one token, so budgets in the tests read as plain numbers.
COUNT = len
TURN_OVERHEAD = 2 * MESSAGE_OVERHEAD_TOKENS


def _turn(question: str = "q" * 10, answer: str = "a" * 10) -> TurnRecord:
    return TurnRecord(
        thread_id=uuid4(),
        turn_id=uuid4(),
        question=question,
        answer=answer,
        mode_requested=ChatMode.ADVANCED,
        mode_effective=ChatMode.ADVANCED,
        lane="advanced",
        status="grounded",
    )


def _window(turns: list[TurnRecord], budget: int) -> list[TurnRecord]:
    return window_turns(turns, [turn_tokens(turn, COUNT) for turn in turns], budget)


def test_window_keeps_the_newest_turns_that_fit_the_budget() -> None:
    turns = [_turn() for _ in range(5)]
    cost = turn_tokens(turns[0], COUNT)

    assert _window(turns, cost * 2 + 1) == turns[-2:]


def test_window_keeps_the_latest_turn_even_when_it_alone_exceeds_the_budget() -> None:
    turns = [_turn(), _turn("q" * 500, "a" * 500)]

    assert _window(turns, 10) == [turns[-1]]


def test_window_of_no_turns_is_empty() -> None:
    assert _window([], 100) == []


def test_window_stops_at_the_first_turn_that_does_not_fit() -> None:
    small, big = _turn(), _turn("q" * 400, "a" * 400)
    turns = [small, big, small]

    assert _window(turns, turn_tokens(small, COUNT) * 2) == [turns[-1]]


def test_turn_cost_counts_both_messages_and_their_overhead() -> None:
    assert turn_tokens(_turn("abc", "de"), COUNT) == 5 + TURN_OVERHEAD


def test_summary_is_due_only_above_the_threshold() -> None:
    assert not summary_due(3, 300, 100, trigger_tokens=400)
    assert summary_due(3, 300, 100, trigger_tokens=399)


def test_summary_is_due_when_the_fetch_limit_hides_the_backlog() -> None:
    assert summary_due(UNCOVERED_FETCH_LIMIT, 10, 10, trigger_tokens=10**9)


def test_no_summary_is_due_when_the_job_would_fold_nothing() -> None:
    few = SUMMARY_KEEP_RECENT_TURNS - 1

    assert not summary_due(few, 10**6, 10**6, trigger_tokens=1)
    assert summary_due(few + 1, 10**6, 10**6, trigger_tokens=1)


def test_a_trigger_at_or_above_the_window_is_refused() -> None:
    require_trigger_below_budget(1500, 1499)
    with pytest.raises(ValueError):
        require_trigger_below_budget(1500, 1500)


def test_a_growing_thread_never_has_a_turn_outside_both_window_and_summary() -> None:
    """Replays the service and the job in step; the job keeps the newest turns uncovered."""
    budget, trigger = 1500, 1200
    turns: list[TurnRecord] = []
    covered = 0
    for _ in range(200):
        uncovered = turns[covered:]
        costs = [turn_tokens(turn, COUNT) for turn in uncovered]
        windowed = window_turns(uncovered, costs, budget)
        assert len(windowed) == len(uncovered)
        latest = _turn("q" * 150, "a" * 150)
        due = summary_due(len(uncovered), sum(costs), turn_tokens(latest, COUNT), trigger)
        turns.append(latest)
        if due:
            covered = max(covered, len(turns) - SUMMARY_KEEP_RECENT_TURNS)
