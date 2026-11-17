"""Argon2id password hashing with bcrypt kept only to verify legacy hashes (IAM-011)."""

from __future__ import annotations

import bcrypt
from argon2 import PasswordHasher as Argon2Hasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.domain.interfaces.accounts import IPasswordHasher
from app.domain.models.account import PASSWORD_MAX_BYTES

_BCRYPT_PREFIXES = ("$2a$", "$2b$", "$2y$")


class PasswordHasher(IPasswordHasher):
    """New hashes use the argon2-cffi defaults (RFC 9106 low-memory profile)."""

    def __init__(self) -> None:
        self._argon2 = Argon2Hasher()

    def hash(self, password: str) -> str:
        secret = password.encode("utf-8")
        if len(secret) > PASSWORD_MAX_BYTES:
            raise ValueError("password exceeds the input limit")
        return self._argon2.hash(secret)

    def verify(self, password: str, password_hash: str) -> bool:
        secret = password.encode("utf-8")
        if len(secret) > PASSWORD_MAX_BYTES:
            return False
        if password_hash.startswith(_BCRYPT_PREFIXES):
            return self._verify_bcrypt(secret, password_hash)
        return self._verify_argon2(secret, password_hash)

    def needs_rehash(self, password_hash: str) -> bool:
        if password_hash.startswith(_BCRYPT_PREFIXES):
            return True
        try:
            return self._argon2.check_needs_rehash(password_hash)
        except InvalidHashError:
            return True

    def _verify_argon2(self, secret: bytes, password_hash: str) -> bool:
        try:
            return self._argon2.verify(password_hash, secret)
        except (VerificationError, InvalidHashError):
            return False

    @staticmethod
    def _verify_bcrypt(secret: bytes, password_hash: str) -> bool:
        try:
            return bcrypt.checkpw(secret, password_hash.encode("ascii"))
        except ValueError:
            return False
