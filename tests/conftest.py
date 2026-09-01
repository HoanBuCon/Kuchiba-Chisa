"""Pytest configuration and shared fixtures for Chisa test suite."""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from qdrant_client.http.models import (
    CreateAlias,
    CreateAliasOperation,
    DeleteAlias,
    DeleteAliasOperation,
    Distance,
    VectorParams,
)
from sqlalchemy import text

# ── Force test environment before any app imports ───────────────────
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://chisa:chisa_test_secret@localhost:55432/chisa_test"
)
os.environ.setdefault("REDIS_URL", "redis://localhost:56379/15")
os.environ.setdefault("CELERY_BROKER_URL", "redis://localhost:56379/14")
os.environ.setdefault("CELERY_RESULT_BACKEND", "redis://localhost:56379/14")
os.environ.setdefault("QDRANT_URL", "http://localhost:16333")
os.environ.setdefault("GROQ_API_KEY", "test_groq_key_placeholder")
os.environ.setdefault("JWT_SECRET", "test_jwt_secret_that_is_long_enough_for_validation")
os.environ.setdefault(
    "DISCORD_WORKLOAD_JWT_SECRET", "test_discord_workload_secret_that_is_long_enough"
)
os.environ.setdefault("SECRET_KEY", "test_secret_key_that_is_long_enough_for_validation")

from app.config.settings import invalidate_settings_cache  # noqa: E402

invalidate_settings_cache()

from app.domain.interfaces.llm_provider import (  # noqa: E402
    BaseLLMAdapter,
    LLMResponse,
    StructuredPrompt,
)
from app.main import app  # noqa: E402


class DeterministicTestLLM(BaseLLMAdapter):
    """Test-only adapter: orchestration tests never call an external LLM provider."""

    _model = "deterministic-test-adapter"

    @staticmethod
    def _schema_value(schema: dict[str, Any], field_name: str = "") -> Any:
        if "enum" in schema:
            return schema["enum"][0]
        value_type = schema.get("type")
        if isinstance(value_type, list):
            value_type = next((item for item in value_type if item != "null"), "null")
        if value_type == "boolean":
            return field_name == "is_neutral"
        if value_type == "integer":
            return int(schema.get("minimum", 0))
        if value_type == "number":
            return float(schema.get("minimum", 0.0))
        if value_type == "array":
            return []
        if value_type == "object":
            return {
                key: DeterministicTestLLM._schema_value(value, key)
                for key, value in schema.get("properties", {}).items()
            }
        if value_type == "null":
            return None
        if field_name == "response":
            return "Deterministic test reply."
        if field_name == "rewritten_query":
            return "deterministic test query"
        return "deterministic"

    def _response_payload(self, prompt: StructuredPrompt) -> dict[str, Any]:
        properties = prompt.response_schema.get("properties", {})
        payload = {key: self._schema_value(value, key) for key, value in properties.items()}
        if "rewritten_query" in properties:
            payload["rewritten_query"] = self._rewrite_query(prompt.user_message)
        return payload

    @staticmethod
    def _rewrite_query(user_message: str) -> str:
        """Provide stable semantic output for query-rewrite integration assertions."""
        if "năng lực" in user_message.lower():
            return "Kuchiba Chisa năng lực"
        return "deterministic test query"

    async def generate(self, prompt: StructuredPrompt) -> LLMResponse:
        payload = self._response_payload(prompt)
        raw_content = json.dumps(payload, ensure_ascii=False)
        return LLMResponse(raw_content=raw_content, parsed=payload, model=self._model)

    async def stream(self, prompt: StructuredPrompt) -> AsyncIterator[str]:
        payload = self._response_payload(prompt)
        yield json.dumps(payload, ensure_ascii=False)

    async def validate_response(self, raw: str, schema: dict[str, Any]) -> dict[str, Any]:
        del schema
        return json.loads(raw)

    async def estimate_tokens(self, text: str) -> int:
        return len(text.split())


class DeterministicMemoryLLM(DeterministicTestLLM):
    """Deterministic extraction/reconciliation decisions for memory storage integration tests."""

    def _response_payload(self, prompt: StructuredPrompt) -> dict[str, Any]:
        properties = prompt.response_schema.get("properties", {})
        transcript = prompt.user_message.lower()
        if "facts" in properties:
            if "chỉ huy" in transcript:
                return {
                    "facts": [
                        {
                            "type": "shared_story",
                            "content": "Biệt danh của Senpai là Chỉ Huy",
                            "importance_score": 0.9,
                        }
                    ]
                }
            if "đà nẵng" in transcript:
                return {
                    "facts": [
                        {
                            "type": "user_fact",
                            "content": "Senpai sống ở Đà Nẵng",
                            "importance_score": 0.9,
                        }
                    ]
                }
            if "hà nội" in transcript:
                return {
                    "facts": [
                        {
                            "type": "user_fact",
                            "content": "Senpai sống ở Hà Nội",
                            "importance_score": 0.9,
                        }
                    ]
                }
            if "cáo đen" in transcript:
                return {
                    "facts": [
                        {
                            "type": "shared_story",
                            "content": "Biệt danh của Senpai là Cáo Đen",
                            "importance_score": 0.9,
                        }
                    ]
                }
            if "chỉ huy" in transcript:
                return {
                    "facts": [
                        {
                            "type": "shared_story",
                            "content": "Biệt danh của Senpai là Chỉ Huy",
                            "importance_score": 0.9,
                        }
                    ]
                }
            return {"facts": []}
        if "reconciliations" in properties:
            if (
                "hà nội" in transcript
                and "đà nẵng" in transcript
                or "chỉ huy" in transcript
                and "cáo đen" in transcript
            ):
                action = "CONTRADICT"
            elif "chỉ huy" in transcript:
                action = "DUPLICATE"
            else:
                action = "KEEP_BOTH"
            return {
                "reconciliations": [
                    {
                        "index": 0,
                        "action": action,
                        "conflicting_candidate_index": 0 if action == "CONTRADICT" else None,
                    }
                ]
            }
        return super()._response_payload(prompt)


def _assert_isolated_test_endpoints() -> None:
    """Refuse to run integration fixtures against the default developer services."""
    from app.config.settings import settings

    allowed_database_hosts = ("@localhost:55432/", "@postgres:5432/")
    allowed_qdrant_urls = ("http://localhost:16333", "http://qdrant:6333")
    allowed_redis_urls = ("localhost:56379", "redis:6379")

    if settings.APP_ENV != "test":
        raise RuntimeError("Integration fixtures require APP_ENV=test.")
    if not any(host in settings.DATABASE_URL for host in allowed_database_hosts):
        raise RuntimeError("Refusing to use a PostgreSQL endpoint outside the isolated test stack.")
    if settings.QDRANT_URL.rstrip("/") not in allowed_qdrant_urls:
        raise RuntimeError("Refusing to use a Qdrant endpoint outside the isolated test stack.")
    if not any(host in settings.REDIS_URL for host in allowed_redis_urls):
        raise RuntimeError("Refusing to use a Redis endpoint outside the isolated test stack.")


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest_asyncio.fixture(autouse=True)
async def flush_pipeline_tracker_after_test() -> AsyncIterator[None]:
    """Drain test-created trace publication tasks before their request loop closes."""
    yield
    from app.infrastructure.logging.pipeline_tracker import pipeline_tracker

    await pipeline_tracker.flush()


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    """
    Async HTTP client for testing FastAPI routes.
    Uses ASGI transport (no real HTTP server needed).
    """
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        yield ac


@pytest_asyncio.fixture(scope="session")
async def isolated_postgres() -> AsyncIterator[None]:
    """Verify that Alembic has prepared the disposable PostgreSQL test database."""
    _assert_isolated_test_endpoints()
    from app.infrastructure.database.engine import AsyncSessionFactory

    async with AsyncSessionFactory() as session:
        result = await session.execute(text("SELECT to_regclass('public.users')"))
        if result.scalar_one() != "users":
            raise RuntimeError(
                "Test database schema is unavailable. "
                "Run Alembic against docker-compose.test.yml first."
            )
    yield


@pytest_asyncio.fixture(scope="session")
async def isolated_vector_store() -> AsyncIterator[Any]:
    """Create only missing collections in the disposable Qdrant test endpoint."""
    _assert_isolated_test_endpoints()
    from app.config.settings import settings
    from app.infrastructure.vector.qdrant.qdrant_service import (
        ALL_COLLECTIONS,
        active_collection_alias,
        qdrant_service,
    )

    for collection in ALL_COLLECTIONS:
        try:
            info = await qdrant_service._client.get_collection(collection)
        except Exception:
            await qdrant_service._client.create_collection(
                collection_name=collection,
                vectors_config=VectorParams(
                    size=settings.QDRANT_EMBEDDING_DIM, distance=Distance.COSINE
                ),
            )
            continue

        vector_config = info.config.params.vectors
        dimension = getattr(vector_config, "size", None)
        if dimension != settings.QDRANT_EMBEDDING_DIM:
            raise RuntimeError(
                f"Isolated Qdrant collection {collection!r} has dimension {dimension}; "
                f"expected {settings.QDRANT_EMBEDDING_DIM}. Recreate the disposable test stack."
            )

    aliases_response = await qdrant_service._client.get_aliases()
    existing_aliases = {
        alias.alias_name: alias.collection_name for alias in aliases_response.aliases
    }
    alias_operations: list[CreateAliasOperation | DeleteAliasOperation] = []
    for collection in ALL_COLLECTIONS:
        alias_name = active_collection_alias(collection)
        if existing_aliases.get(alias_name) == collection:
            continue
        if alias_name in existing_aliases:
            alias_operations.append(
                DeleteAliasOperation(delete_alias=DeleteAlias(alias_name=alias_name))
            )
        alias_operations.append(
            CreateAliasOperation(
                create_alias=CreateAlias(collection_name=collection, alias_name=alias_name)
            )
        )
    if alias_operations:
        await qdrant_service._client.update_collection_aliases(
            change_aliases_operations=alias_operations
        )
    yield qdrant_service


@pytest.fixture(scope="session")
def test_embedder() -> Any:
    """Use the production embedding adapter against the isolated test services."""
    _assert_isolated_test_endpoints()
    from app.infrastructure.embeddings.fastembed_adapter import FastEmbedAdapter

    return FastEmbedAdapter()


@pytest.fixture(scope="session")
def isolated_entity_resolver(tmp_path_factory: pytest.TempPathFactory) -> Any:
    """Build the entity dictionary in pytest's temporary area, never in the working corpus."""
    from app.domain.services.rag.entity_resolver import EntityResolver
    from app.domain.services.rag.entity_sync import sync_entities_dictionary

    dictionary_path = Path(tmp_path_factory.mktemp("entity_dictionary")) / "entities.json"
    sync_entities_dictionary(output_file=str(dictionary_path))
    resolver = EntityResolver(dict_path=str(dictionary_path))
    resolver.load()
    return resolver


@pytest.fixture
def test_chat_engine(
    isolated_entity_resolver: Any,
    isolated_postgres: None,
    isolated_vector_store: Any,
) -> Any:
    """Build a new application container per test without the module-level singleton."""
    del isolated_postgres, isolated_vector_store
    from app.application.dependencies import AppContainer

    test_container = AppContainer()
    test_container.__dict__["llm"] = DeterministicTestLLM()
    test_container.__dict__["entity_resolver"] = isolated_entity_resolver
    return test_container.chat_engine


@pytest.fixture
def isolated_memory_extractor(isolated_vector_store: Any, test_embedder: Any) -> Any:
    """Exercise the production memory extractor with real Qdrant and deterministic decisions."""
    from app.domain.services.memory_extractor import MemoryExtractor

    return MemoryExtractor(
        llm=DeterministicMemoryLLM(),
        embedder=test_embedder,
        vector_store=isolated_vector_store,
    )
