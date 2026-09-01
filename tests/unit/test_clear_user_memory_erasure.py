"""SEC-04 regression tests for complete, retryable user-data erasure."""

from __future__ import annotations

import hashlib
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.application.usecases.clear_user_memory import ClearUserMemoryUseCase
from app.shared.utils.user_identity import normalize_user_id, normalize_user_id_str


class _UnitOfWork:
    async def __aenter__(self) -> _UnitOfWork:
        return self

    async def __aexit__(self, exc_type, exc_value, traceback) -> None:
        return None


def _use_case(
    *,
    image_ids: list[str],
    vector_store: SimpleNamespace | None = None,
    image_storage: SimpleNamespace | None = None,
) -> tuple[ClearUserMemoryUseCase, SimpleNamespace]:
    conversation_repo = SimpleNamespace(
        get_image_ids_for_user=AsyncMock(return_value=image_ids),
        delete_all_for_user=AsyncMock(),
    )
    emotion_repo = SimpleNamespace(delete_all_for_user=AsyncMock())
    user_repo = SimpleNamespace(delete_all_for_user=AsyncMock())
    erasure_repo = SimpleNamespace(
        create=AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4())),
        finish=AsyncMock(),
    )
    dependencies = SimpleNamespace(
        conversation_repo=conversation_repo,
        emotion_repo=emotion_repo,
        user_repo=user_repo,
        erasure_repo=erasure_repo,
        cache=SimpleNamespace(delete=AsyncMock()),
        vector_store=vector_store
        or SimpleNamespace(delete_by_user=AsyncMock()),
        image_storage=image_storage,
    )
    use_case = ClearUserMemoryUseCase(
        uow_factory=lambda session: _UnitOfWork(),
        user_repo_factory=lambda session: dependencies.user_repo,
        emotion_repo_factory=lambda session: dependencies.emotion_repo,
        conv_repo_factory=lambda session: dependencies.conversation_repo,
        erasure_repo_factory=lambda session: dependencies.erasure_repo,
        vector_store=dependencies.vector_store,
        cache_provider=dependencies.cache,
        image_storage=dependencies.image_storage,
    )
    return use_case, dependencies


@pytest.mark.asyncio
async def test_user_erasure_acknowledges_every_user_scoped_store() -> None:
    image_storage = SimpleNamespace(delete_image=AsyncMock(return_value=True))
    use_case, dependencies = _use_case(
        image_ids=["image-b", "image-a"], image_storage=image_storage
    )
    user_id = "web:subject-a"

    result = await use_case.execute(SimpleNamespace(), user_id)

    user_uuid = normalize_user_id(user_id)
    canonical_user_id = normalize_user_id_str(user_id)
    assert result["status"] == "completed"
    assert result["stores"] == {
        "redis": "acknowledged",
        "qdrant": "acknowledged",
        "images": "acknowledged",
        "traces": "not_applicable_redacted",
        "postgres": "acknowledged",
    }
    assert dependencies.erasure_repo.create.await_args.args == (
        hashlib.sha256(canonical_user_id.encode()).hexdigest(),
    )
    assert dependencies.cache.delete.await_count == 2
    assert {call.args[0] for call in dependencies.cache.delete.await_args_list} == {
        f"chisa:user:{user_uuid}:state",
        f"chisa:user:{user_uuid}:summary",
    }
    assert dependencies.vector_store.delete_by_user.await_args_list[0].args == (
        "memories",
        canonical_user_id,
    )
    assert dependencies.vector_store.delete_by_user.await_args_list[1].args == (
        "image_memories",
        canonical_user_id,
    )
    assert image_storage.delete_image.await_args_list[0].args == ("image-b",)
    assert image_storage.delete_image.await_args_list[1].args == ("image-a",)
    dependencies.conversation_repo.delete_all_for_user.assert_awaited_once_with(user_uuid)
    dependencies.emotion_repo.delete_all_for_user.assert_awaited_once_with(user_uuid)
    dependencies.user_repo.delete_all_for_user.assert_awaited_once_with(user_uuid)
    assert dependencies.erasure_repo.finish.await_args.kwargs["status"] == "COMPLETED"


@pytest.mark.asyncio
async def test_user_erasure_records_retry_without_false_postgres_success() -> None:
    vector_store = SimpleNamespace(delete_by_user=AsyncMock(side_effect=RuntimeError("offline")))
    use_case, dependencies = _use_case(image_ids=[], vector_store=vector_store)

    result = await use_case.execute(SimpleNamespace(), "web:subject-a")

    assert result["status"] == "retry_required"
    assert result["stores"]["redis"] == "acknowledged"
    assert result["stores"]["failed_store"] == "qdrant"
    assert "postgres" not in result["stores"]
    dependencies.conversation_repo.delete_all_for_user.assert_not_awaited()
    dependencies.emotion_repo.delete_all_for_user.assert_not_awaited()
    dependencies.user_repo.delete_all_for_user.assert_not_awaited()
    assert dependencies.erasure_repo.finish.await_args.kwargs["status"] == "RETRY_REQUIRED"
    assert dependencies.erasure_repo.finish.await_args.kwargs["error_code"] == "RuntimeError"


@pytest.mark.asyncio
async def test_user_erasure_requires_object_storage_when_user_images_exist() -> None:
    use_case, dependencies = _use_case(image_ids=["image-a"])

    result = await use_case.execute(SimpleNamespace(), "web:subject-a")

    assert result["status"] == "retry_required"
    assert result["stores"]["failed_store"] == "images"
    dependencies.conversation_repo.delete_all_for_user.assert_not_awaited()
    assert dependencies.erasure_repo.finish.await_args.kwargs["status"] == "RETRY_REQUIRED"
