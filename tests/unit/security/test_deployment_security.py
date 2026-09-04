"""SEC-07 deployment-boundary regression tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from app.config.settings import Settings


def _production_settings(**overrides: str) -> Settings:
    values = {
        "APP_ENV": "production",
        "SECRET_KEY": "a" * 32,
        "DATABASE_URL": "postgresql+asyncpg://chisa:secret@postgres/chisa_db",
        "JWT_SECRET": "b" * 32,
        "DISCORD_WORKLOAD_JWT_SECRET": "c" * 32,
        "REDIS_PASSWORD": "redis-secret",
        "QDRANT_API_KEY": "qdrant-secret",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def _compose() -> dict[str, Any]:
    compose_path = Path(__file__).parents[3] / "docker-compose.yml"
    return yaml.safe_load(compose_path.read_text(encoding="utf-8"))


def test_production_settings_reject_missing_or_template_infrastructure_secrets() -> None:
    assert _production_settings().is_prod

    for overrides, message in (
        ({"REDIS_PASSWORD": ""}, "REDIS_PASSWORD is required"),
        ({"QDRANT_API_KEY": ""}, "QDRANT_API_KEY is required"),
        ({"JWT_SECRET": "replace_with_a_real_secret_value_32_chars"}, "production secrets"),
    ):
        with pytest.raises(ValidationError, match=message):
            _production_settings(**overrides)


def test_compose_keeps_data_services_internal_and_uses_runtime_secrets() -> None:
    compose = _compose()
    services = compose["services"]

    assert compose["networks"]["chisa_data"]["internal"] is True
    assert "ports" not in services["postgres"]
    assert "ports" not in services["redis"]
    assert "ports" not in services["qdrant"]
    assert services["app"]["ports"] == ["127.0.0.1:${APP_PORT:-8000}:8000"]
    assert "POSTGRES_PASSWORD" not in services["postgres"]["environment"]
    assert services["postgres"]["environment"]["POSTGRES_PASSWORD_FILE"] == (
        "/run/secrets/postgres_password"
    )
    assert services["redis"]["secrets"] == ["redis_password"]
    assert services["app"]["secrets"] == ["postgres_password", "redis_password"]
    assert services["discord"]["secrets"] == ["postgres_password"]
    assert services["qdrant"]["environment"]["QDRANT__SERVICE__API_KEY"].startswith(
        "${QDRANT_API_KEY:"
    )


def test_compose_redis_disables_default_user_and_enables_aof() -> None:
    command = " ".join(_compose()["services"]["redis"]["command"])

    assert "user default off" in command
    assert "--aclfile /run/redis/users.acl" in command
    assert "--appendonly yes" in command
    assert "--appendfsync everysec" in command
