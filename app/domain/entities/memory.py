import enum
from dataclasses import dataclass
from typing import Optional, Dict
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field
from typing import Optional
from uuid import UUID
from datetime import datetime

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
    conversation_id: Optional[str] = None
    memory_type: str
    memory_tier: MemoryTier = MemoryTier.CASUAL
    importance_score: float = Field(ge=0.0, le=1.0)
    emotion: Dict[str, float] = Field(default_factory=dict)
    created_at: int
    text_content: str
    
    model_config = ConfigDict(extra="allow")

@dataclass
class MemoryMetadata:
    id: UUID
    user_id: UUID
    memory_type: MemoryType
    created_at: datetime
    updated_at: datetime
    source_message_id: Optional[UUID] = None
    importance_score: float = 0.0
    emotional_intensity: float = 0.0
    last_accessed_at: Optional[datetime] = None
    access_count: int = 0
    is_archived: bool = False
