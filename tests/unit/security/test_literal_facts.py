"""Literal fact checks: names, numbers and negation across languages."""

import pytest

from app.domain.services.guardrails.literal_facts import (
    facts_match,
    introduces_new_facts,
    negation_agrees,
)

QUOTE = "Chisa was born in Ashinohara and joined in 2021."
EVIDENCE = f"Kuchiba Chisa. {QUOTE} She never left Startorch."


@pytest.mark.parametrize(
    "claim",
    [
        "Chisa sinh ra ở Ashinohara và gia nhập năm 2021.",
        "Cô ấy sinh ra ở Ashinohara.",
        "Kuchiba Chisa gia nhập năm 2021.",
    ],
)
def test_faithful_claims_pass(claim) -> None:
    assert facts_match(claim, QUOTE, EVIDENCE)


@pytest.mark.parametrize(
    "claim",
    [
        "Chisa sinh ra ở Ragunna.",
        "Chisa gia nhập năm 2024.",
        "Chisa không sinh ra ở Ashinohara.",
    ],
)
def test_changed_facts_fail(claim) -> None:
    assert not facts_match(claim, QUOTE, EVIDENCE)


def test_a_negative_quote_needs_a_negative_claim() -> None:
    quote = "She never left Startorch."

    assert facts_match("Cô ấy chưa từng rời Startorch.", quote, EVIDENCE)
    assert not facts_match("Cô ấy đã rời Startorch.", quote, EVIDENCE)


def test_addressing_words_are_not_treated_as_names() -> None:
    assert facts_match("Em thấy Chisa sinh ra ở Ashinohara nha Senpai.", QUOTE, EVIDENCE)


def test_a_new_name_or_number_is_detected_against_a_source() -> None:
    source = "Chisa học ở Startorch năm 2021"

    assert not introduces_new_facts("Em nhớ Chisa nha Senpai, năm 2021.", source)
    assert introduces_new_facts("Em nhớ Ragunna nha.", source)
    assert introduces_new_facts("Em nhớ năm 2024.", source)


def test_negation_must_agree() -> None:
    assert negation_agrees("không có", "never had")
    assert not negation_agrees("có", "never had")
