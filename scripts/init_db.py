"""Compatibility entry point for applying the Alembic-owned schema.

This script intentionally contains no SQLAlchemy ``create_all`` or direct DDL.
Operators should normally use ``python -m alembic upgrade head`` directly.
"""

from alembic import command
from alembic.config import Config


def migrate_to_head() -> None:
    """Apply versioned migrations using the repository Alembic configuration."""
    command.upgrade(Config("alembic.ini"), "head")


if __name__ == "__main__":
    migrate_to_head()
