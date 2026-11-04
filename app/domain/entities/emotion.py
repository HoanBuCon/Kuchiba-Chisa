from dataclasses import dataclass
from uuid import UUID

EMOTION_DIMENSIONS = (
    "joy",
    "sadness",
    "trust",
    "attachment",
    "irritation",
    "shyness",
    "curiosity",
    "comfort",
)


@dataclass
class EmotionState:
    user_id: UUID
    joy: float = 0.15
    sadness: float = 0.00
    trust: float = 0.50
    attachment: float = 0.00
    irritation: float = 0.00
    shyness: float = 0.00
    curiosity: float = 0.10
    comfort: float = 0.50
    updated_at: int = 0

    def values(self) -> dict[str, float]:
        """The eight RESONA dimensions by name."""
        return {name: getattr(self, name) for name in EMOTION_DIMENSIONS}


@dataclass(frozen=True)
class EmotionMutation:
    """One turn's additive emotion mutation, applied atomically to canonical state."""

    joy: float = 0.0
    sadness: float = 0.0
    trust: float = 0.0
    irritation: float = 0.0
    attachment: float = 0.0
    shyness: float = 0.0
    curiosity: float = 0.0
    comfort: float = 0.0
