from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.application.security.input_limits import InputLimitPolicy
from app.config.settings import settings
from app.interface.api.schemas.attachments import AttachmentManifestOut


def _empty_strings() -> list[str]:
    return []


def _empty_message_list() -> list["CommunityMessageIn"]:
    return []


def _empty_image_metadata() -> list[dict[str, Any]]:
    return []


def _empty_attachment_manifests() -> list[AttachmentManifestOut]:
    return []


def _empty_citations() -> list[str]:
    return []


class CommunityMessageIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message_id: str = Field(
        default="",
        max_length=settings.COMMUNITY_MAX_IDENTIFIER_CHARS,
        description="Unique Discord/Platform message ID",
    )
    speaker_id: str = Field(
        ...,
        max_length=settings.COMMUNITY_MAX_IDENTIFIER_CHARS,
        description="ID of the user who sent the message",
    )
    speaker_name: str = Field(
        ...,
        max_length=settings.COMMUNITY_MAX_IDENTIFIER_CHARS,
        description="Display name / Username of the speaker",
    )
    content: str = Field(
        ...,
        max_length=settings.COMMUNITY_MAX_MESSAGE_CHARS,
        description="Text content of the message",
    )
    reply_to_speaker: str | None = Field(
        default=None,
        max_length=settings.COMMUNITY_MAX_IDENTIFIER_CHARS,
        description="Username of user being replied to",
    )
    reply_to_content: str | None = Field(
        default=None,
        max_length=settings.COMMUNITY_MAX_REPLY_CONTEXT_CHARS,
        description="Snippet of message being replied to",
    )
    is_bot: bool = Field(default=False, description="True if message is from a bot/assistant")
    created_at: str | None = Field(
        default=None,
        max_length=settings.COMMUNITY_MAX_TIMESTAMP_CHARS,
        description="ISO timestamp string",
    )


class CommunityChatRequest(BaseModel):
    """Community content carried by a verified Discord workload envelope.

    Actor, tenant, and channel claims are deliberately excluded: they are
    taken only from the verified workload credential at the route boundary.
    """

    model_config = ConfigDict(extra="forbid")

    message: str | None = Field(
        default="",
        max_length=settings.CHAT_MAX_MESSAGE_CHARS,
        description="User message addressing Chisa",
    )
    recent_messages: list[CommunityMessageIn] = Field(
        default_factory=_empty_message_list,
        max_length=settings.COMMUNITY_MAX_HISTORY_MESSAGES,
        description="Recent channel transcript",
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
    def validate_message_or_images(self) -> "CommunityChatRequest":
        InputLimitPolicy.validate_community_history(self.recent_messages)
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
    attached_images: list[AttachmentManifestOut] | None = Field(
        default_factory=_empty_attachment_manifests,
        description="Server-approved retrieved-image attachment manifests",
    )
    citations: list[str] = Field(
        default_factory=_empty_citations,
        description="Server-validated evidence IDs supporting the response",
    )
