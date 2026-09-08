"""DB-01 unit checks for Alembic-only production schema ownership."""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.exc import ProgrammingError

from app.infrastructure.database import engine
from app.infrastructure.database.schema_revision import (
    SchemaRevisionMismatchError,
    SchemaRevisionStatus,
    expected_schema_heads,
    require_current_schema,
    verify_database_schema_revision,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_DDL = re.compile(
    r"\b(?:CREATE|ALTER|DROP)\s+(?:TABLE|INDEX)\b|metadata\.create_all|ensureSchema",
    re.IGNORECASE,
)


def test_repository_has_one_detectable_alembic_head() -> None:
    assert expected_schema_heads() == frozenset({"8b9d0e1f2a3c"})


def test_revision_contract_accepts_head_and_rejects_drift() -> None:
    expected = frozenset({"head"})
    require_current_schema(SchemaRevisionStatus(current=expected, expected=expected))

    with pytest.raises(SchemaRevisionMismatchError, match="current=old; expected=head"):
        require_current_schema(
            SchemaRevisionStatus(current=frozenset({"old"}), expected=expected)
        )

    with pytest.raises(SchemaRevisionMismatchError, match="current=<missing>"):
        require_current_schema(
            SchemaRevisionStatus(current=frozenset(), expected=expected)
        )


@pytest.mark.asyncio
async def test_database_revision_verification_is_read_only() -> None:
    result = Mock()
    result.all.return_value = [("8b9d0e1f2a3c",)]
    session = AsyncMock()
    session.execute.return_value = result

    status = await verify_database_schema_revision(session)

    assert status.is_current
    assert session.execute.await_count == 1
    statement = str(session.execute.await_args.args[0])
    assert statement == "SELECT version_num FROM alembic_version"
    assert RUNTIME_DDL.search(statement) is None


@pytest.mark.asyncio
async def test_missing_alembic_table_fails_with_sanitized_schema_error() -> None:
    session = AsyncMock()
    session.execute.side_effect = ProgrammingError("statement", {}, Exception("missing"))

    with pytest.raises(
        SchemaRevisionMismatchError, match="Alembic revision table is unavailable"
    ):
        await verify_database_schema_revision(session)


@pytest.mark.asyncio
async def test_health_check_fails_explicitly_for_revision_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class SessionContext:
        async def __aenter__(self) -> AsyncMock:
            return AsyncMock()

        async def __aexit__(self, *args: object) -> None:
            return None

    monkeypatch.setattr(engine, "AsyncSessionFactory", SessionContext)
    monkeypatch.setattr(
        engine,
        "verify_database_schema_revision",
        AsyncMock(side_effect=SchemaRevisionMismatchError("revision drift")),
    )

    assert await engine.check_database_health() is False


def test_production_runtime_paths_contain_no_schema_ddl() -> None:
    runtime_paths = (
        PROJECT_ROOT / "app",
        PROJECT_ROOT / "discord" / "src",
    )
    violations: list[str] = []
    auxiliary_sqlite_state = (
        PROJECT_ROOT / "app" / "infrastructure" / "ingestion" / "storage" / "state_db.py"
    )
    for root in runtime_paths:
        for path in root.rglob("*"):
            if path.suffix not in {".py", ".js"}:
                continue
            if path == auxiliary_sqlite_state:
                continue
            for line_number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1
            ):
                if RUNTIME_DDL.search(line):
                    violations.append(f"{path.relative_to(PROJECT_ROOT)}:{line_number}")

    assert violations == []
    assert not (PROJECT_ROOT / "discord" / "src" / "database" / "schema.sql").exists()


def test_auxiliary_ingestion_state_ddl_is_sqlite_scoped() -> None:
    path = (
        PROJECT_ROOT / "app" / "infrastructure" / "ingestion" / "storage" / "state_db.py"
    )
    source = path.read_text(encoding="utf-8")
    assert "sqlite3.connect" in source
    assert "DATABASE_URL" not in source


def test_database_bootstrap_delegates_to_alembic() -> None:
    source = (PROJECT_ROOT / "scripts" / "init_db.py").read_text(encoding="utf-8")
    assert 'command.upgrade(Config("alembic.ini"), "head")' in source
    assert RUNTIME_DDL.search(source) is None


def test_adoption_downgrade_is_explicitly_non_destructive() -> None:
    migration = (
        PROJECT_ROOT
        / "alembic_migrations"
        / "versions"
        / "7a8c9d0e1f2b_adopt_discord_schema_ownership.py"
    ).read_text(encoding="utf-8")
    downgrade = migration.split("def downgrade() -> None:", maxsplit=1)[1]
    assert "RuntimeError" in downgrade
    assert "drop_table" not in downgrade
    assert "DELETE FROM" not in migration
