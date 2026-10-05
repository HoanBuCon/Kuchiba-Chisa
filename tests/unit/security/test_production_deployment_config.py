"""B-4 / production configuration regression: Compose, Caddy and settings."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from app.config.settings import Settings

ROOT = Path(__file__).resolve().parents[3]


def _compose() -> dict[str, Any]:
    return yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))


def _mb(value: str) -> int:
    value = value.strip().upper()
    if value.endswith("G"):
        return int(float(value[:-1]) * 1024)
    return int(value.rstrip("MB"))


def _production(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
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


def test_production_settings_reject_unsafe_account_configuration() -> None:
    with pytest.raises(ValidationError, match="must differ from JWT_SECRET"):
        _production(DISCORD_WORKLOAD_JWT_SECRET="b" * 32)
    with pytest.raises(ValidationError, match="AUTH_COOKIE_SECURE"):
        _production(AUTH_COOKIE_SECURE=False)
    google = {
        "GOOGLE_OAUTH_CLIENT_ID": "id.apps.googleusercontent.com",
        "GOOGLE_OAUTH_CLIENT_SECRET": "real-looking-secret-value",
        "GOOGLE_OAUTH_REDIRECT_URI": "http://chisa.example.com/api/v1/auth/google/callback",
        "PUBLIC_APP_URL": "https://chisa.example.com",
    }
    with pytest.raises(ValidationError, match="https"):
        _production(**google)
    with pytest.raises(ValidationError, match="template values"):
        _production(
            **{
                **google,
                "GOOGLE_OAUTH_REDIRECT_URI": "https://chisa.example.com/api/v1/auth/google/callback",
                "GOOGLE_OAUTH_CLIENT_SECRET": "replace_with_google_client_secret",
            }
        )
    ok = _production(
        **{**google, "GOOGLE_OAUTH_REDIRECT_URI": "https://chisa.example.com/api/v1/auth/google/callback"}
    )
    assert ok.google_oauth_enabled


def test_compose_resources_fit_a_4_cpu_8_gb_vps() -> None:
    services = _compose()["services"]
    limits = {
        name: service["deploy"]["resources"]["limits"]
        for name, service in services.items()
        if "deploy" in service and name != "migrate"
    }
    total_memory = sum(_mb(limit["memory"]) for limit in limits.values())
    assert total_memory <= 6600, total_memory  # leaves ≥1.4 GB for OS/page cache
    assert _mb(limits["worker"]["memory"]) >= 1100
    redis_command = " ".join(services["redis"]["command"])
    assert "--maxmemory 384mb" in redis_command
    assert _mb(limits["redis"]["memory"]) > 384


def test_compose_persists_uploads_and_model_cache_and_rotates_logs() -> None:
    compose = _compose()
    services = compose["services"]
    assert "uploads_data:/app/app/static/uploads" in services["app"]["volumes"]
    assert "model_cache:/app/.cache" in services["app"]["volumes"]
    assert "model_cache:/app/.cache" in services["worker"]["volumes"]
    for name in ("postgres", "redis", "qdrant", "app", "worker", "discord", "web"):
        logging_config = services[name]["logging"]
        assert logging_config["driver"] == "json-file", name
        assert logging_config["options"]["max-size"] == "10m", name
        assert services[name]["restart"] == "unless-stopped", name
    assert services["app"]["environment"]["APP_LOG_FILE"] == ""
    assert "--no-access-log" in " ".join(services["app"]["command"])


def test_redis_acl_file_is_written_with_real_newlines() -> None:
    # A doubled backslash made printf emit a literal "\n", producing a one-line ACL
    # file that Redis rejects at startup (found in the compose rehearsal).
    redis_command = " ".join(_compose()["services"]["redis"]["command"])
    assert "printf 'user default off\\nuser chisa on >%s ~* +@all\\n'" in redis_command
    assert "\\\\n" not in redis_command


def test_images_never_include_user_uploads_or_env_files() -> None:
    ignored = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    for entry in ("app/static/uploads", ".env", "secrets"):
        assert entry in ignored, entry


def _production_template() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in (ROOT / ".env.production.example").read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    return values


def test_production_env_template_fails_closed_until_filled() -> None:
    template = _production_template()
    assert template["APP_ENV"] == "production"
    assert template["RERANKER_PROVIDER"] == "jina"
    assert template["TRUSTED_PROXY_CIDRS"] == "172.28.0.10/32"
    assert template["GOOGLE_OAUTH_CLIENT_SECRET"] == ""
    filled_template = {
        key: value for key, value in template.items() if key in Settings.model_fields
    }
    with pytest.raises(ValidationError, match="template values"):
        Settings(_env_file=None, **{**filled_template, "REDIS_PASSWORD": "redis-secret"})
    filled = {
        **filled_template,
        "REDIS_PASSWORD": "redis-secret",
        "SECRET_KEY": "s" * 48,
        "JWT_SECRET": "j" * 48,
        "DISCORD_WORKLOAD_JWT_SECRET": "d" * 48,
        "QDRANT_API_KEY": "q" * 32,
        "SMTP_USERNAME": "chisa-mailer",
        "SMTP_PASSWORD": "m" * 32,
    }
    settings = Settings(_env_file=None, **filled)
    assert settings.is_prod and settings.AUTH_COOKIE_SECURE and not settings.google_oauth_enabled
    assert settings.CHAT_QUOTA_ENABLED and settings.email_delivery_enabled
    assert "DISCORD_ALLOWED_CHANNEL_IDS" not in template  # no allowlist in the beta


def test_ops_modules_do_not_load_full_application_settings() -> None:
    # `docker compose exec/run` does not inherit the secrets exported by the service
    # command, so production Settings validation would refuse to load in these tools.
    for module in ("qdrant_snapshot.py", "warm_embedding_cache.py"):
        source = (ROOT / "app" / "ops" / module).read_text(encoding="utf-8")
        assert "app.config.settings" not in source, module
        assert "fastembed_adapter" not in source, module


def test_https_edge_is_the_only_public_entry_point() -> None:
    compose = _compose()
    services = compose["services"]
    web = services["web"]
    assert web["ports"] == ["80:80", "443:443", "443:443/udp"]
    assert "./deploy/caddy/Caddyfile:/etc/caddy/Caddyfile:ro" in web["volumes"]
    caddy_ip = web["networks"]["chisa_edge"]["ipv4_address"]
    assert services["app"]["environment"]["TRUSTED_PROXY_CIDRS"].endswith(f"{caddy_ip}/32}}")
    for name, service in services.items():
        if name not in {"web", "app"}:
            assert "ports" not in service, name
    assert services["migrate"]["profiles"] == ["ops"]


def test_caddyfile_blocks_internal_surfaces_and_supports_sse() -> None:
    caddyfile = (ROOT / "deploy" / "caddy" / "Caddyfile").read_text(encoding="utf-8")
    for path in ("/docs", "/openapi.json", "/static/*"):
        assert path in caddyfile
    assert "flush_interval -1" in caddyfile
    assert "Strict-Transport-Security" in caddyfile
    assert "X-Content-Type-Options" in caddyfile
    assert "frame-ancestors 'none'" in caddyfile
    assert "max_size 60MB" in caddyfile
    assert "reverse_proxy app:8000" in caddyfile


def test_caddyfile_routes_only_inside_handle_blocks() -> None:
    # Caddy orders site-level `respond`/`reverse_proxy` after the `handle` group,
    # whose catch-all SPA block always matches, so they would never execute
    # (the visualizer block and /health proxy were bypassed this way).
    caddyfile = (ROOT / "deploy" / "caddy" / "Caddyfile").read_text(encoding="utf-8")
    site_level = [
        line.strip()
        for line in caddyfile.splitlines()
        if line.startswith("\t") and not line.startswith("\t\t")
    ]
    assert not [line for line in site_level if line.startswith(("respond", "reverse_proxy"))]
    assert "handle @blocked {" in caddyfile
    assert "handle @health {" in caddyfile


def test_runbook_builds_the_profiled_migrate_image() -> None:
    # Plain `docker compose build` skips profiled services, so an update would run
    # the *previous* migrate image (found in the rehearsal).
    runbook = (ROOT / "docs" / "DEPLOYMENT_RUNBOOK.md").read_text(encoding="utf-8")
    assert "docker compose --profile ops build" in runbook
    assert "docker compose build" not in runbook.splitlines()
