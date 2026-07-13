from dataclasses import dataclass, field
from typing import Optional
from uuid import UUID

@dataclass
class UserStats:
    user_id: UUID
    interaction_count: int = 0
    last_seen: int = 0

@dataclass
class User:
    id: UUID
    username: str
    is_active: bool = True
    discord_id: Optional[str] = None
