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

    # ── SSE Streaming Lifecycle ────────────────────────────────
    SSE_MAX_QUEUE_SIZE: int = 100
    SSE_TIMEOUT: int = 120

    # ── Application ────────────────────────────────────────────
    APP_ENV: Literal["development", "production", "test"] = "development"
    APP_PORT: int = Field(default=8000, ge=1, le=65535)
    APP_HOST: str = "0.0.0.0"
    WEB_CONCURRENCY: int = Field(default=2, ge=1, le=16)
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
    LLM_PROVIDER: Literal["groq", "gemini", "deepseek"] = Field(default="groq", validation_alias="LLM_PROVIDER")


    # ── LLM — Groq ─────────────────────────────────────────────
    GROQ_API_KEY: Optional[str] = None
    GROQ_MODEL: str = "llama-3.1-8b-instant"
    GROQ_MAX_TOKENS: int = 2048
    GROQ_TEMPERATURE: float = Field(default=0.8, ge=0.0, le=2.0)
    GROQ_TIMEOUT: int = 30

    # ── LLM — Gemini ─────────────────────────────────────────────
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-flash-lite"
    GEMINI_MAX_TOKENS: int = 8192
    GEMINI_TEMPERATURE: float = Field(default=0.8, ge=0.0, le=2.0)
    GEMINI_TIMEOUT: int = 30

    # ── LLM — DeepSeek ──────────────────────────────────────────
    DEEPSEEK_API_KEY: Optional[str] = None
    DEEPSEEK_MODEL: str = "deepseek-v4-flash"
    DEEPSEEK_MAX_TOKENS: int = 8192
    DEEPSEEK_TEMPERATURE: float = Field(default=0.8, ge=0.0, le=2.0)
    DEEPSEEK_TIMEOUT: int = 60
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    DEEP_THINKING: bool = False

    # ── Embeddings ─────────────────────────────────────────────
    OPENAI_API_KEY: Optional[str] = None
    EMBEDDING_MODEL: str = "intfloat/multilingual-e5-small"

    # ── Search API Keys (Optional Free Tiers) ──────────────────
    TAVILY_API_KEY: Optional[str] = None
    SERPER_API_KEY: Optional[str] = None
    ENABLE_PAID_SEARCH: bool = False

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

    # ── Prompt Budget ──────────────────────────────────────────
    PROMPT_BUDGET_SMALL_TALK: int = 5000
    PROMPT_BUDGET_RAG: int = 8000
    PROMPT_BUDGET_LOOP: int = 12000
    PROMPT_CHARS_PER_TOKEN: int = 2
    PROMPT_FLEX_RATIO: float = Field(default=0.08, ge=0.0, le=0.25)
    PROMPT_SKELETON_HEADROOM: float = Field(default=0.05, ge=0.0, le=0.25)
    PROMPT_HISTORY_MIN_TURNS: int = Field(default=4, ge=1, le=20)
    PROMPT_REALLOCATE_EMPTY: bool = True
    MAX_RESPONSE_TOKENS: int = 20000

    # ── LLM Telemetry Logging ──────────────────────────────────
    LLM_LOG_FILE: str = "logs/llm_api.jsonl"
    LLM_LOG_MAX_BYTES: int = 10 * 1024 * 1024  # 10 MB default
    LLM_LOG_BACKUP_COUNT: int = 5

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
