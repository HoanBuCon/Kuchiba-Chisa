"""Read-only verification of the Alembic-owned production schema revision."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession


class SchemaRevisionMismatchError(RuntimeError):
    """Raised when the database is not at the repository's Alembic head."""


@dataclass(frozen=True)
class SchemaRevisionStatus:
    """Auditable comparison between database revisions and migration heads."""

    current: frozenset[str]
    expected: frozenset[str]

    @property
    def is_current(self) -> bool:
        return self.current == self.expected


@lru_cache(maxsize=1)
def expected_schema_heads() -> frozenset[str]:
    """Resolve migration heads from the repository Alembic configuration."""
    repository_root = Path(__file__).resolve().parents[3]
    config_path = repository_root / "alembic.ini"
    config = Config(str(config_path))
    config.set_main_option("script_location", str(repository_root / "alembic_migrations"))
    return frozenset(ScriptDirectory.from_config(config).get_heads())


def require_current_schema(status: SchemaRevisionStatus) -> None:
    """Fail closed when a database revision differs from Alembic head."""
    if not status.is_current:
        current = ",".join(sorted(status.current)) or "<missing>"
        expected = ",".join(sorted(status.expected)) or "<missing>"
        raise SchemaRevisionMismatchError(
            f"Database schema revision mismatch: current={current}; expected={expected}"
        )


async def verify_database_schema_revision(session: AsyncSession) -> SchemaRevisionStatus:
    """Read and validate ``alembic_version`` without mutating database schema."""
    try:
        result = await session.execute(text("SELECT version_num FROM alembic_version"))
    except SQLAlchemyError as exc:
        raise SchemaRevisionMismatchError(
            "Alembic revision table is unavailable"
        ) from exc
    status = SchemaRevisionStatus(
        current=frozenset(str(row[0]) for row in result.all()),
        expected=expected_schema_heads(),
    )
    require_current_schema(status)
    return status
