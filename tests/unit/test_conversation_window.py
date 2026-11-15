"""Token window and summary trigger of the v2 short-term context (CONV-002, CONV-003)."""

from uuid import uuid4

from app.domain.models.thread import ChatMode, TurnRecord
from app.domain.services.conversation_window import (
    MESSAGE_OVERHEAD_TOKENS,
    UNCOVERED_FETCH_LIMIT,
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


def test_window_keeps_the_newest_turns_that_fit_the_budget() -> None:
    turns = [_turn() for _ in range(5)]
    cost = turn_tokens(turns[0], COUNT)

    window = window_turns(turns, budget=cost * 2 + 1, count=COUNT)

    assert window == turns[-2:]


def test_window_keeps_the_latest_turn_even_when_it_alone_exceeds_the_budget() -> None:
    turns = [_turn(), _turn("q" * 500, "a" * 500)]

    assert window_turns(turns, budget=10, count=COUNT) == [turns[-1]]


def test_window_of_no_turns_is_empty() -> None:
    assert window_turns([], budget=100, count=COUNT) == []


def test_window_stops_at_the_first_turn_that_does_not_fit() -> None:
    small, big = _turn(), _turn("q" * 400, "a" * 400)
    turns = [small, big, small]

    window = window_turns(turns, budget=turn_tokens(small, COUNT) * 2, count=COUNT)

    assert window == [turns[-1]]


def test_turn_cost_counts_both_messages_and_their_overhead() -> None:
    assert turn_tokens(_turn("abc", "de"), COUNT) == 5 + TURN_OVERHEAD


def test_summary_is_due_only_above_the_threshold() -> None:
    latest = _turn()
    cost = turn_tokens(latest, COUNT)
    uncovered = [_turn(), _turn()]

    assert not summary_due(uncovered, latest, trigger_tokens=cost * 3, count=COUNT)
    assert summary_due(uncovered, latest, trigger_tokens=cost * 3 - 1, count=COUNT)


def test_summary_is_due_when_the_fetch_limit_hides_the_backlog() -> None:
    uncovered = [_turn("q", "a") for _ in range(UNCOVERED_FETCH_LIMIT)]

    assert summary_due(uncovered, _turn("q", "a"), trigger_tokens=10**9, count=COUNT)
