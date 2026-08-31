from typing import Any

from pydantic import BaseModel, Field, model_validator


def _empty_strings() -> list[str]:
    return []


def _empty_message_list() -> list["CommunityMessageIn"]:
    return []


def _empty_image_metadata() -> list[dict[str, Any]]:
    return []


class CommunityMessageIn(BaseModel):
    message_id: str = Field(default="", description="Unique Discord/Platform message ID")
    speaker_id: str = Field(..., description="ID of the user who sent the message")
    speaker_name: str = Field(..., description="Display name / Username of the speaker")
    content: str = Field(..., description="Text content of the message")
    reply_to_speaker: str | None = Field(
        default=None, description="Username of user being replied to"
    )
    reply_to_content: str | None = Field(
        default=None, description="Snippet of message being replied to"
    )
    is_bot: bool = Field(default=False, description="True if message is from a bot/assistant")
    created_at: str | None = Field(default=None, description="ISO timestamp string")


class CommunityChatRequest(BaseModel):
    channel_id: str = Field(..., description="Discord Channel ID")
    guild_id: str | None = Field(default=None, description="Discord Guild/Server ID")
    channel_name: str = Field(default="general", description="Name of the channel")
    guild_name: str | None = Field(default=None, description="Name of the guild/server")
    user_id: str = Field(..., description="Current speaker Discord User ID")
    username: str = Field(..., description="Current speaker display name / username")
    message: str | None = Field(default="", description="User message addressing Chisa")
    recent_messages: list[CommunityMessageIn] = Field(
        default_factory=_empty_message_list, description="Recent channel transcript"
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

    @model_validator(mode="after")
    def validate_message_or_images(self) -> "CommunityChatRequest":
        msg = (self.message or "").strip()
        has_imgs = bool(self.images and len(self.images) > 0)
        if not msg and not has_imgs:
            raise ValueError("Message cannot be empty when no images are attached.")
        if not msg and has_imgs:
            self.message = "Em hãy xem và phân tích bức ảnh này giúp Senpai nhé."
        else:
            self.message = msg
        return self


class CommunityChatResponse(BaseModel):
    response: str = Field(..., description="Chisa's reply in the community channel")
    emotions: dict[str, Any] = Field(
        default_factory=dict, description="Updated emotion state with current speaker"
    )
    emotion_caption: str | None = Field(
        default=None, description="Dynamic psychological summary caption"
    )
    sentiment: dict[str, Any] | None = Field(
        default=None, description="Sentiment analysis of interaction"
    )
    execution_time_ms: float = Field(
        default=0.0, description="Pipeline execution duration in milliseconds"
    )
    images_processed: list[dict[str, Any]] | None = Field(
        default_factory=_empty_image_metadata, description="Metadata of processed images"
    )
    attached_images: list[str] | None = Field(
        default_factory=_empty_strings,
        description="List of retrieved image URLs attached in response",
    )
