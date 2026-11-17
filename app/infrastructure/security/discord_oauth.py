"""Discord OAuth2 adapter: Authorization Code + PKCE, server-side code redemption.

Discord is plain OAuth2, not OIDC, so there is no ID token to verify. The identity is
read from ``/users/@me`` with the access token that Chisa's backend just obtained
using its client secret and the PKCE verifier; the browser never sees a token. The
CSRF ``state`` is checked by the caller against the browser-bound transaction.

The Discord account ID (snowflake) is the stable subject. The e-mail is only
reported as verified when Discord says ``verified is true``.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

import httpx

from app.domain.interfaces.accounts import IExternalIdentityProvider
from app.domain.models.account import ExternalProvider, VerifiedExternalIdentity
from app.infrastructure.security.google_oidc import ExternalIdentityVerificationError

DISCORD_AUTHORIZATION_ENDPOINT = "https://discord.com/oauth2/authorize"
DISCORD_TOKEN_ENDPOINT = "https://discord.com/api/oauth2/token"
DISCORD_USER_ENDPOINT = "https://discord.com/api/users/@me"
DISCORD_SCOPES = ("identify", "email")
_MAX_SUBJECT_LENGTH = 32


class DiscordOAuthProvider(IExternalIdentityProvider):
    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        http_client: httpx.AsyncClient,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri
        self._http = http_client
        self._timeout = timeout_seconds

    @property
    def provider(self) -> ExternalProvider:
        return "discord"

    def authorization_url(self, *, state: str, nonce: str, code_challenge: str) -> str:
        # ``nonce`` only binds OIDC ID tokens; plain OAuth2 relies on state and PKCE.
        query = urlencode(
            {
                "client_id": self._client_id,
                "redirect_uri": self._redirect_uri,
                "response_type": "code",
                "scope": " ".join(DISCORD_SCOPES),
                "state": state,
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
                "prompt": "consent",
            }
        )
        return f"{DISCORD_AUTHORIZATION_ENDPOINT}?{query}"

    async def exchange_code(
        self, *, code: str, code_verifier: str, nonce: str
    ) -> VerifiedExternalIdentity:
        access_token = await self._redeem_code(code, code_verifier)
        profile = await self._fetch_profile(access_token)
        subject = profile.get("id")
        if not isinstance(subject, str) or not subject.isdigit():
            raise ExternalIdentityVerificationError("discord user id is invalid")
        if len(subject) > _MAX_SUBJECT_LENGTH:
            raise ExternalIdentityVerificationError("discord user id is invalid")
        email = profile.get("email")
        return VerifiedExternalIdentity(
            provider="discord",
            subject=subject,
            email=email if isinstance(email, str) and email else None,
            email_verified=profile.get("verified") is True,
        )

    async def _redeem_code(self, code: str, code_verifier: str) -> str:
        try:
            response = await self._http.post(
                DISCORD_TOKEN_ENDPOINT,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "code_verifier": code_verifier,
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "redirect_uri": self._redirect_uri,
                },
                headers={"Accept": "application/json"},
                timeout=self._timeout,
                follow_redirects=False,
            )
        except httpx.HTTPError as error:
            raise ExternalIdentityVerificationError("token endpoint unavailable") from error
        if response.status_code != 200:
            raise ExternalIdentityVerificationError("authorization code was rejected")
        body = _json_object(response)
        token = body.get("access_token")
        scopes = str(body.get("scope", "")).split()
        if not isinstance(token, str) or not token or "identify" not in scopes:
            raise ExternalIdentityVerificationError("token response is incomplete")
        return token

    async def _fetch_profile(self, access_token: str) -> dict[str, Any]:
        try:
            response = await self._http.get(
                DISCORD_USER_ENDPOINT,
                headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
                timeout=self._timeout,
                follow_redirects=False,
            )
        except httpx.HTTPError as error:
            raise ExternalIdentityVerificationError("user endpoint unavailable") from error
        if response.status_code != 200:
            raise ExternalIdentityVerificationError("user profile was rejected")
        return _json_object(response)


def _json_object(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError as error:
        raise ExternalIdentityVerificationError("response is not JSON") from error
    if not isinstance(body, dict):
        raise ExternalIdentityVerificationError("response is not an object")
    return body
