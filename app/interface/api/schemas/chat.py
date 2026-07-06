from typing import Optional
from pydantic import BaseModel, Field

class ChatRequest(BaseModel):
    user_id: str = Field(..., description="The unique identifier for the user (e.g. discord:12345 or web:user_id)")
    message: str = Field(..., description="The message text from the user")
    pipeline: Optional[str] = Field(default=None, description="Optional override for the chat pipeline to use ('legacy' or 'production')")
    source: Optional[str] = Field(default="web", description="The origin source of the request ('web' or 'discord')")
    username: Optional[str] = Field(default=None, description="Optional username of the sender")
    channel_name: Optional[str] = Field(default=None, description="Optional channel name (if discord)")
    guild_name: Optional[str] = Field(default=None, description="Optional guild name/server name (if discord)")

class ChatResponse(BaseModel):
    response: str = Field(..., description="The generated response from Chisa")
    user_id: str = Field(..., description="Echoes back the user_id for tracking")
    emotions: dict | None = Field(default=None, description="Current emotional state of Chisa")
    loop_thinking_activated: bool = Field(default=False, description="True if the Loop Thinking Agent was activated during this request")

