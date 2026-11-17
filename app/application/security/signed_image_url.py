"""Short-lived HMAC signatures: only the server can hand out image links (SEC-RAG-002)."""

from __future__ import annotations

import hashlib
import hmac
import time
from collections.abc import Callable

# Separates this use of the shared secret from every other signature made with it.
DOMAIN_TAG = b"entity-image-url-v1"


class ImageUrlSigner:
    def __init__(
        self, secret: str, ttl_seconds: int, clock: Callable[[], float] = time.time
    ) -> None:
        self._key = hmac.new(secret.encode("utf-8"), DOMAIN_TAG, hashlib.sha256).digest()
        self._ttl = ttl_seconds
        self._clock = clock

    def sign(self, sha256: str, *, original: bool) -> tuple[int, str]:
        """The expiry (unix seconds) and the signature that covers it."""
        expires = int(self._clock()) + self._ttl
        return expires, self._signature(sha256, original, expires)

    def verify(self, sha256: str, *, original: bool, expires: int, signature: str) -> bool:
        if expires < self._clock():
            return False
        expected = self._signature(sha256, original, expires)
        return hmac.compare_digest(expected, signature)

    def _signature(self, sha256: str, original: bool, expires: int) -> str:
        message = f"{sha256}:{int(original)}:{expires}".encode()
        return hmac.new(self._key, message, hashlib.sha256).hexdigest()
