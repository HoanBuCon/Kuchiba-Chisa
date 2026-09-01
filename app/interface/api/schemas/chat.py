from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.application.security.input_limits import InputLimitPolicy
from app.config.settings import settings


def _empty_strings() -> list[str]:
    return []


def _empty_image_metadata() -> list[dict[str, Any]]:
    return []


class ChatRequest(BaseModel):
    """Untrusted chat content only; identity comes from ``PrincipalContext``."""

    model_config = ConfigDict(extra="forbid")

    message: str | None = Field(
        default="",
        max_length=settings.CHAT_MAX_MESSAGE_CHARS,
        description="The message text from the user",
    )
    images: list[str] | None = Field(
        default_factory=_empty_strings,
        max_length=settings.VISION_MAX_IMAGES,
        description="Optional list of image URLs or Base64 Data URIs",
    )
    is_ephemeral_reference: bool | None = Field(
        default=False,
        description=(
            "True if images are from referenced community messages without permanent saving"
        ),
    )
    @model_validator(mode="after")
    def validate_message_or_images(self) -> "ChatRequest":
        InputLimitPolicy.validate_images(self.images)
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
    emotion_caption: str | None = Field(
        default=None, description="Dynamic psychological summary caption of Chisa's emotion state"
    )
    loop_thinking_activated: bool = Field(
        default=False,
        description="True if the Loop Thinking Agent was activated during this request",
    )
    images_processed: list[dict[str, Any]] | None = Field(
        default_factory=_empty_image_metadata, description="Metadata of processed images"
    )
    attached_images: list[str] | None = Field(
        default_factory=_empty_strings,
        description="List of retrieved image URLs attached in response",
    )
