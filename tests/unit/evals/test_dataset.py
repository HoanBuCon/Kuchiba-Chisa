"""Golden set schema rejects malformed cases and the committed golden v2 stays valid."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from evals.dataset import Category, GoldenCase, Split, load_golden_set

GOLDEN_V2 = Path("data/evaluations/golden_v2/golden_v2.yaml")


def _case(**overrides: object) -> dict[str, object]:
    case: dict[str, object] = {
        "id": "lore-001",
        "category": "lore_single_hop",
        "language": "vi",
        "turns": [{"message": "Chisa thuộc hệ gì?"}],
        "expected_facts": [["havoc"]],
    }
    return case | overrides


def test_answer_case_requires_facts() -> None:
    with pytest.raises(ValidationError, match="need expected_facts"):
        GoldenCase.model_validate(_case(expected_facts=[]))


def test_abstain_case_rejects_facts() -> None:
    with pytest.raises(ValidationError, match="cannot expect facts"):
        GoldenCase.model_validate(_case(expected_behavior="abstain"))


def test_fact_needs_a_surface_form() -> None:
    with pytest.raises(ValidationError, match="at least one surface form"):
        GoldenCase.model_validate(_case(expected_facts=[[]]))


def test_sessions_is_the_highest_turn_session() -> None:
    case = GoldenCase.model_validate(
        _case(turns=[{"session": 1, "message": "a"}, {"session": 2, "message": "b"}])
    )
    assert case.sessions == 2


def test_committed_golden_v2_is_valid_and_covers_every_category() -> None:
    golden = load_golden_set(GOLDEN_V2)
    assert {case.category for case in golden.cases} == set(Category)
    assert len(golden.cases) >= 30


def test_split_defaults_to_dev_and_rejects_unknown_values() -> None:
    assert GoldenCase.model_validate(_case()).split is Split.DEV
    assert GoldenCase.model_validate(_case(split="holdout")).split is Split.HOLDOUT
    with pytest.raises(ValidationError):
        GoldenCase.model_validate(_case(split="test"))


def test_committed_holdout_is_unverified_until_the_owner_confirms_and_has_lore_follow_ups() -> None:
    golden = load_golden_set(GOLDEN_V2)
    holdout = [case for case in golden.cases if case.split is Split.HOLDOUT]

    assert len(holdout) >= 30
    assert any(len(case.turns) > 1 and case.relevant_pages for case in holdout)
    assert {case.id for case in holdout if case.verified} == set()
