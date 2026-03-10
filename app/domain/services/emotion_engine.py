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

    # ── Intensity Damping Constants ────────────────────────────────
    # When is_neutral=True, emotion gains are multiplied by these factors.
    # This prevents casual/mild messages from spiking emotions as strongly
    # as clearly heartfelt or intensely emotional messages.
    NEUTRAL_DAMPER = {
        "joy": 0.30,         # Casual warmth → only 30% of full joy gain
        "sadness": 0.35,     # Mild complaint → 35% of sadness gain
        "irritation": 0.55,  # Rude+neutral is contradictory; less dampening
    }

    def update(self, state: "EmotionState", is_positive: bool = False, is_negative: bool = False, is_rude: bool = False, is_neutral: bool = False) -> EmotionDelta:
        """
        Apply emotion deltas based on flags provided by the LLM Sentiment Classifier.

        is_neutral acts as an emotional intensity gate:
          - is_neutral=True  → emotion is mild/casual  → gains are dampened
          - is_neutral=False → emotion is intense/clear → full gains applied

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
            # Intensity gate: casual warmth gets a fraction of the full joy gain
            joy_intensity = self.NEUTRAL_DAMPER["joy"] if is_neutral else 1.0
            joy_gain = self.MAX_GAIN["joy"] * (1.1 - state.joy) * positivity_multiplier * joy_intensity
            delta.joy += joy_gain
            delta.sadness -= (joy_gain * 1.5)      # Suppresses sadness
            delta.irritation -= (joy_gain * 2.0)   # Heavily suppresses irritation
            
            # Trust is HARD to earn; casual positives earn even less
            trust_intensity = 0.25 if is_neutral else 0.5
            delta.trust += (self.MAX_GAIN["trust"] * trust_intensity) * (1.0 - state.trust)
            
        if is_negative:
            # Intensity gate: mild complaints cause less sadness than genuine distress
            sad_intensity = self.NEUTRAL_DAMPER["sadness"] if is_neutral else 1.0
            sad_gain = self.MAX_GAIN["sadness"] * (1.1 - state.sadness) * negativity_multiplier * sad_intensity
            delta.sadness += sad_gain
            delta.joy -= (sad_gain * 1.5)          # Suppresses joy
            
            # Trust loss is also dampened for mild negatives
            trust_loss_intensity = 0.4 if is_neutral else 1.0
            delta.trust -= 0.15 * negativity_multiplier * trust_loss_intensity
            
        if is_rude:
            # Rudeness is inherently intense; is_neutral has partial effect
            irr_intensity = self.NEUTRAL_DAMPER["irritation"] if is_neutral else 1.0
            irr_gain = self.MAX_GAIN["irritation"] * (1.1 - state.irritation) * negativity_multiplier * irr_intensity
            delta.irritation += irr_gain
            delta.joy -= (irr_gain * 2.0)          # Heavily suppresses joy
            delta.sadness += 0.05 * irr_intensity
            
            # Trust loss from rudeness is also partially dampened if mild
            delta.trust -= 0.25 * (0.7 if is_neutral else 1.0)
            
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
            signals={"pos": is_positive, "neg": is_negative, "rude": is_rude, "neutral": is_neutral},
        )
        return delta
