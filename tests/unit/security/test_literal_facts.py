"""Literal fact checks: names, numbers and negation across languages."""

import pytest

from app.domain.services.guardrails.literal_facts import (
    facts_match,
    introduces_new_facts,
    invents_names,
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


@pytest.mark.parametrize(
    "claim",
    [
        "Cô ấy đứng giữa không gian rộng.",
        "Khu vực nằm trong không khí lạnh.",
        "Cô ấy thuộc không quân Ashinohara.",
    ],
)
def test_khong_inside_a_compound_is_not_a_negation(claim) -> None:
    assert negation_agrees(claim, "She is in the open space of Ashinohara.")


def test_khong_as_a_negation_is_still_detected() -> None:
    assert not negation_agrees("Cô ấy không rời đi.", "She left.")


def test_negation_must_agree() -> None:
    assert negation_agrees("không có", "never had")
    assert not negation_agrees("có", "never had")


def test_an_invented_name_in_english_is_caught() -> None:
    assert invents_names("It causes Hack - Interfered.", "Tune Rupture and Tune Strain.")


def test_a_name_in_the_evidence_is_allowed() -> None:
    assert not invents_names("She studies at Startorch Academy.", "Startorch Academy is a school.")


def test_a_sentence_initial_capital_is_not_a_name() -> None:
    assert not invents_names("The school is old. Then it closed.", "a school closed")
