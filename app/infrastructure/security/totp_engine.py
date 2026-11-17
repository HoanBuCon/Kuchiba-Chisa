"""RFC 6238 TOTP on top of pyotp, plus sealing of the stored secret (SEC-ADM-002)."""

from __future__ import annotations

import base64
import hashlib
import hmac
from datetime import datetime

import pyotp
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.domain.interfaces.admin_mfa import IMfaSecretVault, ITotpEngine
from app.domain.models.admin_mfa import TOTP_DIGITS, TOTP_PERIOD_SECONDS

_KEY_BYTES = 32


class PyOtpTotpEngine(ITotpEngine):
    def new_secret(self) -> str:
        return pyotp.random_base32()

    def provisioning_uri(self, secret: str, account_label: str, issuer: str) -> str:
        return self._totp(secret).provisioning_uri(name=account_label, issuer_name=issuer)

    def matching_step(self, secret: str, code: str, now: datetime, drift_steps: int) -> int | None:
        if len(code) != TOTP_DIGITS or not code.isascii() or not code.isdigit():
            return None
        totp = self._totp(secret)
        current = int(now.timestamp()) // TOTP_PERIOD_SECONDS
        for step in range(current - drift_steps, current + drift_steps + 1):
            if hmac.compare_digest(totp.at(step * TOTP_PERIOD_SECONDS), code):
                return step
        return None

    @staticmethod
    def _totp(secret: str) -> pyotp.TOTP:
        return pyotp.TOTP(secret, digits=TOTP_DIGITS, interval=TOTP_PERIOD_SECONDS)


class DerivedKeyMfaSecretVault(IMfaSecretVault):
    """Seals TOTP secrets and digests recovery codes with keys derived from the server secret."""

    def __init__(self, server_secret: str) -> None:
        self._fernet = Fernet(base64.urlsafe_b64encode(self._derive(server_secret, b"seal")))
        self._digest_key = self._derive(server_secret, b"digest")

    def seal(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode()).decode()

    def unseal(self, sealed: str) -> str:
        return self._fernet.decrypt(sealed.encode()).decode()

    def digest(self, code: str) -> str:
        return hmac.new(self._digest_key, code.encode(), hashlib.sha256).hexdigest()

    @staticmethod
    def _derive(server_secret: str, purpose: bytes) -> bytes:
        return HKDF(
            algorithm=hashes.SHA256(),
            length=_KEY_BYTES,
            salt=None,
            info=b"chisa-admin-mfa:" + purpose,
        ).derive(server_secret.encode())
