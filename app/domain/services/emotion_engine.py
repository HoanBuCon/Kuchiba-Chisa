"""
EmotionEngine — Domain Service (RESONA Engine: Relational & Environmental Synthesis of Organic Neuro-Affect)
Applies non-linear dynamic matrix updates, ambient server resonance, and relational dynamics to EmotionState after each conversation turn.

Design principles:
- Pure domain logic: no HTTP, no DB calls directly.
- Dual-Flag Matrix with Variance Dispersion (reaction + user_stance + intensity + variance).
- Backward-compatible with legacy sentiment_analysis (primary_emotion, valence, intensity) and boolean flags.
- Relational Resonance Matrix (Synergy Modifiers, Pout Shield, Trust Protection).
- Continuous Non-linear Saturation Headroom Law & Homeostasis Exponential Decay.
"""

from __future__ import annotations
import math
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, Optional
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

VALID_STANCES = {
    "loving",
    "playful",
    "vulnerable",
    "neutral",
    "hostile"
}


# ── 1. Base Profiles for 7 Archetypes (6 Mood Dimensions) ───────
ARCHETYPE_PROFILES: Dict[str, Dict[str, float]] = {
    "flustered_affection": {"shyness": 0.40, "joy": 0.15, "comfort": 0.20, "sadness": 0.00, "irritation": 0.00, "curiosity": 0.05},
    "playful_pout":        {"shyness": 0.20, "joy": 0.05, "comfort": 0.05, "sadness": 0.00, "irritation": 0.25, "curiosity": 0.10},
    "melancholic_care":    {"shyness": 0.05, "joy": -0.20, "comfort": 0.25, "sadness": 0.35, "irritation": 0.00, "curiosity": 0.10},
    "cheerful_joy":        {"shyness": 0.10, "joy": 0.55, "comfort": 0.20, "sadness": -0.40, "irritation": -0.20, "curiosity": 0.25},
    "guarded_cold":        {"shyness": -0.30, "joy": -0.30, "comfort": -0.40, "sadness": 0.10, "irritation": 0.50, "curiosity": -0.20},
    "calm_warmth":         {"shyness": 0.05, "joy": 0.10, "comfort": 0.30, "sadness": 0.00, "irritation": -0.05, "curiosity": 0.15},
    "neutral":             {"shyness": 0.00, "joy": 0.00, "comfort": 0.05, "sadness": 0.00, "irritation": 0.00, "curiosity": 0.10},
}


# ── 2. Relational Base Deltas according to user_stance ──────────
STANCE_RELATION_DELTAS: Dict[str, Dict[str, float]] = {
    "loving":     {"trust_gain": +0.04, "attachment_gain": +0.03},
    "playful":    {"trust_gain": +0.015, "attachment_gain": +0.015},
    "vulnerable": {"trust_gain": +0.05, "attachment_gain": +0.02}, # Cùng chia sẻ tâm sự -> Trust tăng mạnh
    "neutral":    {"trust_gain": +0.005, "attachment_gain": +0.005},
    "hostile":    {"trust_gain": -0.20, "attachment_gain": -0.10}, # Chỉ duy nhất trường hợp này mới trừ Trust
}


# ── 3. Relational Resonance Matrix (Synergy Modifiers) ──────────
RESONANCE_MATRIX: Dict[tuple[str, str], Dict[str, Any]] = {
    # 1. Nhóm Tình Cảm & Thả Thính (Loving)
    ("loving", "flustered_affection"): {
        "shyness_mult": 1.5, "attachment_mult": 1.6, "trust_mult": 1.3,
        "comfort_mult": 1.2, "joy_mult": 1.3, "pout_shield": True
    },
    ("loving", "calm_warmth"): {
        "comfort_mult": 1.4, "trust_mult": 1.2, "attachment_mult": 1.3,
        "pout_shield": True
    },
    ("loving", "guarded_cold"): {
        # Unwelcome advances / inappropriate romantic pressure -> Chisa rejects
        "trust_mult": -1.0, "attachment_mult": 0.0, "irritation_gain": 0.10, "comfort_mult": 0.3,
        "pout_shield": False
    },

    # 2. Nhóm Trêu Ghẹo (Playful)
    ("playful", "playful_pout"): {
        "irritation_gain": 0.08, "attachment_mult": 1.4, "trust_mult": 1.0,
        "pout_shield": True
    },
    ("playful", "flustered_affection"): {
        "shyness_mult": 1.6, "joy_mult": 1.2, "trust_mult": 1.1,
        "pout_shield": True
    },
    ("playful", "guarded_cold"): {
        # Boundary breach / vulgar, offensive, or crude teasing -> Cold withdrawal
        "trust_mult": -1.5, "attachment_mult": 0.0, "attachment_penalty_mult": 1.5, "irritation_gain": 0.15,
        "pout_shield": False
    },

    # 3. Nhóm Tâm Sự Yếu Lòng & An Ủi (Vulnerable)
    ("vulnerable", "melancholic_care"): {
        "trust_mult": 1.8, "comfort_mult": 1.5, "sadness_mult": 1.2, "attachment_mult": 1.4,
        "pout_shield": True
    },
    ("vulnerable", "calm_warmth"): {
        "trust_mult": 1.5, "comfort_mult": 1.6, "attachment_mult": 1.2,
        "pout_shield": True
    },
    ("vulnerable", "guarded_cold"): {
        # Deceptive / manipulative vulnerability -> Distrust
        "trust_mult": 0.0, "attachment_mult": 0.0, "curiosity_mult": 0.5,
        "pout_shield": False
    },

    # 4. Nhóm Xung Đột & Thù Địch (Hostility)
    ("hostile", "guarded_cold"): {
        "trust_penalty_mult": 1.8, "attachment_penalty_mult": 1.5, "irritation_mult": 1.8, "shyness_drain": True,
        "pout_shield": False
    },
    ("hostile", "melancholic_care"): {
        "sadness_mult": 2.0, "attachment_penalty_mult": 1.8, "trust_penalty_mult": 1.5,
        "pout_shield": False
    },
    ("hostile", "playful_pout"): {
        "pout_shield": False, "trust_penalty_mult": 1.2, "irritation_mult": 1.5
    },

    # 5. Nhóm Trung Tính (Neutral)
    ("neutral", "playful_pout"): {
        "irritation_gain": 0.05, "trust_mult": 1.0, "attachment_mult": 1.0,
        "pout_shield": True
    },
    ("neutral", "guarded_cold"): {
        "trust_mult": -0.5, "attachment_mult": 0.0, "pout_shield": False
    },
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
    reaction: str = "calm_warmth"
    user_stance: str = "neutral"
    intensity: float = 0.5
    variance: float = 0.0
    primary_emotion: str = "calm_warmth"  # Backward-compatible alias
    valence: float = 0.0                 # Backward-compatible alias


class EmotionEngine:
    """
    Continuous rule-based & cognitive-affective engine that computes emotion deltas
    from Dual-Flag Matrix, Continuous Variance, Intensity, and 8 Emotional & Relational Channels.

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
        reaction: str = None,
        user_stance: str = None,
        variance: float = None,
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
        Apply emotion deltas based on DEHA 3.0 Dual-Flag Matrix (reaction, user_stance, intensity, variance)
        with 100% backward compatibility for DEHA 2.0 (primary_emotion, valence, intensity) and legacy booleans.
        """
        # Ensure state has all 8 fields with safe baselines
        for key, val in self.BASELINES.items():
            if not hasattr(state, key) or getattr(state, key) is None:
                setattr(state, key, val)

        # 1. Resolve Inputs into Normalized DEHA 3.0 Variables
        raw_reaction = reaction
        raw_stance = user_stance
        raw_intensity = intensity
        raw_variance = variance

        if sentiment_analysis and isinstance(sentiment_analysis, dict):
            # Prefer DEHA 3.0 keys, fallback to DEHA 2.0 keys
            raw_reaction = sentiment_analysis.get("reaction") or sentiment_analysis.get("primary_emotion") or raw_reaction
            raw_stance = sentiment_analysis.get("user_stance") or raw_stance
            raw_intensity = sentiment_analysis.get("intensity") if raw_intensity is None else raw_intensity
            if raw_intensity is None:
                raw_intensity = sentiment_analysis.get("intensity", 0.5)
            
            raw_variance = sentiment_analysis.get("variance") if raw_variance is None else raw_variance
            if raw_variance is None:
                raw_variance = sentiment_analysis.get("valence", 0.0)

        # Fallback from direct keyword arguments
        if raw_reaction is None and primary_emotion is not None:
            raw_reaction = primary_emotion
        if raw_variance is None and valence is not None:
            raw_variance = valence

        # Legacy Boolean Mapping if no structured sentiment provided
        if raw_reaction is None and raw_intensity is None:
            if is_rude:
                raw_intensity = 0.9 if not is_neutral else 0.6
                raw_variance = -0.9
                raw_reaction = "guarded_cold"
                raw_stance = "hostile"
            elif is_negative:
                raw_intensity = 0.8 if not is_neutral else 0.4
                raw_variance = -0.7
                raw_reaction = "melancholic_care" if chisa_sad else ("playful_pout" if chisa_annoyed else "calm_warmth")
                raw_stance = "vulnerable" if chisa_sad else ("playful" if chisa_annoyed else "neutral")
            elif is_positive:
                raw_intensity = 0.85 if not is_neutral else 0.35
                raw_variance = 0.8
                raw_reaction = "flustered_affection" if chisa_flustered else ("cheerful_joy" if chisa_happy else "calm_warmth")
                raw_stance = "loving"
            elif chisa_sad:
                raw_intensity = 0.8
                raw_variance = -0.7
                raw_reaction = "melancholic_care"
                raw_stance = "vulnerable"
            elif chisa_annoyed:
                raw_intensity = 0.8
                raw_variance = -0.4
                raw_reaction = "playful_pout"
                raw_stance = "playful"
            elif chisa_happy:
                raw_intensity = 0.8
                raw_variance = 0.8
                raw_reaction = "cheerful_joy"
                raw_stance = "loving"
            elif chisa_flustered:
                raw_intensity = 0.85
                raw_variance = 0.8
                raw_reaction = "flustered_affection"
                raw_stance = "loving"
            else:
                raw_intensity = 0.2
                raw_variance = 0.0
                raw_reaction = "neutral" if is_neutral else "calm_warmth"
                raw_stance = "neutral"

        # Defaults and Sanitization
        try:
            eff_intensity = self._clamp(float(raw_intensity if raw_intensity is not None else 0.5), 0.0, 1.0)
        except (ValueError, TypeError):
            eff_intensity = 0.5

        try:
            eff_variance = self._clamp(float(raw_variance if raw_variance is not None else 0.0), -1.0, 1.0)
        except (ValueError, TypeError):
            eff_variance = 0.0

        eff_reaction = str(raw_reaction or "calm_warmth").lower().strip()
        if eff_reaction not in VALID_ARCHETYPES:
            eff_reaction = "calm_warmth"

        # Infer user_stance if not explicitly provided
        if not raw_stance:
            if eff_reaction == "guarded_cold" and eff_variance < -0.5:
                eff_user_stance = "hostile"
            elif eff_reaction == "flustered_affection":
                eff_user_stance = "loving"
            elif eff_reaction == "playful_pout":
                eff_user_stance = "playful"
            elif eff_reaction == "melancholic_care":
                eff_user_stance = "vulnerable"
            elif is_rude:
                eff_user_stance = "hostile"
            elif is_positive:
                eff_user_stance = "loving"
            else:
                eff_user_stance = "neutral"
        else:
            eff_user_stance = str(raw_stance).lower().strip()
            if eff_user_stance not in VALID_STANCES:
                eff_user_stance = "neutral"

        delta = EmotionDelta(
            reaction=eff_reaction,
            user_stance=eff_user_stance,
            intensity=eff_intensity,
            variance=eff_variance,
            primary_emotion=eff_reaction,
            valence=eff_variance,
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
            "attachment": float("inf"), # Attachment preserves long-term bond, no passive decay
            "shyness": 900.0,        # 15 minutes
            "curiosity": 1800.0,     # 30 minutes
            "comfort": 7200.0,       # 2 hours
        }

        decay_factor = {}
        for emotion, half_life in HALF_LIVES.items():
            if half_life == float("inf"):
                decay_factor[emotion] = 1.0
            else:
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

        # 3. Lookup Relational Resonance Matrix & Synergies
        synergy = RESONANCE_MATRIX.get((eff_user_stance, eff_reaction), {})
        synergy_allows_pout = synergy.get("pout_shield", True) is not False
        is_natural_pout = (state.trust >= 0.65 and state.attachment >= 0.25 and eff_reaction == "playful_pout")
        pout_shield = (synergy.get("pout_shield", False) or is_natural_pout) and synergy_allows_pout and (eff_user_stance != "hostile")

        # Pre-calculate Psychological Multipliers
        trust_factor = state.trust
        positivity_multiplier = 0.5 + trust_factor   # 0.5x to 1.5x
        negativity_multiplier = 1.5 - trust_factor   # 1.5x to 0.5x

        joy_dampener = max(0.2, 1.0 - state.sadness)
        sad_dampener = max(0.2, 1.0 - state.joy)

        # 4. Non-linear Matrix Dispersion across 6 Mood Channels
        base_profile = ARCHETYPE_PROFILES.get(eff_reaction, ARCHETYPE_PROFILES["calm_warmth"])

        for channel in ["joy", "sadness", "shyness", "curiosity", "comfort", "irritation"]:
            base_weight = base_profile.get(channel, 0.0)
            synergy_mult = synergy.get(f"{channel}_mult", 1.0)
            bonus_gain = synergy.get(f"{channel}_gain", 0.0) or synergy.get(f"{channel}_bonus", 0.0)

            # Variance Modifier
            var_mod = 0.0
            if channel == "sadness" and eff_variance < 0:
                var_mod = abs(eff_variance) * 0.15
            elif channel == "joy" and eff_variance > 0:
                var_mod = eff_variance * 0.15
            elif channel == "joy" and eff_variance < 0:
                var_mod = eff_variance * 0.15

            raw_stimulus = (base_weight * eff_intensity * synergy_mult) + var_mod + bonus_gain

            # Apply Damping & Trust Multipliers
            if channel == "joy":
                raw_stimulus *= positivity_multiplier * joy_dampener
            elif channel == "sadness":
                raw_stimulus *= negativity_multiplier * sad_dampener
            elif channel == "irritation" and eff_reaction == "guarded_cold":
                raw_stimulus *= negativity_multiplier

            # Saturation Headroom Law
            current_val = getattr(state, channel)
            if raw_stimulus >= 0:
                headroom = 1.0 - current_val
            else:
                headroom = current_val

            channel_delta = raw_stimulus * headroom
            current_delta = getattr(delta, channel)
            setattr(delta, channel, current_delta + channel_delta)

        # 5. Relational Progression: Trust & Attachment Dynamics
        stance_info = STANCE_RELATION_DELTAS.get(eff_user_stance, STANCE_RELATION_DELTAS["neutral"])
        trust_base = stance_info["trust_gain"]
        trust_mult = synergy.get("trust_mult", 1.0)
        trust_pen_mult = synergy.get("trust_penalty_mult", 1.0)

        # Boundary breach / Unsafe / Guarded condition
        is_guarded_or_unsafe = (eff_reaction == "guarded_cold") or (not pout_shield and (eff_user_stance == "hostile" or trust_mult < 0))

        if eff_user_stance == "hostile" and not pout_shield:
            delta.trust += trust_base * eff_intensity * trust_pen_mult * negativity_multiplier * state.trust
        elif trust_mult < 0 or eff_reaction == "guarded_cold":
            # Negative trust multiplier from resonance matrix (e.g. playful + guarded_cold)
            penalty_intensity = eff_intensity * abs(trust_mult if trust_mult < 0 else 1.0)
            delta.trust += -0.035 * penalty_intensity * negativity_multiplier * (1.0 + abs(eff_variance)) * state.trust
        elif trust_base > 0 and not is_guarded_or_unsafe:
            trust_headroom = 1.0 - state.trust
            delta.trust += trust_base * eff_intensity * trust_mult * trust_headroom

        # Attachment Progression (Catalyzed by Shyness, Comfort & Joy)
        cur_shy = self._clamp(state.shyness + delta.shyness)
        cur_comf = self._clamp(state.comfort + delta.comfort)
        cur_joy = self._clamp(state.joy + delta.joy)
        attachment_catalyst = (0.015 * cur_shy + 0.010 * cur_comf + 0.005 * cur_joy) * (1.0 - state.attachment)

        attach_base = stance_info["attachment_gain"]
        attach_mult = synergy.get("attachment_mult", 1.0)
        attach_pen_mult = synergy.get("attachment_penalty_mult", 1.0)

        if is_guarded_or_unsafe or attach_mult <= 0.0:
            # Zero positive attachment growth when guarded or unsafe; apply penalty if hostile or boundary breach
            if eff_reaction == "guarded_cold" or eff_user_stance == "hostile" or attach_pen_mult > 1.0:
                delta.attachment -= 0.015 * eff_intensity * attach_pen_mult * negativity_multiplier * (1.0 + abs(eff_variance))
        elif attach_base > 0:
            if state.trust >= 0.35:
                raw_attach_gain = (attach_base * eff_intensity * attach_mult + attachment_catalyst) * (1.0 - state.attachment)
                if state.trust > 0.60 and is_neutral:
                    raw_attach_gain = max(raw_attach_gain, 0.010 * (1.0 - state.attachment))
                # Single-turn growth rate cap (+0.03 max / turn)
                delta.attachment += min(0.03, raw_attach_gain)
        elif eff_user_stance == "hostile":
            delta.attachment += attach_base * eff_intensity * attach_pen_mult * negativity_multiplier

        # 6. Antagonistic Cross-Inhibition Layer (Plutchik/Russell Coherence Engine)
        final_joy = state.joy + delta.joy
        final_sad = state.sadness + delta.sadness
        final_irr = state.irritation + delta.irritation

        # A. Joy & Sadness Cross-Inhibition
        if final_joy > 0.15 and final_sad > 0.15:
            inhibition = min(final_joy, final_sad) * 0.5
            delta.joy -= inhibition
            delta.sadness -= inhibition

        # B. Real Anger suppresses Shyness (Pout Shield preserves Shyness)
        if final_irr > 0.35 and not pout_shield:
            shyness_inhibition_factor = max(0.0, 1.0 - 2.0 * final_irr)
            cur_final_shy = state.shyness + delta.shyness
            target_shy = cur_final_shy * shyness_inhibition_factor
            delta.shyness += (target_shy - cur_final_shy)

        # C. Irritation & Sadness suppress Comfort (Except during gentle solace / confiding)
        if (final_irr > 0.25 and not pout_shield) or (final_sad > 0.35 and eff_reaction != "melancholic_care"):
            comfort_inhibition_factor = max(0.0, 1.0 - (final_irr * 1.0 + final_sad * 0.8))
            cur_final_comf = state.comfort + delta.comfort
            target_comf = cur_final_comf * comfort_inhibition_factor
            delta.comfort += (target_comf - cur_final_comf)

        # D. Sadness dampens Curiosity
        if final_sad > 0.30:
            curiosity_damp_factor = max(0.2, 1.0 - 0.75 * final_sad)
            cur_final_cur = state.curiosity + delta.curiosity
            target_cur = cur_final_cur * curiosity_damp_factor
            delta.curiosity += (target_cur - cur_final_cur)

        # E. Emotional Withdrawal Penalty
        final_sad_post = state.sadness + delta.sadness
        final_irr_post = state.irritation + delta.irritation
        is_real_anger_or_withdrawal = (eff_reaction == "guarded_cold") or (eff_user_stance == "hostile") or (final_irr_post >= 0.30 and not pout_shield)
        if is_real_anger_or_withdrawal and (final_sad_post > 0.08 or final_irr_post > 0.15) and not pout_shield:
            withdrawal_intensity = (final_sad_post * 0.5 + final_irr_post * 1.0)
            withdrawal_penalty = min(0.08, withdrawal_intensity * 0.04 * (1.0 + abs(eff_variance)))
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
            "DEHA 3.0 EmotionEngine update applied",
            reaction=eff_reaction,
            user_stance=eff_user_stance,
            intensity=f"{eff_intensity:.2f}",
            variance=f"{eff_variance:.2f}",
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
