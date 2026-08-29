import math
import time
from typing import Dict, Any, Optional
from app.domain.entities.emotion import EmotionState


class AmbientMoodManager:
    """
    Manages Server-Level Ambient Emotional Resonance using continuous exponential decay.
    
    In a shared community/group environment, Chisa's transient emotional channels
    (joy, sadness, irritation, shyness, curiosity, comfort) form a collective living
    ambient state across all interactions in the server. Relational bonds (trust, attachment)
    remain strictly individual per user.
    """

    KUUDERE_BASELINE: Dict[str, float] = {
        "joy": 0.40,
        "sadness": 0.10,
        "irritation": 0.10,
        "shyness": 0.0,
        "curiosity": 0.20,
        "comfort": 0.50,
    }

    # Half-life of 30 minutes (1800 seconds) for transient mood return to equilibrium
    HALF_LIFE_SECONDS: float = 1800.0
    TAU: float = HALF_LIFE_SECONDS / math.log(2)  # ~2597.07 seconds

    @classmethod
    def calculate_decay(
        cls,
        stored_state: Optional[Dict[str, Any]],
        current_time: Optional[float] = None,
    ) -> Dict[str, float]:
        """
        Applies exponential decay towards the Kuudere baseline:
        E(t) = Baseline + (Stored - Baseline) * exp(-delta_t / tau)
        """
        now = current_time if current_time is not None else time.time()
        if not stored_state or not isinstance(stored_state, dict):
            return dict(cls.KUUDERE_BASELINE)

        last_updated = float(stored_state.get("last_updated_at", now))
        delta_t = max(0.0, now - last_updated)
        decay_factor = math.exp(-delta_t / cls.TAU)

        decayed = {}
        for channel, baseline_val in cls.KUUDERE_BASELINE.items():
            stored_val = float(stored_state.get(channel, baseline_val))
            decayed_val = baseline_val + (stored_val - baseline_val) * decay_factor
            # Clamp between 0.0 and 1.0
            decayed[channel] = max(0.0, min(1.0, round(decayed_val, 4)))

        return decayed

    @classmethod
    def synthesize_ambient_into_emotion(
        cls,
        emotion: EmotionState,
        ambient_mood: Dict[str, float],
    ) -> None:
        """
        Blends the server-level ambient mood into the speaker's transient emotion channels.
        Trust and Attachment remain untouched (strictly individual).
        """
        if not ambient_mood:
            return

        emotion.joy = ambient_mood.get("joy", emotion.joy)
        emotion.sadness = ambient_mood.get("sadness", emotion.sadness)
        emotion.irritation = ambient_mood.get("irritation", emotion.irritation)
        emotion.shyness = ambient_mood.get("shyness", getattr(emotion, "shyness", 0.0))
        emotion.curiosity = ambient_mood.get("curiosity", getattr(emotion, "curiosity", 0.20))
        emotion.comfort = ambient_mood.get("comfort", getattr(emotion, "comfort", 0.50))

    @classmethod
    def extract_ambient_snapshot(
        cls,
        emotion: EmotionState,
        timestamp: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Captures the post-interaction transient emotion channels to persist as the new
        Server-Level Ambient State.
        """
        now = timestamp if timestamp is not None else time.time()
        return {
            "joy": max(0.0, min(1.0, round(emotion.joy, 4))),
            "sadness": max(0.0, min(1.0, round(emotion.sadness, 4))),
            "irritation": max(0.0, min(1.0, round(emotion.irritation, 4))),
            "shyness": max(0.0, min(1.0, round(getattr(emotion, "shyness", 0.0), 4))),
            "curiosity": max(0.0, min(1.0, round(getattr(emotion, "curiosity", 0.20), 4))),
            "comfort": max(0.0, min(1.0, round(getattr(emotion, "comfort", 0.50), 4))),
            "last_updated_at": now,
        }
