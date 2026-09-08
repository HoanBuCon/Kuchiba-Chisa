from dataclasses import dataclass
from typing import Optional
from uuid import UUID
from datetime import datetime

@dataclass
class Conversation:
    id: UUID
    user_id: UUID
    started_at: datetime
    ended_at: Optional[datetime] = None
    summary: Optional[str] = None
    is_archived: bool = False


@dataclass(frozen=True)
class ConversationSummary:
    conversation_id: UUID
    user_id: UUID
    text: str | None
    revision: int
    source_revision: int
