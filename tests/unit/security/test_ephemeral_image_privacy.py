"""IMG-01 regression tests for ephemeral image processing."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.domain.entities.emotion import EmotionState
from app.domain.entities.user import UserStats
from app.domain.models.background_job import BackgroundJobType
from app.domain.services.chat_pipeline.context import ChatContext
from app.domain.services.chat_pipeline.stages.background_task_stage import BackgroundTaskStage
from app.domain.services.chat_pipeline.stages.initialization_stage import InitializationStage
from app.domain.services.chat_pipeline.stages.persistence_stage import PersistenceStage
from app.domain.services.image_ingestion import ImageIngestionService
from app.shared.security.vision_security import ImageSanitizer


@pytest.mark.asyncio
async def test_ephemeral_image_is_processed_in_memory_without_storage_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = MagicMock()
    storage.save_sanitized_image = AsyncMock()
    sanitizer_result = {
        "sanitized_bytes": b"sanitized-image",
        "mime_type": "image/webp",
        "width": 32,
        "height": 32,
        "size_bytes": 15,
    }
    monkeypatch.setattr(ImageSanitizer, "sanitize_image", AsyncMock(return_value=sanitizer_result))

    images = await ImageIngestionService(storage=storage).ingest_images(
        ["data:image/png;base64,aGVsbG8="],
        save_to_disk=False,
        is_ephemeral=True,
    )

    storage.save_sanitized_image.assert_not_awaited()
    assert images[0]["is_ephemeral"] is True
    assert images[0]["local_path"] is None
    assert "raw_input" not in images[0]


@pytest.mark.asyncio
async def test_ephemeral_flag_propagates_to_ingestion_and_trace_excludes_image_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ingested = [
        {
            "image_id": "ephemeral_0",
            "url": "data:image/webp;base64,private-image-payload",
            "thumbnail_data_uri": "data:image/webp;base64,private-thumbnail",
            "width": 32,
            "height": 32,
            "size_bytes": 15,
            "is_ephemeral": True,
        }
    ]
    ingest_images = AsyncMock(return_value=ingested)
    monkeypatch.setattr(ImageIngestionService, "ingest_images", ingest_images)

    user_uuid = uuid4()
    conv_id = uuid4()
    user_repo = MagicMock()
    user_repo.get_or_create_user = AsyncMock()
    user_repo.get_user_stats = AsyncMock(return_value=UserStats(user_id=user_uuid))
    emotion_repo = MagicMock()
    emotion_repo.get_emotion_state = AsyncMock(return_value=EmotionState(user_id=user_uuid))
    conversation_repo = MagicMock()
    conversation_repo.get_or_create_conversation = AsyncMock(return_value=conv_id)
    conversation_repo.get_recent_history = AsyncMock(return_value=[])
    conversation_repo.get_latest_summary = AsyncMock(return_value=None)
    tracker = MagicMock()
    session = MagicMock()
    session.commit = AsyncMock()

    stage = InitializationStage(
        user_repo_factory=lambda _: user_repo,
        emotion_repo_factory=lambda _: emotion_repo,
        conv_repo_factory=lambda _: conversation_repo,
        pipeline_tracker=tracker,
    )
    context = ChatContext(
        session=session,
        user_id=str(user_uuid),
        user_message="analyze this",
        images=["data:image/png;base64,aGVsbG8="],
        is_ephemeral_reference=True,
    )

    result = await stage.process(context)

    ingest_images.assert_awaited_once_with(
        image_inputs=context.images,
        save_to_disk=False,
        is_ephemeral=True,
    )
    trace_data = tracker.add_step.call_args.kwargs["data"]
    assert "private-image-payload" not in str(trace_data)
    assert "private-thumbnail" not in str(trace_data)
    assert trace_data["processed_images"] == [
        {
            "image_id": "ephemeral_0",
            "width": 32,
            "height": 32,
            "size_bytes": 15,
            "is_ephemeral": True,
        }
    ]
    assert result.processed_images == ingested


@pytest.mark.asyncio
async def test_ephemeral_image_is_not_persisted_or_sent_to_visual_memory_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_uuid = uuid4()
    conv_id = uuid4()
    stats = UserStats(user_id=user_uuid)
    emotion = EmotionState(user_id=user_uuid)
    context = ChatContext(
        session=MagicMock(),
        user_id=str(user_uuid),
        user_uuid=user_uuid,
        conv_id=conv_id,
        user_message="private image",
        chisa_reply="acknowledged",
        stats=stats,
        emotion=emotion,
        processed_images=[{"image_id": "ephemeral_0", "url": "data:image/webp;base64,private"}],
        is_ephemeral_reference=True,
    )
    user_repo = MagicMock()
    user_repo.update_stats = AsyncMock()
    user_repo.apply_interaction = AsyncMock(
        return_value=UserStats(user_id=user_uuid, interaction_count=1, state_revision=1)
    )
    conversation_repo = MagicMock()
    conversation_repo.save_message = AsyncMock()
    persistence = PersistenceStage(
        user_repo_factory=lambda _: user_repo,
        conv_repo_factory=lambda _: conversation_repo,
    )

    await persistence.process(context)

    assert conversation_repo.save_message.call_args_list[0].kwargs["media_metadata"] is None

    queue = MagicMock()
    queue.enqueue = AsyncMock()
    background = BackgroundTaskStage(job_queue=queue)
    await background.process(context)

    # Only the canonical post-commit state projection is enqueued; an ephemeral
    # image never reaches the visual-memory job path.
    submissions = [call.args[1] for call in queue.enqueue.await_args_list]
    assert [item.job_type for item in submissions] == [BackgroundJobType.USER_STATE_CACHE]
