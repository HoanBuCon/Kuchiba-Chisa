from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class CommunityMessageIn(BaseModel):
    message_id: str = Field(default="", description="Unique Discord/Platform message ID")
    speaker_id: str = Field(..., description="ID of the user who sent the message")
    speaker_name: str = Field(..., description="Display name / Username of the speaker")
    content: str = Field(..., description="Text content of the message")
    reply_to_speaker: Optional[str] = Field(default=None, description="Username of user being replied to")
    reply_to_content: Optional[str] = Field(default=None, description="Snippet of message being replied to")
    is_bot: bool = Field(default=False, description="True if message is from a bot/assistant")
    created_at: Optional[str] = Field(default=None, description="ISO timestamp string")


class CommunityChatRequest(BaseModel):
    channel_id: str = Field(..., description="Discord Channel ID")
    guild_id: Optional[str] = Field(default=None, description="Discord Guild/Server ID")
    channel_name: str = Field(default="general", description="Name of the channel")
    guild_name: Optional[str] = Field(default=None, description="Name of the guild/server")
    user_id: str = Field(..., description="Current speaker Discord User ID")
    username: str = Field(..., description="Current speaker display name / username")
    message: str = Field(..., description="User message addressing Chisa")
    recent_messages: List[CommunityMessageIn] = Field(default_factory=list, description="Recent channel transcript")


class CommunityChatResponse(BaseModel):
    response: str = Field(..., description="Chisa's reply in the community channel")
    emotions: Dict[str, Any] = Field(default_factory=dict, description="Updated emotion state with current speaker")
    emotion_caption: Optional[str] = Field(default=None, description="Dynamic psychological summary caption")
    sentiment: Optional[Dict[str, Any]] = Field(default=None, description="Sentiment analysis of interaction")
    execution_time_ms: float = Field(default=0.0, description="Pipeline execution duration in milliseconds")
