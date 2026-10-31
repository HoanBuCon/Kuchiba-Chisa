"""Inference service settings; separate so it needs none of the application secrets."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class InferenceSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore", case_sensitive=True)

    EMBEDDING_MODEL: str = "intfloat/multilingual-e5-small"
    # A provisioned local cross-encoder enables /v1/rerank; unset keeps the endpoint off.
    RERANKER_MODEL: str | None = None
    RERANKER_BATCH_SIZE: int = Field(default=16, ge=1, le=64)
    RERANKER_TIMEOUT_SECONDS: float = Field(default=5.0, gt=0, le=30)
    INFERENCE_THREADS: int = Field(default=2, ge=1, le=8)
    # Measured in a Linux cgroup with e5-small fp32 (~512-token passages): batch 8 peaks at
    # 1.07 GB, batch 32 at 1.86 GB; 8 keeps the service inside its 1.4 GB limit.
    INFERENCE_MAX_BATCH: int = Field(default=8, ge=1, le=64)
    INFERENCE_MAX_TEXT_CHARS: int = Field(default=8000, ge=256, le=32_000)
    # One batch at a time bounds peak RAM inside the container budget (SRS 3.4).
    INFERENCE_CONCURRENCY: int = Field(default=1, ge=1, le=4)
