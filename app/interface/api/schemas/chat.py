from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, model_validator

class ChatRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_\-\:]+$", description="The unique identifier for the user (e.g. discord:12345 or web:user_id)")
    message: Optional[str] = Field(default="", max_length=4000, description="The message text from the user")
    images: Optional[List[str]] = Field(default_factory=list, description="Optional list of image URLs or Base64 Data URIs")
    is_ephemeral_reference: Optional[bool] = Field(default=False, description="True if images are from referenced community messages without permanent saving")
    source: Optional[str] = Field(default="web", max_length=64, description="The origin source of the request ('web' or 'discord')")
    username: Optional[str] = Field(default=None, max_length=64, description="Optional username of the sender")
    channel_name: Optional[str] = Field(default=None, max_length=64, description="Optional channel name (if discord)")
    guild_name: Optional[str] = Field(default=None, max_length=64, description="Optional guild name/server name (if discord)")

    @model_validator(mode="after")
    def validate_message_or_images(self) -> "ChatRequest":
        msg = (self.message or "").strip()
        has_imgs = bool(self.images and len(self.images) > 0)
        if not msg and not has_imgs:
            raise ValueError("Message cannot be empty when no images are attached.")
        if not msg and has_imgs:
            self.message = "Em hãy xem và phân tích bức ảnh này giúp Senpai nhé."
        else:
            self.message = msg
        return self

class ChatResponse(BaseModel):
    response: str = Field(..., description="The generated response from Chisa")
    user_id: str = Field(..., description="Echoes back the user_id for tracking")
    emotions: dict | None = Field(default=None, description="Current emotional state of Chisa")
    emotion_caption: Optional[str] = Field(default=None, description="Dynamic psychological summary caption of Chisa's emotion state")
    loop_thinking_activated: bool = Field(default=False, description="True if the Loop Thinking Agent was activated during this request")
    images_processed: Optional[List[Dict[str, Any]]] = Field(default_factory=list, description="Metadata of processed images")
    attached_images: Optional[List[str]] = Field(default_factory=list, description="List of retrieved image URLs attached in response")
