"""Literal fact checks across languages: names, numbers and negation (GRD-001, GRD-003).

Embeddings cannot tell a true paraphrase from one with a swapped name or a flipped negation, so
these facts are compared as text instead, and no model call is needed.
"""

from __future__ import annotations

import re
import unicodedata

# Plain ASCII capitalised words: Vietnamese sentence openers almost always carry diacritics.
_NAME = re.compile(r"\b[A-Z][A-Za-z'’-]{2,}\b")
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
# Addressing words and common capitalised Vietnamese words without diacritics are not names.
_NOT_NAMES = frozenset(
    {"Anh", "Ban", "Cha", "Chapter", "Con", "Em", "Hoa", "Khi", "Nhan", "Sau", "Senpai", "Ten"}
    | {"Theo", "Tin", "Trong", "Tuy"}
)
_NEGATION = re.compile(
    r"\b(không|chưa|chẳng|chả|đừng|cấm|not|no|never|cannot|without|none|nothing|neither|nor"
    r"|unable|lack|lacks|unknown)\b|n't\b",
    re.IGNORECASE,
)


def _fold(text: str) -> str:
    return unicodedata.normalize("NFKC", text).casefold()


def negation_agrees(left: str, right: str) -> bool:
    """Both texts negate, or neither does."""
    return bool(_NEGATION.search(left)) == bool(_NEGATION.search(right))


def introduces_new_facts(text: str, source: str) -> bool:
    """True when ``text`` holds a number or proper name that ``source`` does not."""
    folded = _fold(source)
    if any(number not in folded for number in _NUMBER.findall(text)):
        return True
    names = (match for match in _NAME.findall(text) if match not in _NOT_NAMES)
    return any(_fold(name) not in folded for name in names)


def facts_match(claim: str, quote: str, evidence: str) -> bool:
    """Every number and name must be in the evidence, and both sides must agree on negation."""
    return not introduces_new_facts(claim, f"{evidence} {quote}") and negation_agrees(claim, quote)
