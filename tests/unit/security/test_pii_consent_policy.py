"""SAFE-02 regressions for provider PII minimization and memory consent."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call
from uuid import UUID, uuid4

import pytest

from app.application.privacy import MemoryPolicyService
from app.domain.entities.user import UserStats
from app.domain.interfaces.llm_provider import LLMResponse, StructuredPrompt
from app.domain.models.evidence import (
    Evidence,
    EvidenceAccess,
    EvidenceProvenance,
    EvidenceScore,
)
from app.domain.models.privacy import MemoryPrivacyPolicy
from app.domain.services.chat_pipeline.context import ChatContext
from app.domain.services.chat_pipeline.stages.background_task_stage import BackgroundTaskStage
from app.domain.services.chat_pipeline.stages.initialization_stage import InitializationStage
from app.domain.services.chat_pipeline.stages.provider_pii_redaction_stage import (
    ProviderPiiRedactionStage,
)
from app.domain.services.guardrails.pii_redaction import PiiRedactor
from app.domain.services.memory_extractor import MemoryExtractor, _bounded_expiry
from app.domain.services.visual_memory_ingestion import VisualMemoryIngestionWorker
from app.domain.value_objects.principal import PrincipalContext
from app.interface.api.routes import chat
from app.interface.api.schemas.chat import MemoryConsentRequest
from app.shared.utils.background_tasks import BackgroundTaskManager


def _evidence(text: str) -> Evidence:
    return Evidence(
        evidence_id="lore:trusted-1",
        kind="lore",
        text=text,
        provenance=EvidenceProvenance(
            source_id="source-1", source_type="lore", collection="world_lore"
        ),
        access=EvidenceAccess(scope="public"),
        score=EvidenceScore(final=0.9),
    )


def test_pii_redactor_masks_high_confidence_identifier_and_secret_categories() -> None:
    source = (
        "mail me@example.com, call +84 912 345 678, card 4111 1111 1111 1111, "
        "CCCD 001234567890, api_key=super-secret-token-123"
    )

    result = PiiRedactor().redact(source)

    assert "me@example.com" not in result.value
    assert "912 345 678" not in result.value
    assert "4111" not in result.value
    assert "001234567890" not in result.value
    assert "super-secret-token-123" not in result.value
    assert result.categories == {
        "email": 1,
        "phone": 1,
        "national_id": 1,
        "payment_card": 1,
        "secret": 1,
    }


@pytest.mark.asyncio
async def test_provider_prompt_is_redacted_copy_and_preserves_evidence_identity() -> None:
    original = StructuredPrompt(
        system="Dynamic context: user email is jane@example.com",
        history=[{"role": "user", "content": "card 4111 1111 1111 1111"}],
        user_message="contact +84 912 345 678",
        response_schema={"type": "object"},
        retrieved_evidence=[_evidence("source says jane@example.com")],
    )
    context = ChatContext(
        session=MagicMock(), user_id="verified", user_message="message", prompt=original
    )

    result = await ProviderPiiRedactionStage().process(context)

    assert result.prompt is not original
    assert "jane@example.com" in original.system
    provider_visible = " ".join(
        [
            result.prompt.system,
            result.prompt.user_message,
            result.prompt.history[0]["content"],
            result.prompt.retrieved_evidence[0].text,
        ]
    )
    assert "jane@example.com" not in provider_visible
    assert "4111" not in provider_visible
    assert "912 345 678" not in provider_visible
    assert result.prompt.retrieved_evidence[0].evidence_id == "lore:trusted-1"
    assert result.provider_pii_redaction_counts["email"] == 2


@pytest.mark.asyncio
async def test_memory_extractor_redacts_transcript_before_its_own_provider_call() -> None:
    llm = MagicMock()
    llm.generate = AsyncMock(return_value=LLMResponse(raw_content="{}", parsed={"facts": []}))
    extractor = MemoryExtractor(llm=llm, embedder=MagicMock(), vector_store=MagicMock())

    await extractor.extract_and_store_batch(
        user_id="verified-user",
        conversation_id="conversation-1",
        history=[],
        current_user_message="email jane@example.com",
        current_assistant_reply="call +84 912 345 678",
        retention_expires_at=100,
    )

    prompt = llm.generate.await_args.args[0]
    assert "jane@example.com" not in prompt.user_message
    assert "912 345 678" not in prompt.user_message


@pytest.mark.asyncio
async def test_visual_memory_payload_is_redacted_before_vector_persistence() -> None:
    client = MagicMock()
    client.upsert = AsyncMock()
    vector_store = MagicMock(_client=client)
    embedder = MagicMock()
    embedder.embed_text = AsyncMock(return_value=[0.1, 0.2])
    worker = VisualMemoryIngestionWorker(vector_store=vector_store, embedder=embedder)

    count = await worker.ingest_image_memories(
        user_id="verified-user",
        user_message="email jane@example.com",
        chisa_reply="phone +84 912 345 678",
        processed_images=[{"image_id": "image-1", "url": "opaque://image-1"}],
        retention_expires_at=100,
    )

    payload = client.upsert.await_args.kwargs["points"][0].payload
    assert count == 1
    assert "jane@example.com" not in payload["visual_caption"]
    assert "912 345 678" not in payload["chisa_comment_hint"]
    assert payload["expires_at"] == 100


@pytest.mark.asyncio
async def test_long_term_memory_is_default_deny_without_verified_consent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = ChatContext(
        session=MagicMock(),
        user_id="verified-user",
        user_uuid=uuid4(),
        conv_id=uuid4(),
        user_message="remember this",
        chisa_reply="acknowledged",
        stats=UserStats(user_id=uuid4(), interaction_count=30),
        processed_images=[{"image_id": "permanent-image"}],
    )
    spawn = MagicMock()
    monkeypatch.setattr(BackgroundTaskManager, "spawn", spawn)
    stage = BackgroundTaskStage(
        memory_extractor=MagicMock(),
        unified_auto_summarize_callback=AsyncMock(),
        topic_summarizer=MagicMock(),
    )

    await stage.process(context)

    spawn.assert_not_called()


@pytest.mark.asyncio
async def test_image_is_ephemeral_when_no_memory_consent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid4()
    processed = [{"image_id": "ephemeral-0", "is_ephemeral": True}]
    ingest = AsyncMock(return_value=processed)
    monkeypatch.setattr(
        "app.domain.services.image_ingestion.ImageIngestionService.ingest_images", ingest
    )
    user_repo = MagicMock()
    user_repo.get_or_create_user = AsyncMock()
    user_repo.get_user_stats = AsyncMock(return_value=UserStats(user_id=user_id))
    emotion_repo = MagicMock()
    emotion_repo.get_emotion_state = AsyncMock(return_value=MagicMock())
    conversation_repo = MagicMock()
    conversation_repo.get_or_create_conversation = AsyncMock(return_value=uuid4())
    conversation_repo.get_recent_history = AsyncMock(return_value=[])
    conversation_repo.get_latest_summary = AsyncMock(return_value=None)
    privacy_repo = MagicMock()
    privacy_repo.get_memory_policy = AsyncMock(return_value=MemoryPrivacyPolicy())
    session = MagicMock()
    session.commit = AsyncMock()
    context = ChatContext(
        session=session,
        user_id=str(user_id),
        user_message="analyze this",
        images=["data:image/png;base64,aGVsbG8="],
    )
    stage = InitializationStage(
        user_repo_factory=lambda _: user_repo,
        emotion_repo_factory=lambda _: emotion_repo,
        conv_repo_factory=lambda _: conversation_repo,
        privacy_repo_factory=lambda _: privacy_repo,
    )

    result = await stage.process(context)

    ingest.assert_awaited_once_with(
        image_inputs=context.images, save_to_disk=False, is_ephemeral=True
    )
    assert result.is_ephemeral_reference is True


@pytest.mark.asyncio
async def test_consented_policy_spawns_bounded_memory_extraction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = MemoryPrivacyPolicy(
        long_term_memory_enabled=True,
        retention_days=30,
        consented_at=datetime.now(UTC),
    )
    context = ChatContext(
        session=MagicMock(),
        user_id="verified-user",
        user_uuid=uuid4(),
        conv_id=uuid4(),
        user_message="remember this",
        chisa_reply="acknowledged",
        stats=UserStats(user_id=uuid4(), interaction_count=3),
        memory_privacy_policy=policy,
    )
    extractor = MagicMock()
    extractor.extract_and_store_batch = AsyncMock()
    extractor.vector_store = MagicMock()
    extractor.embedder = MagicMock()
    spawned: list[str] = []

    def capture(coroutine, *, name: str):
        coroutine.close()
        spawned.append(name)
        return MagicMock()

    monkeypatch.setattr(BackgroundTaskManager, "spawn", capture)
    stage = BackgroundTaskStage(
        memory_extractor=extractor,
        unified_auto_summarize_callback=AsyncMock(),
    )

    await stage.process(context)

    assert spawned == ["memory_extract_batch:verified-user"]
    assert _bounded_expiry(None, 123) == 123
    assert _bounded_expiry(456, 123) == 123


@pytest.mark.asyncio
async def test_withdrawal_deletes_only_the_verified_users_active_text_memory() -> None:
    user_id = uuid4()
    user_repo = MagicMock()
    user_repo.get_or_create_user = AsyncMock()
    privacy_repo = MagicMock()
    privacy_repo.set_memory_policy = AsyncMock(return_value=MemoryPrivacyPolicy())
    conversation_repo = MagicMock()
    conversation_repo.get_image_ids_for_user = AsyncMock(return_value=["image-1"])
    vector_store = MagicMock()
    vector_store.delete_by_user = AsyncMock()
    image_storage = MagicMock()
    image_storage.delete_image = AsyncMock()
    service = MemoryPolicyService(
        user_repo_factory=lambda _: user_repo,
        conversation_repo_factory=lambda _: conversation_repo,
        privacy_repo_factory=lambda _: privacy_repo,
        vector_store=vector_store,
        image_storage=image_storage,
    )

    policy = await service.update(
        MagicMock(), user_id, enabled=False, retention_days=30
    )

    assert policy.allows_long_term_memory is False
    privacy_repo.set_memory_policy.assert_awaited_once()
    assert privacy_repo.set_memory_policy.await_args.kwargs["retention_days"] is None
    assert vector_store.delete_by_user.await_args_list == [
        call("memories", str(user_id)),
        call("image_memories", str(user_id)),
        call("guild_memories", str(user_id)),
    ]
    image_storage.delete_image.assert_awaited_once_with("image-1")


@pytest.mark.asyncio
async def test_memory_consent_route_uses_verified_principal_not_client_identity() -> None:
    principal = PrincipalContext(
        subject_id="verified-user",
        tenant_id=None,
        channel_id=None,
        source="web",
        kind="user",
        scopes=frozenset({"chat:write"}),
    )
    policy = MemoryPrivacyPolicy(long_term_memory_enabled=True, retention_days=30)
    service = SimpleNamespace(update=AsyncMock(return_value=policy))
    session = SimpleNamespace(commit=AsyncMock())

    response = await chat.set_memory_consent(
        request=MemoryConsentRequest(enabled=True, retention_days=30),
        principal=principal,
        session=session,
        memory_policy_service=service,
    )

    asserted_user_id = service.update.await_args.args[1]
    assert isinstance(asserted_user_id, UUID)
    assert response.enabled is True
    session.commit.assert_awaited_once()
