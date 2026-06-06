from __future__ import annotations

from functools import lru_cache
from typing import Literal, Optional

from pydantic import AnyUrl, Field, RedisDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Centralized application configuration loaded from environment variables.
    Validated at startup via Pydantic — fail-fast on misconfiguration.
    No environment variable reads anywhere else in the codebase.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ── Application ────────────────────────────────────────────
    APP_ENV: Literal["development", "production", "test"] = "development"
    APP_PORT: int = Field(default=8000, ge=1, le=65535)
    APP_HOST: str = "0.0.0.0"
    APP_DEBUG: bool = False
    SECRET_KEY: str = Field(min_length=32)

    # ── PostgreSQL ─────────────────────────────────────────────
    DATABASE_URL: str  # postgresql+asyncpg://user:pass@host:port/db

    # ── Redis ──────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_PASSWORD: Optional[str] = None

    # ── Qdrant ─────────────────────────────────────────────────
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_API_KEY: Optional[str] = None
    QDRANT_EMBEDDING_DIM: int = 384

    # ── LLM — Provider ─────────────────────────────────────────
    LLM_PROVIDER: Literal["groq", "gemini"] = Field(default="groq", validation_alias="LLM_PROVIDER")

    # ── LLM — Groq ─────────────────────────────────────────────
    GROQ_API_KEY: Optional[str] = None
    GROQ_MODEL: str = "llama-3.1-8b-instant"
    GROQ_MAX_TOKENS: int = 2048
    GROQ_TEMPERATURE: float = Field(default=0.8, ge=0.0, le=2.0)
    GROQ_TIMEOUT: int = 30

    # ── LLM — Gemini ─────────────────────────────────────────────
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-2.5-flash-lite"
    GEMINI_MAX_TOKENS: int = 8192
    GEMINI_TEMPERATURE: float = Field(default=0.8, ge=0.0, le=2.0)
    GEMINI_TIMEOUT: int = 30

    # ── Embeddings ─────────────────────────────────────────────
    OPENAI_API_KEY: Optional[str] = None
    EMBEDDING_MODEL: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

    # ── JWT ────────────────────────────────────────────────────
    JWT_SECRET: str = Field(min_length=32)
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60
    JWT_REFRESH_EXPIRE_DAYS: int = 7

    # ── Rate Limiting ──────────────────────────────────────────
    RATE_LIMIT_PER_MINUTE: int = 60

    # ── Celery / Workers ───────────────────────────────────────
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"
    WORKER_CONCURRENCY: int = 4

    # ── Derived Properties ─────────────────────────────────────
    @property
    def is_dev(self) -> bool:
        return self.APP_ENV == "development"

    @property
    def is_prod(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def is_test(self) -> bool:
        return self.APP_ENV == "test"

    @field_validator("DATABASE_URL")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        if not v.startswith("postgresql"):
            raise ValueError("DATABASE_URL must be a PostgreSQL connection string")
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Cached settings singleton. Use this throughout the codebase.
    Call invalidate_settings_cache() in tests to reset.
    """
    return Settings()


def invalidate_settings_cache() -> None:
    """For test isolation only."""
    get_settings.cache_clear()


# Module-level singleton for convenient imports
settings = get_settings()
