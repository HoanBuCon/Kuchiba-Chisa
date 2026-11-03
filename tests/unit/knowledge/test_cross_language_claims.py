"""Cross-language claim check: literal names, numbers and negation, then similarity."""

import pytest

from app.domain.services.knowledge.cross_language_claims import (
    CrossLanguageClaimCheck,
    facts_match,
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


class Embedder:
    def __init__(self, vectors) -> None:
        self.vectors = vectors

    async def embed_batch(self, texts, prefix="query: "):
        assert prefix == "query: "
        return [self.vectors[text] for text in texts]


async def test_low_similarity_fails_even_when_the_facts_match() -> None:
    claim = "Chisa sinh ra ở Ashinohara."
    embedder = Embedder({claim: [1.0, 0.0], QUOTE: [0.0, 1.0]})

    check = await CrossLanguageClaimCheck.prepare(embedder, [(claim, QUOTE)])

    assert not check(claim, QUOTE, EVIDENCE)


async def test_high_similarity_with_matching_facts_passes() -> None:
    claim = "Chisa sinh ra ở Ashinohara."
    embedder = Embedder({claim: [1.0, 0.1], QUOTE: [1.0, 0.0]})

    check = await CrossLanguageClaimCheck.prepare(embedder, [(claim, QUOTE)])

    assert check(claim, QUOTE, EVIDENCE)


async def test_a_pair_never_prepared_does_not_pass() -> None:
    check = await CrossLanguageClaimCheck.prepare(Embedder({}), [])

    assert not check("Chisa sinh ra ở Ashinohara.", QUOTE, EVIDENCE)
