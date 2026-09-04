"""Public contract for server-approved attachment delivery manifests."""

from pydantic import BaseModel, ConfigDict, Field


class AttachmentManifestOut(BaseModel):
    """An opaque evidence identifier plus a server-issued delivery URL."""

    model_config = ConfigDict(extra="forbid")

    attachment_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    delivery_url: str = Field(min_length=1, max_length=2_048)
