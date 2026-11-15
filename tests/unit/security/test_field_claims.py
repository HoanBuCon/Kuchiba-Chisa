import pytest

from app.domain.services.guardrails.field_claims import states_field
from app.domain.services.guardrails.literal_facts import negation_agrees


@pytest.mark.parametrize(
    ("claim", "quote"),
    [
        ("The quest following Rewinding Raindrops is Grand Warstorm.", "next: Grand Warstorm"),
        ("The quest before Rewinding Raindrops is Clashing Blades.", "prev: Clashing Blades"),
        ("Jingran's weapon is Broadblade.", "weapon: Broadblade"),
    ],
)
def test_a_claim_naming_the_field_and_its_value_is_supported(claim, quote) -> None:
    assert states_field(claim, quote)


@pytest.mark.parametrize(
    ("claim", "quote"),
    [
        # The relation is flipped: "next" stated as the quest before.
        ("The quest before Rewinding Raindrops is Grand Warstorm.", "next: Grand Warstorm"),
        ("Jingran's weapon is Sword.", "weapon: Broadblade"),
        # Two fields on one line are left to the term-overlap guard.
        ("Jingran's weapon is Broadblade.", "attribute: Fusion weapon: Broadblade"),
        ("Jingran is strong.", "Jingran is a playable Fusion Natural Resonator."),
    ],
)
def test_a_claim_missing_the_key_or_value_is_not_supported(claim, quote) -> None:
    assert not states_field(claim, quote)


def test_a_taboo_is_not_a_negation() -> None:
    assert negation_agrees("ghi các nguyên tắc và điều cấm", "details the principles and taboos")
