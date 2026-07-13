import enum
from dataclasses import dataclass
from typing import Optional
from uuid import UUID
from datetime import datetime

class MessageRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"

@dataclass
class Message:
    id: UUID
    conversation_id: UUID
    user_id: UUID
    role: MessageRole
    content: str
    created_at: datetime
    updated_at: datetime
    token_count: Optional[int] = None
    is_success: bool = True
