"""
EmotionEngine — Domain Service
Applies rule-based delta updates to EmotionState after each conversation turn.

Design principles:
- Pure domain logic: no HTTP, no DB calls directly.
- Takes EmotionState ORM object + text signals, mutates and returns deltas.
- The caller (ChatEngine) is responsible for persisting the updated state.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.infrastructure.logging.logger import get_logger

if TYPE_CHECKING:
    from app.infrastructure.database.models.emotion_state import EmotionState

log = get_logger(__name__)

# Keyword Signals were removed in favor of LLM Classification

@dataclass
class EmotionDelta:
    """Records the changes applied this turn for observability."""
    joy: float = 0.0
    sadness: float = 0.0
    trust: float = 0.0
    irritation: float = 0.0
    attachment: float = 0.0


class EmotionEngine:
    """
    Stateless rule-based engine that computes emotion deltas from a
    user message and the Chisa reply, then applies them to EmotionState.

    Calling update() mutates the EmotionState object in-place.
    The caller must commit the session.
    """

    # ── DEHA Constants ──────────────────────────────────────────────
    BASELINES = {
        "joy": 0.10,
        "sadness": 0.00,
        "trust": 0.50,
        "irritation": 0.00,
        "attachment": 0.00
    }
    
    DECAY_RATES = {
        "joy": 0.10,
        "sadness": 0.15,
        "trust": 0.02,
        "irritation": 0.20,
        "attachment": 0.00
    }
    
    MAX_GAIN = {
        "joy": 0.15,
        "sadness": 0.20,
        "trust": 0.05,
        "irritation": 0.25,
        "attachment": 0.02
    }
    
    CAP = 1.0
    FLOOR = 0.0

    @staticmethod
    def _clamp(value: float) -> float:
        return max(EmotionEngine.FLOOR, min(EmotionEngine.CAP, value))

    def update(self, state: "EmotionState", is_positive: bool = False, is_negative: bool = False, is_rude: bool = False) -> EmotionDelta:
        """
        Apply emotion deltas based on flags provided by the LLM Sentiment Classifier.
        Returns an EmotionDelta summary for logging.
        """

        delta = EmotionDelta()

        # 1. Psychological Homeostasis (Natural Decay toward Baseline)
        delta.joy = -self.DECAY_RATES["joy"] * (state.joy - self.BASELINES["joy"])
        delta.sadness = -self.DECAY_RATES["sadness"] * (state.sadness - self.BASELINES["sadness"])
        delta.trust = -self.DECAY_RATES["trust"] * (state.trust - self.BASELINES["trust"])
        delta.irritation = -self.DECAY_RATES["irritation"] * (state.irritation - self.BASELINES["irritation"])
        
        # 2. Pre-calculate Psychological Multipliers (Trust & Attachment)
        # Low trust (<0.5) dampens Joy and amplifies Negativity
        # High trust (>0.5) amplifies Joy and dampens Negativity
        trust_factor = state.trust
        positivity_multiplier = 0.5 + trust_factor  # ranges 0.5x to 1.5x
        negativity_multiplier = 1.5 - trust_factor  # ranges 1.5x to 0.5x

        # 3. Stimulus Application (Weber-Fechner Law + Trust Modulation)
        if is_positive:
            # Joy gain is multiplied by trust
            joy_gain = self.MAX_GAIN["joy"] * (1.1 - state.joy) * positivity_multiplier
            delta.joy += joy_gain
            delta.sadness -= (joy_gain * 1.5)      # Suppresses sadness
            delta.irritation -= (joy_gain * 2.0)   # Heavily suppresses irritation
            
            # Trust is HARD to earn (diminishing very fast)
            delta.trust += (self.MAX_GAIN["trust"] * 0.5) * (1.0 - state.trust)
            
        if is_negative:
            # Sadness is amplified by low trust
            sad_gain = self.MAX_GAIN["sadness"] * (1.1 - state.sadness) * negativity_multiplier
            delta.sadness += sad_gain
            delta.joy -= (sad_gain * 1.5)          # Suppresses joy
            
            # Trust is EASY to lose
            delta.trust -= 0.15 * negativity_multiplier
            
        if is_rude:
            # Irritation/Anger is amplified by low trust
            irr_gain = self.MAX_GAIN["irritation"] * (1.1 - state.irritation) * negativity_multiplier
            delta.irritation += irr_gain
            delta.joy -= (irr_gain * 2.0)          # Heavily suppresses joy
            delta.sadness += 0.05
            
            # Trust is VERY EASY to lose when rude
            delta.trust -= 0.25
            
        # 4. Attachment progression (Asymmetrical progression)
        # Attachment only grows if trust is high without rudeness, and grows very slowly
        if state.trust > 0.6 and not is_rude and not is_negative:
            delta.attachment = (self.MAX_GAIN["attachment"] * 0.5) * (1.0 - state.attachment)
        elif is_rude or is_negative:
            # Attachment drops rapidly on abuse
            delta.attachment = -self.MAX_GAIN["attachment"] * 2.5 * negativity_multiplier

        # Apply Deltas
        state.joy = self._clamp(state.joy + delta.joy)
        state.sadness = self._clamp(state.sadness + delta.sadness)
        state.trust = self._clamp(state.trust + delta.trust)
        state.irritation = self._clamp(state.irritation + delta.irritation)
        state.attachment = self._clamp(state.attachment + delta.attachment)

        log.debug(
            "EmotionEngine update applied",
            joy=f"{state.joy:.3f}",
            sadness=f"{state.sadness:.3f}",
            trust=f"{state.trust:.3f}",
            irritation=f"{state.irritation:.3f}",
            attachment=f"{state.attachment:.3f}",
            signals={"pos": is_positive, "neg": is_negative, "rude": is_rude},
        )
        return delta
