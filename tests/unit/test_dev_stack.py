"""`chisa dev` orchestrator: development-only safety, secret hygiene and contracts."""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest
import yaml

from app.config.settings import settings
from app.infrastructure.security.jwt_authenticator import jwt_authenticator
from scripts import dev_bootstrap_qdrant, dev_stack

ROOT = Path(__file__).resolve().parents[2]
SECRET = "s" * 40


def good_env(**overrides: str) -> dict[str, str]:
    env = {
        "APP_ENV": "development",
        "DATABASE_URL": "postgresql+asyncpg://chisa:pw-for-dev-1234@localhost:5432/chisa_db",
        "REDIS_URL": "redis://localhost:6379/0",
        "QDRANT_URL": "http://localhost:6333",
        "JWT_SECRET": "j" * 40,
        "SECRET_KEY": "k" * 40,
        "DISCORD_WORKLOAD_JWT_SECRET": "d" * 40,
        "LLM_PROVIDER": "deepseek",
        "LLM_ENABLED_PROVIDERS": "deepseek",
        "DEEPSEEK_API_KEY": "sk-dev-key-123456",
        "RERANKER_PROVIDER": "disabled",
    }
    env.update(overrides)
    return env


def problems(**overrides: str) -> list[str]:
    return dev_stack.validate_environment(good_env(**overrides))


# ── Validation ──────────────────────────────────────────────────────────


def test_a_complete_development_environment_is_accepted() -> None:
    assert problems() == []


@pytest.mark.parametrize("value", ("production", "test", ""))
def test_anything_but_development_is_refused(value: str) -> None:
    assert any("APP_ENV" in p for p in problems(APP_ENV=value))


@pytest.mark.parametrize(
    ("key", "url"),
    (
        ("DATABASE_URL", "postgresql+asyncpg://chisa:pw-for-dev-1234@db.prod.example.com/chisa_db"),
        ("REDIS_URL", "redis://cache.example.com:6379/0"),
        ("QDRANT_URL", "https://qdrant.example.com"),
        ("CORE_RAG_BASE_URL", "https://api.chisa.example.com"),
        ("PUBLIC_APP_URL", "https://chisa.example.com"),
    ),
)
def test_non_local_endpoints_are_refused(key: str, url: str) -> None:
    found = problems(**{key: url})
    assert any(key in p and "localhost" in p for p in found)
    assert not any("example.com" in p for p in found)  # the offending host is never echoed


def test_loopback_variants_are_local() -> None:
    assert problems(REDIS_URL="redis://127.0.0.1:6379/0", QDRANT_URL="http://[::1]:6333") == []


@pytest.mark.parametrize("key", ("JWT_SECRET", "SECRET_KEY", "DISCORD_WORKLOAD_JWT_SECRET"))
def test_secrets_must_be_real_and_long(key: str) -> None:
    assert any(key in p and "missing" in p for p in problems(**{key: ""}))
    assert any(key in p and "template" in p for p in problems(**{key: "change_this_" + "x" * 30}))
    assert any(key in p and "32" in p for p in problems(**{key: "short"}))


def test_the_selected_llm_and_reranker_need_their_keys() -> None:
    assert any("DEEPSEEK_API_KEY" in p for p in problems(DEEPSEEK_API_KEY=""))
    assert any("unknown LLM provider" in p for p in problems(LLM_PROVIDER="made-up"))
    assert any("VOYAGE_API_KEY" in p for p in problems(RERANKER_PROVIDER="voyage"))
    assert problems(RERANKER_PROVIDER="voyage", VOYAGE_API_KEY="pa-dev-key-123456") == []


def test_database_url_needs_a_password() -> None:
    assert any(
        "password" in p
        for p in problems(DATABASE_URL="postgresql+asyncpg://chisa@localhost:5432/chisa_db")
    )


def test_shell_environment_cannot_silently_override_env(monkeypatch) -> None:
    env = good_env()
    for key in dev_stack.SAFETY_KEYS:  # the pytest process has its own test endpoints
        monkeypatch.delenv(key, raising=False)
    assert dev_stack.conflicting_process_env(env) == []
    monkeypatch.setenv("APP_ENV", "production")
    assert dev_stack.conflicting_process_env(env) == ["APP_ENV"]
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@prod.example.com/db")
    assert dev_stack.conflicting_process_env(env) == ["DATABASE_URL"]


def test_discord_secret_must_match_core_without_printing_it(tmp_path, monkeypatch) -> None:
    discord_env = tmp_path / ".env"
    discord_env.write_text(
        "DISCORD_TOKEN=real-looking-token-value\nDISCORD_CLIENT_ID=123\n"
        "CORE_RAG_WORKLOAD_JWT_SECRET=" + "x" * 40 + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(dev_stack, "ROOT", tmp_path)
    (tmp_path / "discord").mkdir()
    (tmp_path / "discord" / ".env").write_text(discord_env.read_text(), encoding="utf-8")
    found = dev_stack.validate_discord(good_env())
    assert any("must equal DISCORD_WORKLOAD_JWT_SECRET" in p for p in found)
    assert "x" * 40 not in " ".join(found) and "d" * 40 not in " ".join(found)


# ── Secret hygiene ──────────────────────────────────────────────────────


def test_scrub_removes_every_known_secret_including_url_passwords() -> None:
    env = good_env()
    secrets = dev_stack.secret_values(env)
    text = (
        f"jwt={env['JWT_SECRET']} key={env['DEEPSEEK_API_KEY']} "
        "dsn=postgresql://chisa:pw-for-dev-1234@localhost/db"
    )
    cleaned = dev_stack.scrub(text, secrets)
    for leaked in (env["JWT_SECRET"], env["DEEPSEEK_API_KEY"], "pw-for-dev-1234"):
        assert leaked not in cleaned
    assert cleaned.count("***") == 3


def test_placeholder_values_are_not_treated_as_secrets() -> None:
    assert dev_stack.secret_values({"X_API_KEY": "replace_with_real_key_value"}) == []


# ── Contracts ───────────────────────────────────────────────────────────


def test_stop_never_touches_infrastructure_outside_development(monkeypatch) -> None:
    monkeypatch.setattr(dev_stack, "stop_process", lambda name: False)
    monkeypatch.setattr(dev_stack, "load_env", lambda path: good_env(APP_ENV="production"))
    with pytest.raises(dev_stack.DevError, match="APP_ENV"):
        dev_stack.cmd_stop(argparse.Namespace(infra=True), "python")


def test_the_cli_can_never_delete_data() -> None:
    source = (ROOT / "scripts" / "dev_stack.py").read_text(encoding="utf-8")
    for forbidden in ('"down"', "--volumes", '"-v"', '"rm"', "volume rm", "DROP DATABASE"):
        assert forbidden not in source, forbidden


def test_dev_compose_is_loopback_only_and_secretless() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.dev.yml").read_text(encoding="utf-8"))
    assert set(compose["services"]) == {"postgres", "redis", "qdrant"}
    for name, service in compose["services"].items():
        assert all(port.startswith("127.0.0.1:") for port in service["ports"]), name
        assert "secrets" not in service, name
    assert "secrets" not in compose
    postgres = compose["services"]["postgres"]["environment"]
    assert "${CHISA_DEV_POSTGRES_PASSWORD:?" in postgres["POSTGRES_PASSWORD"]
    # Same project/volume names as the pre-existing dev stack: data is reused.
    assert compose["name"] == "kuchiba_chisa"
    assert not any(isinstance(v, dict) and v.get("external") for v in compose["volumes"].values())


def test_smoke_workload_token_satisfies_the_core_contract() -> None:
    env = good_env()
    # Core verifies with the settings secret; mint with the same value to prove shape/claims.
    token = dev_stack.mint_workload_token(
        {**env, "DISCORD_WORKLOAD_JWT_SECRET": settings.DISCORD_WORKLOAD_JWT_SECRET},
        "11111111-2222-4333-8444-555555555555",
        ["chat:write", "chat:clear"],
    )
    principal = jwt_authenticator.authenticate_bearer(f"Bearer {token}")
    assert principal.source == "discord" and principal.kind == "workload"
    assert principal.scopes == frozenset({"chat:write", "chat:clear"})


def test_unreachable_http_is_reported_as_status_zero_not_an_exception() -> None:
    assert dev_stack.http_json("GET", "http://127.0.0.1:9/never-listening", timeout=1) == (0, None)
    assert dev_stack.http_status("http://127.0.0.1:9/never-listening", timeout=1) is None


@pytest.mark.asyncio
async def test_qdrant_bootstrap_refuses_to_run_outside_development() -> None:
    assert not settings.is_dev  # the test suite runs with APP_ENV=test
    assert await dev_bootstrap_qdrant.bootstrap() == 2


def test_lore_acl_gap_reports_counts_and_failures(monkeypatch) -> None:
    calls: list[str] = []

    def fake_http(method, url, body=None, headers=None, timeout=30.0):
        calls.append(url)
        return 200, {"result": {"count": 7 if "world_lore" in url else 0}}

    monkeypatch.setattr(dev_stack, "http_json", fake_http)
    assert dev_stack.lore_acl_gap(good_env()) == {
        "character_lore": 0,
        "world_lore": 7,
        "story_lore": 0,
    }
    assert all("__active" in url for url in calls)

    monkeypatch.setattr(dev_stack, "http_json", lambda *a, **k: (500, None))
    with pytest.raises(dev_stack.DevError, match="count failed"):
        dev_stack.lore_acl_gap(good_env())


def test_command_line_surface() -> None:
    parser = dev_stack.build_parser()
    start = parser.parse_args(["start", "--discord", "--no-frontend", "--no-backup"])
    assert start.discord and start.no_frontend and start.no_backup and not start.no_worker
    assert parser.parse_args(["stop", "--infra"]).infra is True
    assert parser.parse_args(["logs", "backend", "-n", "5", "-f"]).follow is True
    for command in (
        "restart",
        "status",
        "test",
        "migrate",
        "bootstrap",
        "check",
        "backfill-lore-acl",
    ):
        assert parser.parse_args([command]).command == command
    with pytest.raises(SystemExit):
        parser.parse_args(["logs", "not-a-service"])


def test_every_command_is_wired() -> None:
    parser = dev_stack.build_parser()
    commands = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    assert set(commands.choices) == set(dev_stack.COMMANDS)
