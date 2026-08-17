"""
EmotionEngine — Domain Service
Applies rule-based delta updates to EmotionState after each conversation turn.

Design principles:
- Pure domain logic: no HTTP, no DB calls directly.
- Takes EmotionState ORM object + text signals, mutates and returns deltas.
- The caller (ChatEngine) is responsible for persisting the updated state.
"""

from __future__ import annotations
import math
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING
from app.shared.utils.logger import get_logger

if TYPE_CHECKING:
    from app.domain.entities.emotion import EmotionState

log = get_logger(__name__)


VALID_ARCHETYPES = {
    "calm_warmth",
    "flustered_affection",
    "playful_pout",
    "melancholic_care",
    "cheerful_joy",
    "guarded_cold",
    "neutral"
}


@dataclass
class EmotionDelta:
    """Records the changes applied this turn for observability."""
    joy: float = 0.0
    sadness: float = 0.0
    trust: float = 0.0
    irritation: float = 0.0
    attachment: float = 0.0
    shyness: float = 0.0
    curiosity: float = 0.0
    comfort: float = 0.0
    primary_emotion: str = "calm_warmth"
    intensity: float = 0.5
    valence: float = 0.0


class EmotionEngine:
    """
    Continuous rule-based & cognitive-affective engine that computes emotion deltas
    from Continuous Valence, Intensity, and 8 Emotional & Relational Channels.

    Calling update() mutates the EmotionState object in-place.
    The caller must commit the session.
    """

    # ── DEHA Baselines ──────────────────────────────────────────────
    BASELINES = {
        "joy": 0.10,
        "sadness": 0.00,
        "trust": 0.50,
        "irritation": 0.00,
        "attachment": 0.00,
        "shyness": 0.00,
        "curiosity": 0.20,
        "comfort": 0.50,
    }
    
    MAX_GAIN = {
        "joy": 0.15,
        "sadness": 0.20,
        "trust": 0.05,
        "irritation": 0.25,
        "attachment": 0.025,
        "shyness": 0.35,
        "curiosity": 0.30,
        "comfort": 0.25,
    }
    
    CAP = 1.0
    FLOOR = 0.0

    @staticmethod
    def _clamp(value: float, min_val: float = 0.0, max_val: float = 1.0) -> float:
        return max(min_val, min(max_val, value))

    def update(
        self,
        state: "EmotionState",
        sentiment_analysis: dict = None,
        intensity: float = None,
        valence: float = None,
        primary_emotion: str = None,
        is_positive: bool = False,
        is_negative: bool = False,
        is_rude: bool = False,
        is_neutral: bool = False,
        chisa_sad: bool = False,
        chisa_happy: bool = False,
        chisa_annoyed: bool = False,
        chisa_flustered: bool = False,
    ) -> EmotionDelta:
        """
        Apply emotion deltas based on Continuous Emotion Vector (intensity, valence, primary_emotion)
        or fallback to legacy boolean flags across all 8 emotional dimensions.
        """
        # Ensure state has all 8 fields with safe baselines
        for key, val in self.BASELINES.items():
            if not hasattr(state, key) or getattr(state, key) is None:
                setattr(state, key, val)

        # 1. Resolve and Clamp Continuous Inputs
        if sentiment_analysis and isinstance(sentiment_analysis, dict):
            raw_intensity = sentiment_analysis.get("intensity", 0.5)
            raw_valence = sentiment_analysis.get("valence", 0.0)
            raw_emotion = sentiment_analysis.get("primary_emotion", "calm_warmth")
        elif intensity is not None or valence is not None or primary_emotion is not None:
            raw_intensity = intensity if intensity is not None else 0.5
            raw_valence = valence if valence is not None else 0.0
            raw_emotion = primary_emotion or "calm_warmth"
        else:
            # Map legacy boolean flags into Continuous Vector for full backward compatibility
            if is_rude:
                raw_intensity = 0.9 if not is_neutral else 0.6
                raw_valence = -0.9
                raw_emotion = "guarded_cold"
            elif is_negative:
                raw_intensity = 0.8 if not is_neutral else 0.4
                raw_valence = -0.7
                raw_emotion = "melancholic_care" if chisa_sad else ("playful_pout" if chisa_annoyed else "calm_warmth")
            elif is_positive:
                raw_intensity = 0.85 if not is_neutral else 0.35
                raw_valence = 0.8
                raw_emotion = "flustered_affection" if chisa_flustered else ("cheerful_joy" if chisa_happy else "calm_warmth")
            else:
                raw_intensity = 0.2
                raw_valence = 0.0
                raw_emotion = "neutral" if is_neutral else "calm_warmth"

        try:
            eff_intensity = self._clamp(float(raw_intensity), 0.0, 1.0)
        except (ValueError, TypeError):
            eff_intensity = 0.5

        try:
            eff_valence = self._clamp(float(raw_valence), -1.0, 1.0)
        except (ValueError, TypeError):
            eff_valence = 0.0

        eff_emotion = str(raw_emotion).lower().strip()
        if eff_emotion not in VALID_ARCHETYPES:
            eff_emotion = "calm_warmth"

        delta = EmotionDelta(
            primary_emotion=eff_emotion,
            intensity=eff_intensity,
            valence=eff_valence
        )

        # 2. Time-Aware Psychological Homeostasis (Exponential Decay toward Baseline)
        current_time_ms = int(time.time() * 1000)
        elapsed_sec = 0.0
        if state.updated_at and state.updated_at > 0:
            elapsed_sec = max(0.0, (current_time_ms - state.updated_at) / 1000.0)
        state.updated_at = current_time_ms

        HALF_LIVES = {
            "joy": 2700.0,          # 45 minutes
            "sadness": 10800.0,      # 3 hours
            "trust": 604800.0,       # 7 days
            "irritation": 900.0,     # 15 minutes
            "attachment": 1209600.0, # 14 days
            "shyness": 900.0,        # 15 minutes (cools down rapidly)
            "curiosity": 1800.0,     # 30 minutes
            "comfort": 7200.0,       # 2 hours
        }

        decay_factor = {}
        for emotion, half_life in HALF_LIVES.items():
            decay_constant = 0.69314718056 / half_life
            decay_factor[emotion] = math.exp(-decay_constant * elapsed_sec)

        delta.joy = (self.BASELINES["joy"] + (state.joy - self.BASELINES["joy"]) * decay_factor["joy"]) - state.joy
        delta.sadness = (self.BASELINES["sadness"] + (state.sadness - self.BASELINES["sadness"]) * decay_factor["sadness"]) - state.sadness
        delta.trust = (self.BASELINES["trust"] + (state.trust - self.BASELINES["trust"]) * decay_factor["trust"]) - state.trust
        delta.irritation = (self.BASELINES["irritation"] + (state.irritation - self.BASELINES["irritation"]) * decay_factor["irritation"]) - state.irritation
        delta.attachment = (self.BASELINES["attachment"] + (state.attachment - self.BASELINES["attachment"]) * decay_factor["attachment"]) - state.attachment
        delta.shyness = (self.BASELINES["shyness"] + (state.shyness - self.BASELINES["shyness"]) * decay_factor["shyness"]) - state.shyness
        delta.curiosity = (self.BASELINES["curiosity"] + (state.curiosity - self.BASELINES["curiosity"]) * decay_factor["curiosity"]) - state.curiosity
        delta.comfort = (self.BASELINES["comfort"] + (state.comfort - self.BASELINES["comfort"]) * decay_factor["comfort"]) - state.comfort

        # 3. Pre-calculate Psychological Multipliers (Trust Modulation)
        trust_factor = state.trust
        positivity_multiplier = 0.5 + trust_factor   # 0.5x to 1.5x
        negativity_multiplier = 1.5 - trust_factor   # 1.5x to 0.5x

        joy_dampener = max(0.2, 1.0 - state.sadness)
        sad_dampener = max(0.2, 1.0 - state.joy)

        # 4. Continuous Stimulus Application (Weber-Fechner Law + Valence Gradient)
        if eff_valence > 0:
            joy_gain = self.MAX_GAIN["joy"] * (1.1 - state.joy) * positivity_multiplier * eff_valence * eff_intensity * joy_dampener
            delta.joy += joy_gain
            delta.sadness -= (joy_gain * 1.5)
            delta.irritation -= (joy_gain * 2.0)
            delta.trust += (self.MAX_GAIN["trust"] * 0.5 * eff_valence * eff_intensity) * (1.0 - state.trust)
            delta.comfort += 0.08 * eff_intensity * (1.0 - state.comfort)
        elif eff_valence < 0:
            abs_val = abs(eff_valence)
            sad_gain = self.MAX_GAIN["sadness"] * (1.1 - state.sadness) * negativity_multiplier * abs_val * eff_intensity * sad_dampener
            delta.sadness += sad_gain
            delta.joy -= (sad_gain * 1.5)
            # Only penalize trust on hostile/abusive interactions, NOT on empathetic melancholic sharing or playful pout
            if eff_emotion != "melancholic_care" and eff_emotion != "playful_pout":
                delta.trust -= 0.15 * negativity_multiplier * abs_val * eff_intensity
                delta.comfort -= 0.20 * abs_val * eff_intensity

        # 5. Archetype-Specific Modulation (8 Dimensions)
        if eff_emotion == "flustered_affection":
            delta.joy += 0.08 * eff_intensity
            delta.shyness += self.MAX_GAIN["shyness"] * eff_intensity * (1.0 - state.shyness)
            delta.comfort += 0.10 * eff_intensity * (1.0 - state.comfort)
        elif eff_emotion == "playful_pout":
            delta.irritation += 0.07 * eff_intensity
            delta.shyness += 0.15 * eff_intensity * (1.0 - state.shyness)
            # Playful pout does NOT penalize trust (The Pout Shield)
        elif eff_emotion == "melancholic_care":
            delta.sadness += 0.06 * eff_intensity
            delta.trust += (self.MAX_GAIN["trust"] * 0.8 * eff_intensity) * (1.0 - state.trust)
            delta.comfort += 0.08 * eff_intensity * (1.0 - state.comfort)
        elif eff_emotion == "cheerful_joy":
            delta.joy += 0.12 * eff_intensity
            delta.curiosity += 0.15 * eff_intensity * (1.0 - state.curiosity)
            delta.sadness -= 0.10 * eff_intensity
            delta.irritation -= 0.10 * eff_intensity
        elif eff_emotion == "guarded_cold":
            irr_gain = self.MAX_GAIN["irritation"] * (1.1 - state.irritation) * negativity_multiplier * eff_intensity
            delta.irritation += irr_gain
            delta.trust -= 0.25 * eff_intensity
            delta.attachment -= self.MAX_GAIN["attachment"] * 2.0 * eff_intensity
            delta.comfort -= 0.30 * eff_intensity
            delta.shyness -= state.shyness  # Real anger quenches shyness immediately
        elif eff_emotion == "neutral" or eff_emotion == "calm_warmth":
            delta.curiosity += 0.05 * eff_intensity * (1.0 - state.curiosity)
            delta.comfort += 0.05 * eff_intensity * (1.0 - state.comfort)

        # 6. Attachment Progression (Catalyzed by Shyness, Comfort & Joy)
        cur_shy = self._clamp(state.shyness + delta.shyness)
        cur_comf = self._clamp(state.comfort + delta.comfort)
        cur_joy = self._clamp(state.joy + delta.joy)
        attachment_catalyst = (0.015 * cur_shy + 0.010 * cur_comf + 0.005 * cur_joy) * (1.0 - state.attachment)

        if state.trust > 0.40 and eff_valence >= 0 and eff_emotion != "guarded_cold":
            delta.attachment += (self.MAX_GAIN["attachment"] * 0.5 * eff_intensity + attachment_catalyst) * (1.0 - state.attachment)
        elif eff_emotion == "guarded_cold" or eff_valence < -0.5:
            delta.attachment -= self.MAX_GAIN["attachment"] * 2.5 * negativity_multiplier * eff_intensity

        # 7. Antagonistic Cross-Inhibition Layer (Plutchik/Russell Coherence Engine)
        final_joy = state.joy + delta.joy
        final_sad = state.sadness + delta.sadness
        final_irr = state.irritation + delta.irritation

        # A. Joy & Sadness Cross-Inhibition
        if final_joy > 0.15 and final_sad > 0.15:
            inhibition = min(final_joy, final_sad) * 0.7
            delta.joy -= inhibition
            delta.sadness -= inhibition

        # B. Irritation suppresses Shyness (Anger quenches Romance)
        if final_irr > 0.25:
            shyness_inhibition_factor = max(0.0, 1.0 - 2.0 * final_irr)
            cur_final_shy = state.shyness + delta.shyness
            target_shy = cur_final_shy * shyness_inhibition_factor
            delta.shyness += (target_shy - cur_final_shy)

        # C. Irritation & Sadness suppress Comfort
        if final_irr > 0.20 or final_sad > 0.20:
            comfort_inhibition_factor = max(0.0, 1.0 - (final_irr * 1.2 + final_sad * 0.8))
            cur_final_comf = state.comfort + delta.comfort
            target_comf = cur_final_comf * comfort_inhibition_factor
            delta.comfort += (target_comf - cur_final_comf)

        # D. Sadness dampens Curiosity (No manic laughing when grieving)
        if final_sad > 0.30:
            curiosity_damp_factor = max(0.2, 1.0 - 0.75 * final_sad)
            cur_final_cur = state.curiosity + delta.curiosity
            target_cur = cur_final_cur * curiosity_damp_factor
            delta.curiosity += (target_cur - cur_final_cur)

        # 8. Emotional Withdrawal Penalty
        final_sad_post = state.sadness + delta.sadness
        final_irr_post = state.irritation + delta.irritation
        if final_sad_post > 0.15 and final_irr_post > 0.10:
            withdrawal_intensity = final_sad_post * final_irr_post
            withdrawal_penalty = min(0.10, withdrawal_intensity * 0.50)
            delta.attachment -= withdrawal_penalty

        # Apply and Clamp Deltas across all 8 Dimensions
        state.joy = self._clamp(state.joy + delta.joy)
        state.sadness = self._clamp(state.sadness + delta.sadness)
        state.trust = self._clamp(state.trust + delta.trust)
        state.irritation = self._clamp(state.irritation + delta.irritation)
        state.attachment = self._clamp(state.attachment + delta.attachment)
        state.shyness = self._clamp(state.shyness + delta.shyness)
        state.curiosity = self._clamp(state.curiosity + delta.curiosity)
        state.comfort = self._clamp(state.comfort + delta.comfort)

        log.debug(
            "8-Dimensional EmotionEngine update applied",
            archetype=eff_emotion,
            intensity=f"{eff_intensity:.2f}",
            valence=f"{eff_valence:.2f}",
            joy=f"{state.joy:.3f}",
            sadness=f"{state.sadness:.3f}",
            trust=f"{state.trust:.3f}",
            irritation=f"{state.irritation:.3f}",
            attachment=f"{state.attachment:.3f}",
            shyness=f"{state.shyness:.3f}",
            curiosity=f"{state.curiosity:.3f}",
            comfort=f"{state.comfort:.3f}",
        )
        return delta
