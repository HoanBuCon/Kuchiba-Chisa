from typing import Optional
from pydantic import BaseModel, Field, field_validator

class ChatRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_\-\:]+$", description="The unique identifier for the user (e.g. discord:12345 or web:user_id)")
    message: str = Field(..., min_length=1, max_length=4000, description="The message text from the user")
    source: Optional[str] = Field(default="web", max_length=64, description="The origin source of the request ('web' or 'discord')")
    username: Optional[str] = Field(default=None, max_length=64, description="Optional username of the sender")
    channel_name: Optional[str] = Field(default=None, max_length=64, description="Optional channel name (if discord)")
    guild_name: Optional[str] = Field(default=None, max_length=64, description="Optional guild name/server name (if discord)")

    @field_validator("message")
    @classmethod
    def message_must_not_be_whitespace(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Message cannot be empty or just whitespace")
        return v.strip()

class ChatResponse(BaseModel):
    response: str = Field(..., description="The generated response from Chisa")
    user_id: str = Field(..., description="Echoes back the user_id for tracking")
    emotions: dict | None = Field(default=None, description="Current emotional state of Chisa")
    emotion_caption: Optional[str] = Field(default=None, description="Dynamic psychological summary caption of Chisa's emotion state")
    loop_thinking_activated: bool = Field(default=False, description="True if the Loop Thinking Agent was activated during this request")

