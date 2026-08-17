from dataclasses import dataclass
from uuid import UUID

@dataclass
class EmotionState:
    user_id: UUID
    joy: float = 0.10
    sadness: float = 0.00
    trust: float = 0.50
    attachment: float = 0.00
    irritation: float = 0.00
    shyness: float = 0.00
    curiosity: float = 0.20
    comfort: float = 0.50
    updated_at: int = 0
