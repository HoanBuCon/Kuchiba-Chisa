"""
Unit tests for Text-to-Image Reverse Memory Retrieval & Delivery.
Location: tests/unit/test_text_to_image_memory_retrieval.py
"""

import pytest
import time
from unittest.mock import AsyncMock, MagicMock, patch

from app.domain.entities.image_memory import ImageMemoryPayload, RetrievedImageMemory
from app.domain.entities.emotion import EmotionState
from app.domain.models.intent_result import ChatIntent, IntentResult
from app.domain.services.visual_memory_ingestion import VisualMemoryIngestionWorker
from app.domain.services.rag.retriever_image_memory import ImageMemoryRetriever
from app.domain.services.context_builder import ContextBuilder
from app.domain.services.chat_pipeline.context import ChatContext
from app.domain.services.chat_pipeline.stages.intent_stage import IntentStage
from app.domain.services.chat_pipeline.stages.llm_generation_stage import LLMGenerationStage
from app.domain.interfaces.llm_provider import LLMResponse, StructuredPrompt


@pytest.mark.asyncio
async def test_image_memory_entity_and_ingestion_worker():
    """Kiểm tra schema ImageMemoryPayload và VisualMemoryIngestionWorker trích xuất tags, sinh vector và upsert Qdrant."""
    mock_vector_store = MagicMock()
    mock_client = AsyncMock()
    mock_vector_store._client = mock_client
    
    mock_embedder = AsyncMock()
    mock_embedder.embed_text.return_value = [0.1] * 384

    worker = VisualMemoryIngestionWorker(vector_store=mock_vector_store, embedder=mock_embedder)

    processed_images = [
        {
            "image_id": "img-uuid-12345",
            "url": "/static/uploads/2026/08/beach_trip.webp",
            "thumbnail_url": "/static/uploads/2026/08/beach_trip_thumb.webp",
            "local_path": "app/static/uploads/2026/08/beach_trip.webp",
            "width": 1280,
            "height": 720,
            "size_bytes": 102400,
            "is_ephemeral": False,
        }
    ]

    ingested = await worker.ingest_image_memories(
        user_id="user_senpai_1",
        user_message="Ảnh anh và em đi du lịch biển hôm qua nè",
        chisa_reply="Biển hoàng hôn đẹp quá Senpai ơi, em đã lưu lại vào ký ức rồi ạ.",
        processed_images=processed_images,
        conversation_id="conv-1",
        guild_id="guild-1",
        channel_id="chan-1",
        is_ephemeral=False,
    )

    assert ingested == 1
    mock_embedder.embed_text.assert_called_once()
    assert "passage: " in mock_embedder.embed_text.call_args[1].get("prefix", "")
    mock_client.upsert.assert_called_once()
    upsert_args = mock_client.upsert.call_args[1]
    assert upsert_args["collection_name"] == "image_memories"
    points = upsert_args["points"]
    assert len(points) == 1
    payload = points[0].payload
    assert payload["image_id"] == "img-uuid-12345"
    assert payload["user_id"] == "user_senpai_1"
    assert "du lịch" in payload["tags"] or "kỷ niệm" in payload["tags"]


@pytest.mark.asyncio
async def test_intent_classification_image_retrieval_anchors():
    """Kiểm tra IntentStage nhận diện chính xác ý định RETRIEVE_PAST_IMAGE từ các câu nói tiếng Việt."""
    mock_classifier = AsyncMock()
    mock_classifier.is_small_talk_hybrid.return_value = (False, "Not small talk")
    mock_classifier.detect_persona_trait.return_value = None

    mock_embedder = AsyncMock()
    mock_embedder.embed_text.return_value = [0.05] * 384

    stage = IntentStage(
        intent_classifier=mock_classifier,
        embedder=mock_embedder,
        query_rewriter=None,
        conv_repo_factory=None,
        pipeline_tracker=None,
    )

    test_queries = [
        "Gửi lại cho anh ảnh em và anh đi du lịch hồi trước đi",
        "Cho anh xem lại cái ảnh con mèo xám hôm nọ",
        "Tìm lại ảnh cũ hôm bữa giúp anh nhé Chisa",
        "Cho anh xin lại cái ảnh lúc trước",
    ]

    for q in test_queries:
        ctx = ChatContext(session=MagicMock(), user_id="user_1", user_message=q)
        res_ctx = await stage.process(ctx)
        assert res_ctx.needs_image_retrieval is True
        assert ChatIntent.RETRIEVE_PAST_IMAGE in res_ctx.intents
        assert res_ctx.needs_vector_search is True


@pytest.mark.asyncio
async def test_image_memory_retriever_dm_privacy_isolation():
    """Kiểm tra ImageMemoryRetriever áp dụng bộ lọc user_id tuyệt đối trong tin nhắn riêng (DM)."""
    mock_vector_store = MagicMock()
    mock_client = AsyncMock()
    mock_vector_store._client = mock_client

    mock_hit = MagicMock()
    mock_hit.id = "point-1"
    mock_hit.score = 0.85
    mock_hit.payload = {
        "image_id": "img-abc-123",
        "url": "/static/uploads/2026/08/trip.webp",
        "thumbnail_url": "/static/uploads/2026/08/trip_thumb.webp",
        "visual_caption": "Bức ảnh đi du lịch Đà Lạt cùng Senpai",
        "tags": ["du lịch", "kỷ niệm"],
        "user_id": "user_senpai_1",
        "guild_id": None,
        "created_at": int(time.time()),
    }
    mock_client.search.return_value = [mock_hit]

    retriever = ImageMemoryRetriever(vector_store=mock_vector_store)

    results = await retriever.retrieve_image_memories(
        query_vector=[0.1] * 384,
        user_id="user_senpai_1",
        guild_id=None,
        is_community=False,
        score_threshold=0.68,
    )

    assert len(results) == 1
    assert isinstance(results[0], RetrievedImageMemory)
    assert results[0].url == "/static/uploads/2026/08/trip.webp"
    assert results[0].score == 0.85

    # Check search filter passed to Qdrant
    search_kwargs = mock_client.search.call_args[1]
    filter_obj = search_kwargs["query_filter"]
    must_conds = filter_obj.must
    assert any(c.key == "user_id" and c.match.value == "user_senpai_1" for c in must_conds)


@pytest.mark.asyncio
async def test_image_memory_retriever_score_threshold_filtering():
    """Kiểm tra ImageMemoryRetriever chỉ trả về ảnh có score >= score_threshold."""
    mock_vector_store = MagicMock()
    mock_client = AsyncMock()
    mock_vector_store._client = mock_client

    # Qdrant server returns empty if threshold is not met
    mock_client.search.return_value = []

    retriever = ImageMemoryRetriever(vector_store=mock_vector_store)

    results = await retriever.retrieve_image_memories(
        query_vector=[0.1] * 384,
        user_id="user_senpai_1",
        score_threshold=0.68,
    )

    assert len(results) == 0


def test_context_builder_injects_retrieved_images_section():
    """Kiểm tra ContextBuilder đóng gói section [KÝ ỨC HÌNH ẢNH TÌM THẤY TRONG KHO] và RESPONSE_SCHEMA attached_images."""
    builder = ContextBuilder()
    emotion = EmotionState(user_id="user_1")

    retrieved_images = [
        {
            "image_id": "img-001",
            "url": "/static/uploads/2026/08/cat.webp",
            "visual_caption": "Bức ảnh chú mèo xám đang ngủ ngon trên bàn học",
            "tags": ["thú cưng", "mèo"],
            "score": 0.88,
        }
    ]

    result = builder.build(
        emotion=emotion,
        attachment_bonus=0.0,
        memories=[],
        lore=[],
        history=[],
        user_message="Gửi lại ảnh con mèo cho anh xem với",
        intent_name="RETRIEVE_PAST_IMAGE",
        retrieved_images=retrieved_images,
    )

    system_prompt = result.prompt.system
    assert "[KÝ ỨC HÌNH ẢNH TÌM THẤY TRONG KHO (RETRIEVED IMAGE MEMORY)]" in system_prompt
    assert "/static/uploads/2026/08/cat.webp" in system_prompt
    assert "Bức ảnh chú mèo xám đang ngủ ngon" in system_prompt
    assert "attached_images" in result.prompt.response_schema["properties"]


@pytest.mark.asyncio
async def test_llm_generation_stage_extracts_and_fallbacks_attached_images():
    """Kiểm tra LLMGenerationStage trích xuất attached_images và fallback an toàn khi LLM quên điền field."""
    mock_llm = AsyncMock()
    # Mock LLM output that omitted attached_images but retrieved_images had a high score match
    mock_llm.generate.return_value = LLMResponse(
        raw_content='{"response": "Đây là ảnh con mèo xám hôm nọ em chụp cho Senpai nè~", "sentiment": {"reaction": "calm_warmth", "user_stance": "loving", "intensity": 0.7, "variance": 0.2}}',
        parsed={
            "response": "Đây là ảnh con mèo xám hôm nọ em chụp cho Senpai nè~",
            "sentiment": {
                "reaction": "calm_warmth",
                "user_stance": "loving",
                "intensity": 0.7,
                "variance": 0.2
            }
        },
        input_tokens=100,
        output_tokens=50,
        model="deepseek-chat",
    )

    stage = LLMGenerationStage(llm=mock_llm)

    ctx = ChatContext(session=MagicMock(), user_id="user_1", user_message="Cho anh xem lại ảnh con mèo")
    ctx.prompt = StructuredPrompt(system="system", history=[], user_message="Cho anh xem lại ảnh con mèo", response_schema={"type": "object"})
    ctx.retrieved_images = [
        {
            "image_id": "img-cat-1",
            "url": "/static/uploads/2026/08/cat.webp",
            "visual_caption": "Bức ảnh con mèo xám",
            "score": 0.89,
        }
    ]

    res_ctx = await stage.process(ctx)

    assert res_ctx.chisa_reply == "Đây là ảnh con mèo xám hôm nọ em chụp cho Senpai nè~"
    # Fallback auto-populates top retrieved image url
    assert res_ctx.attached_images == ["/static/uploads/2026/08/cat.webp"]


@pytest.mark.asyncio
async def test_llm_router_semantic_image_retrieval_fallback():
    """Kiểm tra LLM Router nhận diện yêu cầu truy hồi ảnh khi người dùng dùng câu không có từ khóa anchor."""
    from app.domain.services.rag.query_rewriter import QueryRewriter, RewriteResult

    mock_rewriter = MagicMock()
    mock_rewriter.rewrite = AsyncMock(return_value=RewriteResult(
        rewritten_query="bức ảnh bờ biển chụp cùng Senpai",
        method="LLM_FLASH",
        needs_vector_search=True,
        needs_web_search=False,
        needs_image_retrieval=True,
    ))

    mock_embedder = AsyncMock()
    mock_embedder.embed_text.return_value = [0.05] * 384
    mock_classifier = AsyncMock()
    mock_classifier.is_small_talk_hybrid.return_value = (False, "Not small talk")
    mock_classifier.detect_persona_trait.return_value = None

    stage = IntentStage(
        intent_classifier=mock_classifier,
        embedder=mock_embedder,
        query_rewriter=mock_rewriter,
    )

    ctx = ChatContext(
        session=MagicMock(),
        user_id="user_123",
        user_message="quăng lại cho anh cái tấm hình chụp ở biển bữa nọ",
        has_images=False,
    )

    res_ctx = await stage.process(ctx)

    assert ChatIntent.RETRIEVE_PAST_IMAGE in res_ctx.intents
    assert res_ctx.needs_image_retrieval is True
    assert res_ctx.needs_vector_search is True


@pytest.mark.asyncio
async def test_llm_router_semantic_vision_lore_intent_fallback():
    """Kiểm tra LLM Router nhận diện cần tra cứu Lore Game khi người dùng gửi ảnh."""
    from app.domain.services.rag.query_rewriter import QueryRewriter, RewriteResult

    mock_rewriter = MagicMock()
    mock_rewriter.rewrite = AsyncMock(return_value=RewriteResult(
        rewritten_query="chỉ số trang bị Echo",
        method="LLM_FLASH",
        needs_vector_search=True,
        needs_web_search=False,
        needs_image_retrieval=False,
    ))

    mock_embedder = AsyncMock()
    mock_embedder.embed_text.return_value = [0.05] * 384
    mock_classifier = AsyncMock()
    mock_classifier.is_small_talk_hybrid.return_value = (False, "Not small talk")
    mock_classifier.detect_persona_trait.return_value = None

    stage = IntentStage(
        intent_classifier=mock_classifier,
        embedder=mock_embedder,
        query_rewriter=mock_rewriter,
    )

    ctx = ChatContext(
        session=MagicMock(),
        user_id="user_123",
        user_message="coi giúp anh coi thế nào",
        has_images=True,
        processed_images=[{"url": "http://example.com/item.webp"}]
    )

    res_ctx = await stage.process(ctx)

    assert ChatIntent.IMAGE_ANALYSIS in res_ctx.intents
    assert res_ctx.needs_vector_search is True


@pytest.mark.asyncio
async def test_hybrid_image_input_and_image_retrieval_scenario():
    """Kiểm tra kịch bản 3: Người dùng vừa gửi ảnh mới vừa yêu cầu tìm lại/so sánh với ảnh cũ trong kho."""
    from app.domain.services.rag.query_rewriter import QueryRewriter, RewriteResult

    mock_rewriter = MagicMock()
    mock_rewriter.rewrite = AsyncMock(return_value=RewriteResult(
        rewritten_query="ảnh con mèo hôm trước",
        method="LLM_FLASH",
        needs_vector_search=True,
        needs_web_search=False,
        needs_image_retrieval=True,
    ))

    mock_embedder = AsyncMock()
    mock_embedder.embed_text.return_value = [0.05] * 384
    mock_classifier = AsyncMock()
    mock_classifier.is_small_talk_hybrid.return_value = (False, "Not small talk")
    mock_classifier.detect_persona_trait.return_value = None

    stage = IntentStage(
        intent_classifier=mock_classifier,
        embedder=mock_embedder,
        query_rewriter=mock_rewriter,
    )

    ctx = ChatContext(
        session=MagicMock(),
        user_id="user_123",
        user_message="Con mèo mới này với con mèo trong bức ảnh hôm nọ con nào xinh hơn em? Gửi lại ảnh cũ cho anh xem",
        has_images=True,
        processed_images=[{"url": "http://example.com/new_cat.webp"}]
    )

    res_ctx = await stage.process(ctx)

    # Đảm bảo được kích hoạt cả 2 ý định: Phân tích ảnh mới & Truy hồi ảnh cũ
    assert ChatIntent.IMAGE_ANALYSIS in res_ctx.intents
    assert ChatIntent.RETRIEVE_PAST_IMAGE in res_ctx.intents
    assert res_ctx.needs_image_retrieval is True
    assert res_ctx.needs_vector_search is True
