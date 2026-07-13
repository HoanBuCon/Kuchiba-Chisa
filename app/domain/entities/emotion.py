from dataclasses import dataclass
from uuid import UUID

@dataclass
class EmotionState:
    user_id: UUID
    joy: float = 0.0
    sadness: float = 0.0
    trust: float = 0.0
    attachment: float = 0.0
    irritation: float = 0.0
    updated_at: int = 0
