"""Page-level checks between silver and the corpus: quarantine, hold or accept (ING-006, S3)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from app.domain.ingestion.documents import BlockKind, CanonicalDocument


class Verdict(StrEnum):
    ACCEPT = "accept"
    # Expected-empty pages (E12) are recorded, not treated as failures.
    EMPTY = "empty_after_clean"
    QUARANTINE = "quarantine"
    # A sharp shrink keeps the last-known-good until the new state proves stable.
    HOLD = "hold"


@dataclass(frozen=True)
class FamilyContract:
    """Markers every page of a family must have; a miss means the wiki layout changed."""

    requires_infobox: bool = False
    required_kinds: frozenset[BlockKind] = frozenset()


@dataclass(frozen=True)
class CheckPolicy:
    residue: re.Pattern[str]
    max_shrink: float = 0.4
    # Runs a shrunken page must stay unchanged before it replaces its last-known-good.
    hold_runs: int = 2
    # Conservation check, calibrated on Tier A: above both limits the cleaner lost real text.
    max_unexplained_ratio: float = 0.02
    min_unexplained_chars: int = 50


@dataclass(frozen=True)
class PageCheck:
    verdict: Verdict
    reasons: tuple[str, ...] = ()

    @property
    def usable(self) -> bool:
        return self.verdict in {Verdict.ACCEPT, Verdict.EMPTY}


def residue_hits(document: CanonicalDocument, residue: re.Pattern[str]) -> list[str]:
    return [match.group(0) for block in document.blocks for match in residue.finditer(block.text)]


def contract_violations(document: CanonicalDocument, contract: FamilyContract | None) -> list[str]:
    if contract is None:
        return []
    violations = []
    if contract.requires_infobox and not document.infoboxes:
        violations.append("missing_infobox")
    kinds = {block.kind for block in document.blocks}
    violations.extend(f"missing_{kind.value}" for kind in sorted(contract.required_kinds - kinds))
    return violations


def check_page(
    document: CanonicalDocument,
    *,
    policy: CheckPolicy,
    contract: FamilyContract | None,
    last_known_good: CanonicalDocument | None,
    unchanged_runs: int = 0,
) -> PageCheck:
    """`unchanged_runs` counts consecutive runs that produced this same silver output."""
    if hits := residue_hits(document, policy.residue):
        return PageCheck(Verdict.QUARANTINE, tuple(f"residue:{hit}" for hit in sorted(set(hits))))
    if _lost_text(document, policy):
        return PageCheck(Verdict.QUARANTINE, ("unexplained_text",))
    if not document.blocks:
        return _empty_or_hold(last_known_good, policy, unchanged_runs)
    if violations := contract_violations(document, contract):
        return PageCheck(Verdict.QUARANTINE, tuple(f"layout_changed:{v}" for v in violations))
    if _shrank(document, last_known_good, policy) and unchanged_runs < policy.hold_runs:
        return PageCheck(Verdict.HOLD, ("shrink",))
    return PageCheck(Verdict.ACCEPT)


def _lost_text(document: CanonicalDocument, policy: CheckPolicy) -> bool:
    lost = document.unexplained_chars
    limit = policy.max_unexplained_ratio * document.source_chars
    return lost >= policy.min_unexplained_chars and lost > limit


def _empty_or_hold(
    last_known_good: CanonicalDocument | None, policy: CheckPolicy, unchanged_runs: int
) -> PageCheck:
    had_text = last_known_good is not None and last_known_good.text_length > 0
    if had_text and unchanged_runs < policy.hold_runs:
        return PageCheck(Verdict.HOLD, ("emptied",))
    return PageCheck(Verdict.EMPTY)


def _shrank(
    document: CanonicalDocument, last_known_good: CanonicalDocument | None, policy: CheckPolicy
) -> bool:
    # Characters stand in for tokens: the ratio is what matters and needs no tokenizer here.
    if last_known_good is None or last_known_good.text_length == 0:
        return False
    return document.text_length < (1 - policy.max_shrink) * last_known_good.text_length
