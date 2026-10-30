"""Google OpenID Connect adapter: Authorization Code + PKCE, server-side code redemption.

The browser never handles tokens. Chisa's backend:

1. builds the authorization URL (``response_type=code``, S256 PKCE challenge,
   ``state`` and ``nonce``);
2. redeems the code at Google's token endpoint with its confidential client
   secret and the PKCE verifier;
3. verifies the returned ID token locally: RS256 signature against Google's JWKS
   (selected by ``kid``), issuer, audience (= our client ID), ``azp``, expiry,
   issued-at and the ``nonce`` bound to this browser transaction.

Only then is a ``VerifiedExternalIdentity`` (stable ``sub``) returned. E-mail and
profile data sent by a client are never trusted.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any
from urllib.parse import urlencode

import httpx
from jose import JWTError, jwk, jwt
from jose.utils import base64url_decode

from app.domain.interfaces.accounts import IExternalIdentityProvider
from app.domain.models.account import ExternalProvider, VerifiedExternalIdentity

GOOGLE_AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
GOOGLE_JWKS_URI = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_ISSUERS = frozenset({"https://accounts.google.com", "accounts.google.com"})
_CLOCK_SKEW_SECONDS = 60
_DEFAULT_JWKS_TTL_SECONDS = 3600


class ExternalIdentityVerificationError(Exception):
    """Code redemption or ID-token verification failed. Never carries token material."""


class GoogleOidcProvider(IExternalIdentityProvider):
    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        http_client: httpx.AsyncClient,
        timeout_seconds: float = 10.0,
        clock: Any = time.time,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri
        self._http = http_client
        self._timeout = timeout_seconds
        self._clock = clock
        self._jwks: dict[str, dict[str, Any]] = {}
        self._jwks_expires_at = 0.0
        self._jwks_lock = asyncio.Lock()

    @property
    def provider(self) -> ExternalProvider:
        return "google"

    def authorization_url(self, *, state: str, nonce: str, code_challenge: str) -> str:
        query = urlencode(
            {
                "client_id": self._client_id,
                "redirect_uri": self._redirect_uri,
                "response_type": "code",
                "scope": "openid email profile",
                "state": state,
                "nonce": nonce,
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
                "prompt": "select_account",
                "access_type": "online",
            }
        )
        return f"{GOOGLE_AUTHORIZATION_ENDPOINT}?{query}"

    async def exchange_code(
        self, *, code: str, code_verifier: str, nonce: str
    ) -> VerifiedExternalIdentity:
        try:
            response = await self._http.post(
                GOOGLE_TOKEN_ENDPOINT,
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
        try:
            id_token = response.json()["id_token"]
        except (ValueError, KeyError, TypeError) as error:
            raise ExternalIdentityVerificationError("token response has no id_token") from error
        if not isinstance(id_token, str):
            raise ExternalIdentityVerificationError("token response has no id_token")
        claims = await self.verify_id_token(id_token, expected_nonce=nonce)
        return VerifiedExternalIdentity(
            provider="google",
            subject=claims["sub"],
            email=claims.get("email") if isinstance(claims.get("email"), str) else None,
            email_verified=claims.get("email_verified") is True,
        )

    async def verify_id_token(self, id_token: str, *, expected_nonce: str) -> dict[str, Any]:
        try:
            header = jwt.get_unverified_header(id_token)
        except JWTError as error:
            raise ExternalIdentityVerificationError("malformed id_token") from error
        if header.get("alg") != "RS256" or not isinstance(header.get("kid"), str):
            raise ExternalIdentityVerificationError("unexpected id_token algorithm")
        key_data = await self._signing_key(header["kid"])
        if not _signature_is_valid(id_token, key_data):
            raise ExternalIdentityVerificationError("id_token signature is invalid")

        try:
            claims = jwt.get_unverified_claims(id_token)
        except JWTError as error:
            raise ExternalIdentityVerificationError("malformed id_token") from error

        now = self._clock()
        if claims.get("iss") not in GOOGLE_ISSUERS:
            raise ExternalIdentityVerificationError("id_token issuer is invalid")
        audience = claims.get("aud")
        audiences = audience if isinstance(audience, list) else [audience]
        if self._client_id not in audiences:
            raise ExternalIdentityVerificationError("id_token audience is invalid")
        if len(audiences) > 1 and claims.get("azp") != self._client_id:
            raise ExternalIdentityVerificationError("id_token authorized party is invalid")
        if "azp" in claims and claims.get("azp") != self._client_id:
            raise ExternalIdentityVerificationError("id_token authorized party is invalid")
        exp = claims.get("exp")
        iat = claims.get("iat")
        if not isinstance(exp, int | float) or exp + _CLOCK_SKEW_SECONDS < now:
            raise ExternalIdentityVerificationError("id_token is expired")
        if not isinstance(iat, int | float) or iat - _CLOCK_SKEW_SECONDS > now:
            raise ExternalIdentityVerificationError("id_token issued in the future")
        if not expected_nonce or claims.get("nonce") != expected_nonce:
            raise ExternalIdentityVerificationError("id_token nonce mismatch")
        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject or len(subject) > 255:
            raise ExternalIdentityVerificationError("id_token subject is invalid")
        return claims

    async def _signing_key(self, kid: str) -> dict[str, Any]:
        async with self._jwks_lock:
            if kid not in self._jwks or self._clock() >= self._jwks_expires_at:
                await self._refresh_jwks()
            key = self._jwks.get(kid)
        if key is None:
            raise ExternalIdentityVerificationError("id_token signing key is unknown")
        return key

    async def _refresh_jwks(self) -> None:
        try:
            response = await self._http.get(
                GOOGLE_JWKS_URI, timeout=self._timeout, follow_redirects=False
            )
            response.raise_for_status()
            keys = response.json()["keys"]
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as error:
            raise ExternalIdentityVerificationError("Google signing keys unavailable") from error
        self._jwks = {
            key["kid"]: key
            for key in keys
            if isinstance(key, dict) and key.get("kty") == "RSA" and isinstance(key.get("kid"), str)
        }
        self._jwks_expires_at = self._clock() + _jwks_ttl(response.headers.get("cache-control"))


def _signature_is_valid(token: str, key_data: dict[str, Any]) -> bool:
    try:
        signing_input, encoded_signature = token.rsplit(".", 1)
        public_key = jwk.construct(key_data, algorithm="RS256")
        signature = base64url_decode(encoded_signature.encode("ascii"))
        return bool(public_key.verify(signing_input.encode("ascii"), signature))
    except (JWTError, ValueError, TypeError, UnicodeError):
        return False


def _jwks_ttl(cache_control: str | None) -> float:
    if cache_control:
        for directive in cache_control.split(","):
            name, _, value = directive.strip().partition("=")
            if name.lower() == "max-age" and value.isdigit():
                return float(min(int(value), 24 * 3600))
    return float(_DEFAULT_JWKS_TTL_SECONDS)
