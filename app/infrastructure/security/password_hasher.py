"""bcrypt password hashing adapter (pyca ``bcrypt``; no custom cryptography)."""

from __future__ import annotations

import bcrypt

from app.domain.interfaces.accounts import IPasswordHasher
from app.domain.models.account import PASSWORD_MAX_BYTES


class BcryptPasswordHasher(IPasswordHasher):
    def __init__(self, rounds: int = 12) -> None:
        if not 10 <= rounds <= 15:
            raise ValueError("bcrypt rounds must be between 10 and 15")
        self._rounds = rounds

    def hash(self, password: str) -> str:
        secret = password.encode("utf-8")
        if len(secret) > PASSWORD_MAX_BYTES:
            raise ValueError("password exceeds bcrypt input limit")
        return bcrypt.hashpw(secret, bcrypt.gensalt(rounds=self._rounds)).decode("ascii")

    def verify(self, password: str, password_hash: str) -> bool:
        secret = password.encode("utf-8")
        if len(secret) > PASSWORD_MAX_BYTES:
            return False
        try:
            return bcrypt.checkpw(secret, password_hash.encode("ascii"))
        except ValueError:
            return False

    def needs_rehash(self, password_hash: str) -> bool:
        try:
            cost = int(password_hash.split("$")[2])
        except (IndexError, ValueError):
            return True
        return cost < self._rounds
