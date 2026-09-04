import enum
import time
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class MemoryType(str, enum.Enum):
    FACT = "fact"
    EMOTIONAL = "emotional"
    EPISODIC = "episodic"
    SUMMARY = "summary"

class MemoryTier(str, enum.Enum):
    CASUAL = "casual"
    PERSONAL = "personal"
    CRITICAL = "critical"

class MemoryPayload(BaseModel):
    """
    Strict typing for vector payload metadata stored in Vector DB.
    """
    user_id: str
    conversation_id: str | None = None
    memory_type: str
    memory_tier: MemoryTier = MemoryTier.CASUAL
    importance_score: float = Field(ge=0.0, le=1.0)
    emotion: dict[str, float] = Field(default_factory=dict)
    created_at: int
    expires_at: int | None = None
    sensitivity: str = "standard"
    text_content: str
    
    model_config = ConfigDict(extra="allow")


class GuildMemoryPayload(BaseModel):
    """
    Strict typing for server-shared knowledge, events, and culture stored in Qdrant guild_memories.
    """
    guild_id: str
    user_id: str
    channel_id: str | None = None
    memory_type: str = "guild_event"  # "guild_event" | "guild_culture" | "guild_rule" | "guild_inside_joke"
    memory_tier: MemoryTier = MemoryTier.PERSONAL
    importance_score: float = Field(default=0.8, ge=0.0, le=1.0)
    created_at: int = Field(default_factory=lambda: int(time.time()))
    expires_at: int | None = None
    sensitivity: str = "standard"
    text_content: str
    recorded_by_speaker: str | None = None
    
    model_config = ConfigDict(extra="allow")

@dataclass
class MemoryMetadata:
    id: UUID
    user_id: UUID
    memory_type: MemoryType
    created_at: datetime
    updated_at: datetime
    source_message_id: UUID | None = None
    importance_score: float = 0.0
    emotional_intensity: float = 0.0
    last_accessed_at: datetime | None = None
    access_count: int = 0
    is_archived: bool = False
