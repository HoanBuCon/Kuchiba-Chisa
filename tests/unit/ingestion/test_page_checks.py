"""Page checks (ING-006): residue and layout quarantine, shrink hold, expected-empty pages."""

import re
from dataclasses import replace

from app.domain.ingestion.documents import Block, BlockKind, CanonicalDocument
from app.domain.ingestion.page_checks import CheckPolicy, FamilyContract, Verdict, check_page

POLICY = CheckPolicy(residue=re.compile(r"\{\{|https?://"))
QUEST = FamilyContract(requires_infobox=True, required_kinds=frozenset({BlockKind.DIALOGUE}))


def _doc(*texts: str, infobox: bool = True, kind: BlockKind = BlockKind.PROSE) -> CanonicalDocument:
    blocks = tuple(Block(kind, (), text) for text in texts)
    return CanonicalDocument(
        1, "P", 1, "lore", "v", blocks, infoboxes=({"a": "b"},) if infobox else ()
    )


def _check(doc, *, contract=None, lkg=None, unchanged=0):
    return check_page(
        doc, policy=POLICY, contract=contract, last_known_good=lkg, unchanged_runs=unchanged
    )


def test_clean_page_is_accepted() -> None:
    assert _check(_doc("Fine text.")).verdict is Verdict.ACCEPT


def test_residue_quarantines_with_the_offending_markup() -> None:
    result = _check(_doc("See https://x and {{tpl"))

    assert result.verdict is Verdict.QUARANTINE
    assert result.reasons == ("residue:https://", "residue:{{")
    assert not result.usable


def test_contract_violations_mean_the_layout_changed() -> None:
    result = _check(_doc("Prose only.", infobox=False), contract=QUEST)

    assert result.verdict is Verdict.QUARANTINE
    assert result.reasons == ("layout_changed:missing_infobox", "layout_changed:missing_dialogue")


def test_contract_is_satisfied_by_the_required_kinds() -> None:
    assert _check(_doc("A: hi", kind=BlockKind.DIALOGUE), contract=QUEST).verdict is Verdict.ACCEPT


def test_empty_page_without_history_is_expected_empty() -> None:
    result = _check(_doc())

    assert result.verdict is Verdict.EMPTY and result.usable


def test_page_emptied_after_having_text_is_held_until_stable() -> None:
    lkg = _doc("x" * 100)

    assert _check(_doc(), lkg=lkg).verdict is Verdict.HOLD
    assert _check(_doc(), lkg=lkg, unchanged=POLICY.hold_runs).verdict is Verdict.EMPTY


def test_shrink_over_forty_percent_is_held_then_accepted_when_stable() -> None:
    lkg = _doc("x" * 100)

    assert _check(_doc("x" * 59), lkg=lkg).verdict is Verdict.HOLD
    assert _check(_doc("x" * 59), lkg=lkg, unchanged=1).verdict is Verdict.HOLD
    assert _check(_doc("x" * 59), lkg=lkg, unchanged=2).verdict is Verdict.ACCEPT
    assert _check(_doc("x" * 60), lkg=lkg).verdict is Verdict.ACCEPT


def test_conservation_check_quarantines_only_above_both_limits() -> None:
    def lost(source: int, chars: int):
        return replace(_doc("Body."), source_chars=source, unexplained_text=("x" * chars,))

    assert _check(lost(1_000, 60)).reasons == ("unexplained_text",)
    assert _check(lost(1_000, 40)).verdict is Verdict.ACCEPT
    assert _check(lost(100_000, 60)).verdict is Verdict.ACCEPT


def test_page_emptied_by_a_cleaner_bug_is_not_mistaken_for_expected_empty() -> None:
    document = replace(_doc(), source_chars=500, unexplained_text=("x" * 500,))

    assert _check(document).verdict is Verdict.QUARANTINE
