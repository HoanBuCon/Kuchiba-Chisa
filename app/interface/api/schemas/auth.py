"""Schemas for anonymous web authentication sessions."""

from pydantic import BaseModel, Field


class AnonymousSessionResponse(BaseModel):
    access_token: str = Field(description="Short-lived bearer token for this browser session")
    token_type: str = Field(default="Bearer")
    expires_in: int = Field(ge=1)
    subject_id: str = Field(description="Server-generated subject for the authenticated session")
