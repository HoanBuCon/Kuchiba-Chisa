"""Schemas for web authentication: anonymous sessions and registered accounts."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AnonymousSessionResponse(BaseModel):
    access_token: str = Field(description="Short-lived bearer token for this browser session")
    token_type: str = Field(default="Bearer")
    expires_in: int = Field(ge=1)
    subject_id: str = Field(description="Server-generated subject for the authenticated session")


class EmailPasswordRequest(BaseModel):
    """Credentials payload. Never logged; bounded before hashing."""

    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class AccountSummary(BaseModel):
    email: str | None
    email_verified: bool
    has_password: bool
    providers: list[Literal["google"]]


class AccountSessionResponse(BaseModel):
    access_token: str
    token_type: str = Field(default="Bearer")
    expires_in: int = Field(ge=1)
    subject_id: str = Field(description="Server-owned account identity used as principal subject")
    account: AccountSummary


class CurrentIdentityResponse(BaseModel):
    authenticated: bool
    authentication: Literal["anonymous", "account", "workload"]
    subject_id: str
    account: AccountSummary | None = None


class GoogleStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: Literal["login", "link"] = "login"


class GoogleStartResponse(BaseModel):
    authorization_url: str


class AuthCapabilitiesResponse(BaseModel):
    password: bool = True
    # False when e-mail delivery is not configured: sign-up, verification resend
    # and password reset are then unavailable (existing verified logins still work).
    password_registration: bool = False
    google: bool


class AcceptedResponse(BaseModel):
    """Uniform reply for e-mail-triggering requests (never reveals account existence)."""

    status: Literal["accepted"] = "accepted"


class EmailRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=254)


class AccountTokenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=16, max_length=256)


class ResetPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=16, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


class ChangePasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


class StatusResponse(BaseModel):
    status: str
