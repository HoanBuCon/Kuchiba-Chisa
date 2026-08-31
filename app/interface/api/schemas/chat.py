from typing import Any

from pydantic import BaseModel, Field, model_validator


def _empty_strings() -> list[str]:
    return []


def _empty_image_metadata() -> list[dict[str, Any]]:
    return []


class ChatRequest(BaseModel):
    user_id: str = Field(
        ...,
        min_length=1,
        max_length=128,
        pattern=r"^[a-zA-Z0-9_\-\:]+$",
        description="The unique identifier for the user (e.g. discord:12345 or web:user_id)",
    )
    message: str | None = Field(
        default="", max_length=4000, description="The message text from the user"
    )
    images: list[str] | None = Field(
        default_factory=_empty_strings,
        description="Optional list of image URLs or Base64 Data URIs",
    )
    is_ephemeral_reference: bool | None = Field(
        default=False,
        description=(
            "True if images are from referenced community messages without permanent saving"
        ),
    )
    source: str | None = Field(
        default="web",
        max_length=64,
        description="The origin source of the request ('web' or 'discord')",
    )
    username: str | None = Field(
        default=None, max_length=64, description="Optional username of the sender"
    )
    channel_name: str | None = Field(
        default=None, max_length=64, description="Optional channel name (if discord)"
    )
    guild_name: str | None = Field(
        default=None, max_length=64, description="Optional guild name/server name (if discord)"
    )

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
