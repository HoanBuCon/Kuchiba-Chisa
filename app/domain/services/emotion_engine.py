"""
EmotionEngine — Domain Service
Applies rule-based delta updates to EmotionState after each conversation turn.

Design principles:
- Pure domain logic: no HTTP, no DB calls directly.
- Takes EmotionState ORM object + text signals, mutates and returns deltas.
- The caller (ChatEngine) is responsible for persisting the updated state.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.infrastructure.logging.logger import get_logger

if TYPE_CHECKING:
    from app.infrastructure.database.models.emotion_state import EmotionState

log = get_logger(__name__)

# ── Keyword Signals ──────────────────────────────────────────────────────────

_POSITIVE_PATTERNS = re.compile(
    r"\b(vui|hạnh phúc|tuyệt|cảm ơn|yêu|thích|good|great|happy|love|cảm ơn|tốt lắm|giỏi|dễ thương)\b",
    re.IGNORECASE,
)
_NEGATIVE_PATTERNS = re.compile(
    r"\b(tệ|chán|ghét|tức|bực|buồn|khó chịu|annoying|angry|sad|hate|terrible|fail|tôi không thích)\b",
    re.IGNORECASE,
)
_RUDE_PATTERNS = re.compile(
    r"\b(ngu|đần|xấu|trash|idiot|stupid|shut up|im lặng)\b",
    re.IGNORECASE,
)


@dataclass
class EmotionDelta:
    """Records the changes applied this turn for observability."""
    joy: float = 0.0
    sadness: float = 0.0
    trust: float = 0.0
    irritation: float = 0.0


class EmotionEngine:
    """
    Stateless rule-based engine that computes emotion deltas from a
    user message and the Chisa reply, then applies them to EmotionState.

    Calling update() mutates the EmotionState object in-place.
    The caller must commit the session.
    """

    # ── Delta constants ──────────────────────────────────────────────
    JOY_GAIN = 0.06
    JOY_DECAY = 0.02
    SADNESS_GAIN = 0.05
    SADNESS_DECAY = 0.03
    TRUST_GAIN = 0.03          # Grows every turn naturally
    IRRITATION_GAIN = 0.10
    IRRITATION_DECAY = 0.05
    CAP = 1.0
    FLOOR = 0.0

    @staticmethod
    def _clamp(value: float) -> float:
        return max(EmotionEngine.FLOOR, min(EmotionEngine.CAP, value))

    def update(self, state: "EmotionState", user_message: str) -> EmotionDelta:
        """
        Analyse the user message and apply emotion deltas.
        Returns an EmotionDelta summary for logging.
        """
        is_positive = bool(_POSITIVE_PATTERNS.search(user_message))
        is_negative = bool(_NEGATIVE_PATTERNS.search(user_message))
        is_rude = bool(_RUDE_PATTERNS.search(user_message))

        delta = EmotionDelta()

        # ── Joy ──────────────────────────────────────────────────────
        if is_positive:
            delta.joy = self.JOY_GAIN
        else:
            delta.joy = -self.JOY_DECAY
        state.joy = self._clamp(state.joy + delta.joy)

        # ── Sadness ──────────────────────────────────────────────────
        if is_negative and not is_positive:
            delta.sadness = self.SADNESS_GAIN
        else:
            delta.sadness = -self.SADNESS_DECAY
        state.sadness = self._clamp(state.sadness + delta.sadness)

        # ── Trust ────────────────────────────────────────────────────
        # Grows naturally each turn; decreases on rudeness
        if is_rude:
            delta.trust = -0.05
        else:
            delta.trust = self.TRUST_GAIN
        state.trust = self._clamp(state.trust + delta.trust)

        # ── Irritation ───────────────────────────────────────────────
        if is_rude or is_negative:
            delta.irritation = self.IRRITATION_GAIN
        else:
            delta.irritation = -self.IRRITATION_DECAY
        state.irritation = self._clamp(state.irritation + delta.irritation)

        log.debug(
            "EmotionEngine update applied",
            joy=f"{state.joy:.3f}",
            sadness=f"{state.sadness:.3f}",
            trust=f"{state.trust:.3f}",
            irritation=f"{state.irritation:.3f}",
            signals={"pos": is_positive, "neg": is_negative, "rude": is_rude},
        )
        return delta
