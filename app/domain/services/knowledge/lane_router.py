"""Deterministic triage inside the mode ceiling: companion or Advanced (MODE-008, QUAL-006).

Companion has no grounding, so a lore question sent there could be answered from nothing. It is
chosen only on a clear sign the person is talking with Chisa; anything unclear stays grounded.
"""

from __future__ import annotations

import re
from enum import StrEnum

from app.domain.ingestion.entity_linking import fold_for_matching

CHISA = "Chisa"
# Matched with diacritics kept: folded, "mẹ" reads as "me", "tổ" as "to" and "bàn" as "ban".
_ADDRESSING = re.compile(
    r"\b(anh|em|tôi|mình|tớ|senpai|bạn|toi|minh|i|me|my|you)\b"
    r"(?!\s+(?:ấy|ay|ta|hùng|trai|gái|gai|ruột|ruot)\b)",
    re.IGNORECASE,
)
_GREETING = re.compile(
    r"^(chao|hello|hi|hey|cam on|thanks|thank you|tam biet|bye|ngu ngon|good night|good morning)\b"
)
# A question about Chisa herself goes to retrieval, though it says "em" or "you".
_ASKS_FACTS = re.compile(
    r"\b(he|attribute|vu khi|weapon|sinh ra|born|nhiem vu|quest|chapter|chuong|backstory"
    r"|resonator|wiki|lore|tieu su|hoc o|hoc vien|study|academy|tacet)\b"
)


class Lane(StrEnum):
    COMPANION = "companion"
    ADVANCED = "advanced"


def choose_lane(question: str, entities: tuple[str, ...]) -> Lane:
    """An entity other than Chisa means the game world, whatever the wording."""
    if any(entity != CHISA for entity in entities):
        return Lane.ADVANCED
    folded = fold_for_matching(question)
    if _ASKS_FACTS.search(folded):
        return Lane.ADVANCED
    if _GREETING.search(folded) or _ADDRESSING.search(question):
        return Lane.COMPANION
    return Lane.ADVANCED
