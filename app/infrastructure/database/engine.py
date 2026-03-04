from __future__ import annotations

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config.settings import settings
from app.infrastructure.logging.logger import get_logger

log = get_logger(__name__)

# ─── SQLAlchemy Async Engine ──────────────────────────────────────────────────

engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.is_dev,          # SQL query logging in dev
    echo_pool=settings.is_dev,     # Pool event logging in dev
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,            # Verify connections before use
    pool_recycle=3600,             # Recycle connections every hour
)

# ─── Session Factory ──────────────────────────────────────────────────────────

AsyncSessionFactory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,        # Don't expire objects after commit
    autoflush=False,
    autocommit=False,
)

# ─── Base Model ───────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    """
    All SQLAlchemy ORM models inherit from this base.
    Models are defined in Phase 3: Database Schema Design.
    """
    pass


# ─── Session Dependency (FastAPI) ─────────────────────────────────────────────

async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that provides a database session per request.
    Automatically commits on success or rolls back on exception.

    Usage:
        @router.post("/example")
        async def handler(db: AsyncSession = Depends(get_db_session)):
            ...
    """
    async with AsyncSessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ─── Health Check ─────────────────────────────────────────────────────────────

async def check_database_health() -> bool:
    """Returns True if the database is reachable."""
    try:
        async with AsyncSessionFactory() as session:
            await session.execute(__import__("sqlalchemy").text("SELECT 1"))
        return True
    except Exception as e:
        log.error("Database health check failed", error=str(e))
        return False


# ─── Lifecycle Helpers ────────────────────────────────────────────────────────

async def connect_database() -> None:
    """Called on application startup."""
    log.info("Connecting to PostgreSQL...", url=settings.DATABASE_URL.split("@")[-1])
    healthy = await check_database_health()
    if healthy:
        log.info("PostgreSQL connection established")
    else:
        raise RuntimeError("PostgreSQL health check failed on startup")


async def disconnect_database() -> None:
    """Called on application shutdown."""
    await engine.dispose()
    log.info("PostgreSQL engine disposed")
