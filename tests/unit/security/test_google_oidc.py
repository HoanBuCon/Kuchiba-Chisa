"""Google OIDC verification with a mocked provider (no network, no real Google keys)."""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from app.application.security.oauth_flow import new_oauth_transaction
from app.infrastructure.security.google_oidc import (
    GOOGLE_JWKS_URI,
    GOOGLE_TOKEN_ENDPOINT,
    ExternalIdentityVerificationError,
    GoogleOidcProvider,
)

CLIENT_ID = "chisa-test.apps.googleusercontent.com"
REDIRECT_URI = "https://chisa.example.test/api/v1/auth/google/callback"
NONCE = "expected-nonce"


def _rsa_pem() -> bytes:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


SIGNING_KEY = _rsa_pem()
OTHER_KEY = _rsa_pem()


def _public_jwk(pem: bytes, kid: str) -> dict[str, Any]:
    private_key = serialization.load_pem_private_key(pem, password=None)
    data = RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    return {**data, "kid": kid, "use": "sig", "alg": "RS256"}


def _id_token(overrides: dict[str, Any] | None = None, *, key: bytes = SIGNING_KEY, kid="k1"):
    now = int(time.time())
    claims = {
        "iss": "https://accounts.google.com",
        "aud": CLIENT_ID,
        "azp": CLIENT_ID,
        "sub": "110169484474386276334",
        "email": "senpai@gmail.com",
        "email_verified": True,
        "iat": now,
        "exp": now + 3600,
        "nonce": NONCE,
        "at_hash": "ignored-by-design",
    }
    claims.update(overrides or {})
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": kid})


class FakeGoogle:
    def __init__(self, id_token: str, *, token_status: int = 200) -> None:
        self.id_token = id_token
        self.token_status = token_status
        self.token_requests: list[dict[str, list[str]]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if str(request.url) == GOOGLE_JWKS_URI:
            return httpx.Response(
                200,
                json={"keys": [_public_jwk(SIGNING_KEY, "k1")]},
                headers={"cache-control": "public, max-age=19000"},
            )
        if str(request.url) == GOOGLE_TOKEN_ENDPOINT:
            self.token_requests.append(parse_qs(request.content.decode()))
            if self.token_status != 200:
                return httpx.Response(self.token_status, json={"error": "invalid_grant"})
            return httpx.Response(200, json={"id_token": self.id_token, "access_token": "x"})
        return httpx.Response(404)


def provider_for(fake: FakeGoogle) -> GoogleOidcProvider:
    return GoogleOidcProvider(
        client_id=CLIENT_ID,
        client_secret="test-client-secret",
        redirect_uri=REDIRECT_URI,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(fake)),
    )


def test_authorization_url_uses_code_flow_with_pkce_state_and_nonce() -> None:
    transaction = new_oauth_transaction()
    url = provider_for(FakeGoogle("")).authorization_url(
        state=transaction.state, nonce=transaction.nonce, code_challenge=transaction.code_challenge
    )
    query = parse_qs(urlsplit(url).query)

    assert urlsplit(url).netloc == "accounts.google.com"
    assert query["response_type"] == ["code"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["code_challenge"] == [transaction.code_challenge]
    assert query["code_challenge"] != [transaction.code_verifier]
    assert query["state"] == [transaction.state]
    assert query["nonce"] == [transaction.nonce]
    assert query["client_id"] == [CLIENT_ID]
    assert query["redirect_uri"] == [REDIRECT_URI]
    assert "openid" in query["scope"][0]


@pytest.mark.asyncio
async def test_valid_code_returns_verified_stable_subject() -> None:
    fake = FakeGoogle(_id_token())
    identity = await provider_for(fake).exchange_code(
        code="auth-code", code_verifier="verifier-value", nonce=NONCE
    )

    assert identity.provider == "google"
    assert identity.subject == "110169484474386276334"
    assert identity.email == "senpai@gmail.com"
    assert identity.email_verified is True
    sent = fake.token_requests[0]
    assert sent["code_verifier"] == ["verifier-value"]
    assert sent["grant_type"] == ["authorization_code"]
    assert sent["redirect_uri"] == [REDIRECT_URI]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "overrides",
    (
        {"iss": "https://evil.example.com"},
        {"aud": "someone-else.apps.googleusercontent.com"},
        {"aud": [CLIENT_ID, "other"], "azp": "other"},
        {"azp": "other-client"},
        {"exp": int(time.time()) - 3600},
        {"iat": int(time.time()) + 3600},
        {"nonce": "replayed-nonce"},
        {"sub": ""},
    ),
)
async def test_invalid_id_token_claims_are_rejected(overrides: dict[str, Any]) -> None:
    with pytest.raises(ExternalIdentityVerificationError):
        await provider_for(FakeGoogle(_id_token(overrides))).exchange_code(
            code="c", code_verifier="v", nonce=NONCE
        )


@pytest.mark.asyncio
async def test_token_signed_by_unknown_key_is_rejected() -> None:
    forged = _id_token(key=OTHER_KEY)  # claims kid k1 but signed by another key
    with pytest.raises(ExternalIdentityVerificationError, match="signature"):
        await provider_for(FakeGoogle(forged)).exchange_code(
            code="c", code_verifier="v", nonce=NONCE
        )


@pytest.mark.asyncio
async def test_unknown_kid_and_non_rs256_tokens_are_rejected() -> None:
    with pytest.raises(ExternalIdentityVerificationError):
        await provider_for(FakeGoogle(_id_token(kid="rotated-away"))).exchange_code(
            code="c", code_verifier="v", nonce=NONCE
        )
    hs256 = jwt.encode({"sub": "x", "aud": CLIENT_ID}, "shared", algorithm="HS256")
    with pytest.raises(ExternalIdentityVerificationError, match="algorithm"):
        await provider_for(FakeGoogle(hs256)).exchange_code(
            code="c", code_verifier="v", nonce=NONCE
        )


@pytest.mark.asyncio
async def test_tampered_payload_fails_signature_check() -> None:
    token = _id_token()
    header, payload, signature = token.split(".")
    forged_payload = jwt.encode({"sub": "attacker"}, "k", algorithm="HS256").split(".")[1]
    with pytest.raises(ExternalIdentityVerificationError):
        await provider_for(FakeGoogle(f"{header}.{forged_payload}.{signature}")).exchange_code(
            code="c", code_verifier="v", nonce=NONCE
        )


@pytest.mark.asyncio
async def test_rejected_authorization_code_does_not_leak_provider_body() -> None:
    with pytest.raises(ExternalIdentityVerificationError) as error:
        await provider_for(FakeGoogle("", token_status=400)).exchange_code(
            code="c", code_verifier="v", nonce=NONCE
        )
    assert "invalid_grant" not in str(error.value)


@pytest.mark.asyncio
async def test_unverified_email_flag_is_reported_not_trusted() -> None:
    identity = await provider_for(FakeGoogle(_id_token({"email_verified": False}))).exchange_code(
        code="c", code_verifier="v", nonce=NONCE
    )
    assert identity.email_verified is False
