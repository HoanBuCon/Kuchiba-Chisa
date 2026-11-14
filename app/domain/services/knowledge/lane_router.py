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
# "tiếng Anh" is the English language, not the person speaking.
_ADDRESSING = re.compile(
    r"(?<!tiếng )(?<!tieng )"
    r"\b(anh|em|tôi|mình|tớ|senpai|bạn|mày|tao|cậu|chía|toi|minh|i|me|my|you)\b"
    r"(?!\s+(?:ấy|ay|ta|hùng|trai|gái|gai|ruột|ruot)\b)",
    re.IGNORECASE,
)
_GREETING = re.compile(
    r"^(chao|hello|hi|hey|cam on|thanks|thank you|tam biet|bye|ngu ngon|good night|good morning)\b"
)
# A question about Chisa herself goes to retrieval, though it says "em" or "you".
_ASKS_FACTS = re.compile(
    r"\b(he|attribute|vu khi|weapon|sinh ra|born|nhiem vu|quest|chapter|chuong|backstory"
    r"|resonator|wiki|lore|tieu su|hoc o|hoc vien|study|academy|tacet"
    r"|long tieng|voice|voices|voiced|dien vien)\b"
)
# Without a question mark, a question word or a request to tell, nothing is being asked.
_ASKS = re.compile(
    r"\?|\b(gi|j|ji|nao|ai|dau|sao|bao nhieu|may|the nao|what|who|whom|whose|where|when|which"
    r"|how|why|ke|liet ke|giai thich|tom tat|cho biet|list|tell|explain|describe|name)\b"
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
    # A remark such as praise or an insult would only get an abstention from retrieval.
    return Lane.ADVANCED if _ASKS.search(folded) else Lane.COMPANION
