from __future__ import annotations

from functools import lru_cache
from typing import Literal, Optional

from pydantic import Field, field_validator, model_validator
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
    THINKING_LOOP_TIMEOUT: int = 25

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
    DEEPSEEK_VISION_MODEL: str = "deepseek-v4-flash-vision-exp"
    DEEPSEEK_MAX_TOKENS: int = 8192
    DEEPSEEK_TEMPERATURE: float = Field(default=0.8, ge=0.0, le=2.0)
    DEEPSEEK_TIMEOUT: int = 60
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    DEEP_THINKING: bool = True
    # â”€â”€ Request admission limits (SEC-05 / SEC-API-003) â”€â”€
    CHAT_MAX_MESSAGE_CHARS: int = Field(default=4_000, ge=1, le=20_000)
    COMMUNITY_MAX_HISTORY_MESSAGES: int = Field(default=20, ge=1, le=100)
    COMMUNITY_MAX_MESSAGE_CHARS: int = Field(default=4_000, ge=1, le=20_000)
    COMMUNITY_MAX_REPLY_CONTEXT_CHARS: int = Field(default=1_000, ge=1, le=10_000)
    COMMUNITY_MAX_IDENTIFIER_CHARS: int = Field(default=128, ge=1, le=512)
    COMMUNITY_MAX_TIMESTAMP_CHARS: int = Field(default=64, ge=1, le=256)
    VISION_MAX_IMAGES: int = Field(default=4, ge=1, le=4)
    VISION_MAX_IMAGE_BYTES: int = Field(default=10 * 1024 * 1024, ge=1_024)
    VISION_MAX_IMAGE_URL_CHARS: int = Field(default=2_048, ge=64, le=16_384)
    VISION_MAX_TOTAL_DECODED_BYTES: int = Field(default=40 * 1024 * 1024, ge=1_024)
    API_MAX_REQUEST_BODY_BYTES: int = Field(default=60 * 1024 * 1024, ge=1_024)
    VISION_STORAGE_MAX_MB: int = 1024
    VISION_STORAGE_BACKEND: str = "local"  # "local" | "s3" | "r2" | "minio" | "cloudinary"
    VISION_LOCAL_STORAGE_DIR: str = "app/static/uploads"
    VISION_STORAGE_BASE_URL: str = "/static/uploads"

    # ── S3 / Cloudflare R2 / MinIO Object Storage (Optional) ───
    VISION_S3_BUCKET: Optional[str] = None
    VISION_S3_REGION: str = "auto"
    VISION_S3_ENDPOINT_URL: Optional[str] = None  # e.g. https://<account_id>.r2.cloudflarestorage.com or MinIO URL
    VISION_S3_ACCESS_KEY: Optional[str] = None
    VISION_S3_SECRET_KEY: Optional[str] = None
    VISION_S3_PUBLIC_DOMAIN: Optional[str] = None  # e.g. https://cdn.mysite.com

    # ── Cloudinary Image Hosting (Optional) ────────────────────
    CLOUDINARY_CLOUD_NAME: Optional[str] = None
    CLOUDINARY_API_KEY: Optional[str] = None
    CLOUDINARY_API_SECRET: Optional[str] = None

    # ── Embeddings & Semantic Router ───────────────────────────
    OPENAI_API_KEY: Optional[str] = None
    EMBEDDING_MODEL: str = "intfloat/multilingual-e5-small"
    INTENT_SEMANTIC_THRESHOLD: float = 0.65
    INTENT_ENABLE_L3_SEMANTIC: bool = True

    # ── Search API Keys (Optional Free Tiers) ──────────────────
    TAVILY_API_KEY: Optional[str] = None
    SERPER_API_KEY: Optional[str] = None
    ENABLE_PAID_SEARCH: bool = False

    # ── JWT ────────────────────────────────────────────────────
    JWT_SECRET: str = Field(min_length=32)
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60
    JWT_REFRESH_EXPIRE_DAYS: int = 7
    JWT_ISSUER: str = "kuchiba-chisa"
    JWT_AUDIENCE: str = "kuchiba-chisa-api"
    DISCORD_WORKLOAD_JWT_SECRET: str = Field(min_length=32)
    DISCORD_WORKLOAD_JWT_ISSUER: str = "kuchiba-chisa-discord"

    # ── Rate Limiting ──────────────────────────────────────────
    RATE_LIMIT_PER_MINUTE: int = 60
    RATE_LIMIT_LOCAL_FALLBACK_MAX_KEYS: int = Field(default=10_000, ge=100, le=100_000)
    RATE_LIMIT_IP_ANOMALY_PER_MINUTE: int = Field(default=120, ge=1, le=10_000)
    ANONYMOUS_SESSION_RATE_LIMIT_PER_MINUTE: int = Field(default=10, ge=1, le=1_000)
    TRUSTED_PROXY_CIDRS: str = ""

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
    PIPELINE_TRACE_TTL_SECONDS: int = Field(default=3_600, ge=60, le=2_592_000)

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

    @model_validator(mode="after")
    def validate_request_admission_limits(self) -> Settings:
        """Ensure transport/body limits can carry the configured safe image quota."""
        max_encoded_image_bytes = 4 * ((self.VISION_MAX_IMAGE_BYTES + 2) // 3)
        min_total_decoded = self.VISION_MAX_IMAGES * self.VISION_MAX_IMAGE_BYTES
        if min_total_decoded > self.VISION_MAX_TOTAL_DECODED_BYTES:
            raise ValueError("VISION_MAX_TOTAL_DECODED_BYTES cannot be below the image quota")
        if self.VISION_MAX_IMAGES * max_encoded_image_bytes > self.API_MAX_REQUEST_BODY_BYTES:
            raise ValueError("API_MAX_REQUEST_BODY_BYTES cannot carry the configured image quota")
        return self


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
