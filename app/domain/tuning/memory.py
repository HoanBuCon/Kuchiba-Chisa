from dataclasses import dataclass

@dataclass(frozen=True)
class MemoryTuning:
    """Tuning parameters for memory extraction, scoring, and deduplication."""
    SEMANTIC_DEDUP_THRESHOLD: float = 0.85
    TIER_BOOST_RELATIONSHIP: float = 0.2
    TIER_BOOST_CORE: float = 0.1
    EMOTION_MAGNITUDE_MULTIPLIER: float = 2.5
    NEUTRAL_EMOTION_BOOST: float = 0.2
    IMPORTANCE_SCORE: float = 0.5


@dataclass(frozen=True)
class EmotionTuning:
    """Tuning parameters for emotional state thresholds."""
    LABEL_THRESHOLD_LOW: float = 0.35
    LABEL_THRESHOLD_MEDIUM: float = 0.70
    MOOD_THRESHOLD: float = 0.5
