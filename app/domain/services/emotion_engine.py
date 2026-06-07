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

from app.infrastructure.logging.logger import get_logger

if TYPE_CHECKING:
    from app.infrastructure.database.models.emotion_state import EmotionState

log = get_logger(__name__)


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

    @classmethod
    def get_emotional_dyad(cls, joy: float, sadness: float, trust: float, irritation: float, attachment: float) -> str:
        """
        Calculates Plutchik emotional dyads and returns a descriptive Vietnamese string
        representing Chisa's current complex psychological state.
        """
        complexes = []
        
        # 1. Love / Yêu mến (Joy + Trust)
        if joy > 0.5 and trust > 0.6:
            complexes.append("Yêu mến và tin tưởng tuyệt đối (Love)")
        elif joy > 0.3 and trust > 0.5:
            complexes.append("Ấm áp và dễ chịu (Warmth)")
            
        # 2. Guarded / Đề phòng (Irritation + Low Trust)
        if irritation > 0.4 and trust < 0.4:
            complexes.append("Đang giận dữ và vô cùng đề phòng, hoài nghi (Guarded / Hostile)")
        elif irritation > 0.3:
            complexes.append("Bực dọc, dỗi hờn nhẹ (Annoyed / Tsundere spikes)")
            
        # 3. Frustration / Bất lực, uất ức (Sadness + Irritation)
        if sadness > 0.4 and irritation > 0.3:
            complexes.append("Uất ức, bất lực và dỗi hờn (Frustrated / Bitter)")
        elif sadness > 0.4:
            complexes.append("U sầu, cảm thấy cô độc, tủi thân (Melancholy / Lonely)")
            
        # 4. Attachment & Shyness / Ngượng ngùng (Joy + Attachment)
        if attachment > 0.4 and joy > 0.4:
            complexes.append("Ngượng ngùng tột độ nhưng vô cùng hạnh phúc (Highly affectionate & Flustered)")
        elif attachment > 0.3:
            complexes.append("Gắn bó sâu sắc, thầm lặng hướng về Senpai (Deeply attached)")
            
        # Default fallback
        if not complexes:
            if trust > 0.7:
                return "Bình yên, tin cậy và sẵn sàng lắng nghe (Tranquil & Trusting)"
            return "Bình thường, điềm tĩnh và lý trí (Neutral & Analytical)"
            
        return ", ".join(complexes)

    # ── Intensity Damping Constants ────────────────────────────────
    # When is_neutral=True, emotion gains are multiplied by these factors.
    # This prevents casual/mild messages from spiking emotions as strongly
    # as clearly heartfelt or intensely emotional messages.
    NEUTRAL_DAMPER = {
        "joy": 0.30,         # Casual warmth → only 30% of full joy gain
        "sadness": 0.35,     # Mild complaint → 35% of sadness gain
        "irritation": 0.55,  # Rude+neutral is contradictory; less dampening
    }

    def update(
        self,
        state: "EmotionState",
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
        Apply emotion deltas based on flags provided by the LLM Sentiment Classifier.

        is_neutral acts as an emotional intensity gate:
          - is_neutral=True  → emotion is mild/casual  → gains are dampened
          - is_neutral=False → emotion is intense/clear → full gains applied

        Returns an EmotionDelta summary for logging.
        """

        delta = EmotionDelta()

        # 1. Time-Aware Psychological Homeostasis (Exponential Decay toward Baseline)
        current_time_ms = int(time.time() * 1000)
        
        # Calculate elapsed time in seconds since last update
        elapsed_sec = 0.0
        if state.updated_at and state.updated_at > 0:
            elapsed_sec = max(0.0, (current_time_ms - state.updated_at) / 1000.0)
            
        # Persist the current timestamp onto the state
        state.updated_at = current_time_ms

        # Half-lives in seconds for exponential decay:
        # e.g., Joy decays by half every 45 minutes; Irritation decays by half every 15 minutes.
        HALF_LIVES = {
            "joy": 2700.0,        # 45 minutes
            "sadness": 10800.0,    # 3 hours
            "trust": 604800.0,     # 7 days (trust decays extremely slowly if not interacted)
            "irritation": 900.0,   # 15 minutes (anger cools down quickly)
        }

        decay_factor = {}
        for emotion, half_life in HALF_LIVES.items():
            decay_constant = 0.69314718056 / half_life
            decay_factor[emotion] = math.exp(-decay_constant * elapsed_sec)

        # Calculate decay delta: decayed_value - current_value
        delta.joy = (self.BASELINES["joy"] + (state.joy - self.BASELINES["joy"]) * decay_factor["joy"]) - state.joy
        delta.sadness = (self.BASELINES["sadness"] + (state.sadness - self.BASELINES["sadness"]) * decay_factor["sadness"]) - state.sadness
        delta.trust = (self.BASELINES["trust"] + (state.trust - self.BASELINES["trust"]) * decay_factor["trust"]) - state.trust
        delta.irritation = (self.BASELINES["irritation"] + (state.irritation - self.BASELINES["irritation"]) * decay_factor["irritation"]) - state.irritation
        
        # 2. Pre-calculate Psychological Multipliers (Trust & Attachment)
        # Low trust (<0.5) dampens Joy and amplifies Negativity
        # High trust (>0.5) amplifies Joy and dampens Negativity
        trust_factor = state.trust
        positivity_multiplier = 0.5 + trust_factor  # ranges 0.5x to 1.5x
        negativity_multiplier = 1.5 - trust_factor  # ranges 1.5x to 0.5x

        # Plutchik Mutual Exclusion Dampeners (Sadness dampens Joy, Joy dampens Sadness)
        joy_dampener = max(0.2, 1.0 - state.sadness)
        sad_dampener = max(0.2, 1.0 - state.joy)

        # 3. Stimulus Application (Weber-Fechner Law + Trust Modulation)
        if is_positive:
            # Intensity gate: casual warmth gets a fraction of the full joy gain
            joy_intensity = self.NEUTRAL_DAMPER["joy"] if is_neutral else 1.0
            joy_gain = self.MAX_GAIN["joy"] * (1.1 - state.joy) * positivity_multiplier * joy_intensity * joy_dampener
            delta.joy += joy_gain
            delta.sadness -= (joy_gain * 1.5)      # Suppresses sadness
            delta.irritation -= (joy_gain * 2.0)   # Heavily suppresses irritation
            
            # Trust is HARD to earn; casual positives earn even less
            trust_intensity = 0.25 if is_neutral else 0.5
            delta.trust += (self.MAX_GAIN["trust"] * trust_intensity) * (1.0 - state.trust)
            
        if is_negative:
            # Intensity gate: mild complaints cause less sadness than genuine distress
            sad_intensity = self.NEUTRAL_DAMPER["sadness"] if is_neutral else 1.0
            sad_gain = self.MAX_GAIN["sadness"] * (1.1 - state.sadness) * negativity_multiplier * sad_intensity * sad_dampener
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
            
        # 3.5 Chisa Self-Emotion Triggers (with Plutchik Dampening & Opposition Suppression)
        if chisa_sad:
            delta.sadness += 0.12
            # Sadness actively suppresses joy!
            delta.joy -= 0.15 * state.sadness
        if chisa_annoyed:
            delta.irritation += 0.10
            delta.joy -= 0.10 * state.irritation
            delta.trust -= 0.05
        if chisa_happy:
            delta.joy += 0.08
            # Joy actively suppresses sadness and irritation!
            delta.sadness -= 0.10 * state.joy
            delta.irritation -= 0.10 * state.joy
        if chisa_flustered:
            delta.joy += 0.05
            # Only grow attachment from flustered if Chisa isn't simultaneously hurt
            if not chisa_sad and not chisa_annoyed:
                delta.attachment += 0.01

        # 4. Attachment progression (Asymmetrical progression)
        # Attachment only grows if trust is high without rudeness, and grows very slowly
        if state.trust > 0.6 and not is_rude and not is_negative:
            delta.attachment += (self.MAX_GAIN["attachment"] * 0.5) * (1.0 - state.attachment)
        elif is_rude or is_negative:
            # Attachment drops rapidly on abuse
            delta.attachment += -self.MAX_GAIN["attachment"] * 2.5 * negativity_multiplier

        # 4.5 Plutchik Cross-Emotion Inhibition Layer
        # Enforces mathematical opposition between conflicting emotion channels on final values
        final_joy = state.joy + delta.joy
        final_sad = state.sadness + delta.sadness
        if final_joy > 0.15 and final_sad > 0.15:
            # The stronger emotion suppresses the weaker one
            inhibition = min(final_joy, final_sad) * 0.7
            delta.joy -= inhibition
            delta.sadness -= inhibition

        # 4.6 Emotional Withdrawal — Sadness + Irritation compound penalty on Attachment
        # When Chisa is simultaneously hurt (sad) AND annoyed (irritated), she emotionally
        # withdraws from Senpai. This models the psychological reality that sustained
        # hurt + anger causes distancing, regardless of what the LLM classifier flagged.
        final_sad_post = state.sadness + delta.sadness
        final_irr_post = state.irritation + delta.irritation
        SAD_WITHDRAWAL_THRESHOLD = 0.15    # Sadness must be noticeable
        IRR_WITHDRAWAL_THRESHOLD = 0.10    # Irritation must also be present
        
        if final_sad_post > SAD_WITHDRAWAL_THRESHOLD and final_irr_post > IRR_WITHDRAWAL_THRESHOLD:
            # Penalty scales with the product of sadness × irritation
            # Mild: 0.2 × 0.1 = 0.02 → penalty ≈ 0.02
            # Severe: 0.5 × 0.4 = 0.20 → penalty ≈ 0.10
            withdrawal_intensity = final_sad_post * final_irr_post
            withdrawal_penalty = min(0.10, withdrawal_intensity * 0.50)
            delta.attachment -= withdrawal_penalty
            log.debug(
                "Emotional withdrawal triggered",
                sadness=f"{final_sad_post:.3f}",
                irritation=f"{final_irr_post:.3f}",
                withdrawal_penalty=f"{withdrawal_penalty:.4f}",
            )

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
            signals={
                "pos": is_positive,
                "neg": is_negative,
                "rude": is_rude,
                "neutral": is_neutral,
                "chisa_sad": chisa_sad,
                "chisa_happy": chisa_happy,
                "chisa_annoyed": chisa_annoyed,
                "chisa_flustered": chisa_flustered,
            },
        )
        return delta
