"""Part 3 regression: production code paths never seed users, accounts or credentials."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

ACCOUNT_TABLES = ("users", "accounts", "account_identities", "auth_sessions", "discord_users")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_migrations_do_not_insert_users_or_accounts() -> None:
    for migration in (ROOT / "alembic_migrations" / "versions").glob("*.py"):
        source = _read(migration)
        assert "bulk_insert" not in source, migration.name
        for table in ACCOUNT_TABLES:
            pattern = rf"insert\s+into\s+{table}\b"
            assert not re.search(pattern, source, re.IGNORECASE), (migration.name, table)


def test_startup_entrypoints_do_not_create_accounts() -> None:
    entrypoints = [
        ROOT / "app" / "main.py",
        ROOT / "app" / "worker.py",
        ROOT / "Dockerfile",
        ROOT / "docker-compose.yml",
        ROOT / "discord" / "Dockerfile",
        ROOT / "discord" / "src" / "index.js",
        ROOT / "discord" / "src" / "app.js",
        ROOT / "discord" / "src" / "events" / "ready.js",
    ]
    forbidden = (
        "create_password_account",
        "create_external_account",
        "get_or_create_user",
        "ensureDiscordUser",
        "INSERT INTO users",
        "INSERT INTO accounts",
        "INSERT INTO discord_users",
    )
    # The isolated test image ships only the Python app plus selected configs, so
    # skip build/Discord files that are absent there; the Python entrypoints must exist.
    assert entrypoints[0].exists() and entrypoints[1].exists()
    for entrypoint in entrypoints:
        if not entrypoint.exists():
            continue
        source = _read(entrypoint)
        for token in forbidden:
            assert token not in source, (entrypoint.name, token)


def test_operator_scripts_do_not_seed_database_users() -> None:
    offenders = []
    for script in (ROOT / "scripts").glob("*.py"):
        source = _read(script)
        if re.search(r"\bUser\(\s*id\s*=", source) or "terminal_temp_user" in source:
            offenders.append(script.name)
    assert offenders == []


def test_no_hard_coded_credentials_in_application_code() -> None:
    pattern = re.compile(
        r"""(password|passwd|secret)\s*=\s*["'][^"'\s]{6,}["']""", re.IGNORECASE
    )
    offenders = []
    for path in (ROOT / "app").rglob("*.py"):
        for line_no, line in enumerate(_read(path).splitlines(), start=1):
            if pattern.search(line):
                offenders.append(f"{path.relative_to(ROOT)}:{line_no}")
    assert offenders == []
