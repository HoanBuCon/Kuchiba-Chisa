"""IAM-011: Argon2id for new hashes, bcrypt kept only to verify and upgrade legacy ones."""

from __future__ import annotations

import bcrypt
import pytest

from app.infrastructure.security.password_hasher import PasswordHasher

PASSWORD = "correct horse battery"
WRONG_PASSWORD = "incorrect horse battery"


def _legacy_bcrypt_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=4)).decode("ascii")


@pytest.fixture(scope="module")
def hasher() -> PasswordHasher:
    return PasswordHasher()


def test_new_hash_is_argon2id(hasher: PasswordHasher) -> None:
    assert hasher.hash(PASSWORD).startswith("$argon2id$")


def test_argon2id_hash_verifies_and_rejects_wrong_password(hasher: PasswordHasher) -> None:
    password_hash = hasher.hash(PASSWORD)

    assert hasher.verify(PASSWORD, password_hash)
    assert not hasher.verify(WRONG_PASSWORD, password_hash)


def test_legacy_bcrypt_hash_verifies_and_rejects_wrong_password(hasher: PasswordHasher) -> None:
    legacy_hash = _legacy_bcrypt_hash(PASSWORD)

    assert hasher.verify(PASSWORD, legacy_hash)
    assert not hasher.verify(WRONG_PASSWORD, legacy_hash)


def test_legacy_bcrypt_hash_needs_rehash(hasher: PasswordHasher) -> None:
    assert hasher.needs_rehash(_legacy_bcrypt_hash(PASSWORD))


def test_current_argon2id_hash_does_not_need_rehash(hasher: PasswordHasher) -> None:
    assert not hasher.needs_rehash(hasher.hash(PASSWORD))


def test_argon2id_hash_with_weaker_parameters_needs_rehash(hasher: PasswordHasher) -> None:
    from argon2 import PasswordHasher as Argon2

    weak_hash = Argon2(time_cost=1, memory_cost=8, parallelism=1).hash(PASSWORD)

    assert hasher.needs_rehash(weak_hash)


@pytest.mark.parametrize("garbage", ["", "not-a-hash", "$2b$12$short", "$argon2id$broken"])
def test_malformed_hash_is_rejected_not_raised(hasher: PasswordHasher, garbage: str) -> None:
    assert not hasher.verify(PASSWORD, garbage)


def test_oversized_password_is_rejected(hasher: PasswordHasher) -> None:
    with pytest.raises(ValueError):
        hasher.hash("a" * 73)
    assert not hasher.verify("a" * 73, hasher.hash(PASSWORD))
