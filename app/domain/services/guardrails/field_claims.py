"""Check an English claim against one infobox field line, e.g. "next: Grand Warstorm" (GRD-001)."""

from __future__ import annotations

import re

_FIELD = re.compile(r"^\s*([A-Za-z][A-Za-z ]{0,40}):\s*(\S.*?)\s*$")
# Field keys whose meaning a claim states in other words; any other key must appear as written.
_KEY_WORDS = {
    "next": ("next", "following", "after", "followed"),
    "prev": ("previous", "preceding", "before", "precedes"),
    "previous": ("previous", "preceding", "before", "precedes"),
}


def states_field(claim: str, quote: str) -> bool:
    """A field line has too few words for term overlap, so the claim must name its key and value."""
    match = _FIELD.match(quote)
    if match is None or ":" in match.group(2):
        return False
    key, value = match.group(1).strip().casefold(), match.group(2).casefold()
    text = claim.casefold()
    words = _KEY_WORDS.get(key, (key,))
    return value in text and any(re.search(rf"\b{re.escape(word)}\b", text) for word in words)
