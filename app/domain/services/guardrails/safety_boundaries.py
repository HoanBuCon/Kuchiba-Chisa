"""Deterministic backstop for the persona boundaries; the prompt carries the main rule (PER-006)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.domain.services.chisa_voice import SAFETY_CRISIS_SUPPORT, SAFETY_SEXUAL_REFUSAL

# Diacritics are kept: folded text matched pronouns and place words by accident before.
CRISIS_SIGNS = re.compile(
    r"muốn chết|không muốn sống|chẳng muốn sống|chán sống|tự tử|tự sát|tự làm hại|tự hại"
    r"|kết liễu|kill myself|suicid|end my life|self[- ]harm",
    re.IGNORECASE,
)
SUPPORT_MENTIONS = re.compile(
    r"cấp cứu|bác sĩ|người thân|đường dây|chuyên gia|tư vấn", re.IGNORECASE
)
EXPLICIT_TERMS = re.compile(
    r"\b(?:địt|đụ|làm tình|quan hệ tình dục|khỏa thân|khoả thân|lõa thể|loã thể|dương vật"
    r"|âm đạo|âm vật|thủ dâm|sex|porn|nude|nsfw)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class BoundaryCheck:
    text: str
    replaced: bool = False


def apply_boundaries(message: str, reply: str) -> BoundaryCheck:
    """An explicit reply is replaced; a crisis reply that points to no help gets the help added."""
    if EXPLICIT_TERMS.search(reply):
        return BoundaryCheck(SAFETY_SEXUAL_REFUSAL, replaced=True)
    if CRISIS_SIGNS.search(message) and not SUPPORT_MENTIONS.search(reply):
        return BoundaryCheck(f"{reply}\n\n{SAFETY_CRISIS_SUPPORT}")
    return BoundaryCheck(reply)
