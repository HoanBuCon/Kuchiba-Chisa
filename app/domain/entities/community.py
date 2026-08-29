from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from app.domain.entities.emotion import EmotionState
from app.domain.entities.user import UserStats
from app.domain.services.rag.base import RAGContext
from app.domain.interfaces.llm_provider import StructuredPrompt


@dataclass
class CommunityMessage:
    """Represents a single message in a multi-user community channel."""
    message_id: str
    speaker_id: str
    speaker_name: str
    content: str
    created_at: datetime = field(default_factory=datetime.now)
    reply_to_speaker: Optional[str] = None
    reply_to_content: Optional[str] = None
    is_bot: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "speaker_id": self.speaker_id,
            "speaker_name": self.speaker_name,
            "content": self.content,
            "created_at": self.created_at.isoformat(),
            "reply_to_speaker": self.reply_to_speaker,
            "reply_to_content": self.reply_to_content,
            "is_bot": self.is_bot,
        }


@dataclass
class CommunityChatContext:
    """Lifecycle context traversing the CommunityChatPipeline."""
    # Identification
    channel_id: str
    guild_id: Optional[str]
    channel_name: str
    current_speaker_id: str
    current_speaker_name: str
    user_message: str
    user_uuid: Optional[UUID] = None

    # Multi-speaker History
    recent_messages: List[CommunityMessage] = field(default_factory=list)
    formatted_transcript: str = ""

    # Current Speaker Domain State
    speaker_emotion: Optional[EmotionState] = None
    speaker_stats: Optional[UserStats] = None
    rag_context: Optional[RAGContext] = None

    # Prompt & Budgeting
    prompt: Optional[StructuredPrompt] = None
    budget_audit: Optional[Dict[str, Any]] = None

    # Generation & Extraction
    raw_llm_response: Optional[str] = None
    cleaned_response: Optional[str] = None
    extracted_sentiment: Optional[Dict[str, Any]] = None
    updated_speaker_emotions: Optional[Dict[str, Any]] = None

    # Observability
    execution_time_ms: float = 0.0
