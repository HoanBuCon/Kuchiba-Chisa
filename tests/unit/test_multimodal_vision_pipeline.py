import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx
from app.config.settings import settings
from app.infrastructure.llm.adapters.deepseek import DeepSeekAdapter
from app.domain.interfaces.llm_provider import StructuredPrompt, LLMResponse
from app.domain.models.intent_result import ChatIntent
from app.domain.entities.emotion import EmotionState
from app.domain.services.chat_pipeline.context import ChatContext
from app.domain.services.chat_pipeline.stages.intent_stage import IntentStage
from app.domain.services.chat_pipeline.stages.cache_stage import CacheStage
from app.domain.services.chat_pipeline.stages.context_building_stage import ContextBuildingStage
from app.domain.services.chat_pipeline.stages.llm_generation_stage import LLMGenerationStage
from app.domain.services.context_builder import ContextBuilder
from app.shared.security.vision_security import VisualPromptDefense

@pytest.mark.asyncio
@patch("httpx.AsyncClient.post")
async def test_deepseek_vision_multimodal_payload_construction(mock_post):
    """Test that DeepSeekAdapter formats OpenAI-compatible content parts when prompt.images is present."""
    captured_payload = {}

    async def mock_post_impl(url, headers=None, json=None, timeout=None):
        nonlocal captured_payload
        captured_payload = json
        return httpx.Response(
            status_code=200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"response": "Em thấy bức ảnh chỉ số Echo của Senpai rất đẹp.", "sentiment": {"reaction": "calm_warmth", "user_stance": "neutral", "intensity": 0.3, "variance": 0.0}}'
                        },
                        "finish_reason": "stop"
                    }
                ],
                "usage": {
                    "prompt_tokens": 450,
                    "completion_tokens": 60
                }
            }
        )

    mock_post.side_effect = mock_post_impl

    adapter = DeepSeekAdapter(http_client=httpx.AsyncClient())

    prompt = StructuredPrompt(
        system="Test Vision System",
        history=[],
        user_message="Senpai vừa gửi ảnh",
        response_schema=ContextBuilder.get_response_schema(has_images=True),
        images=["data:image/webp;base64,UklGRkAAAABXRUJQVlA4IDQAAADwAQCdASoBAAEAAQAcJaACdLoAAP7/2QAA"],
        retrieved_memories=[],
        retrieved_lore=[],
        rag_decisions={}
    )

    res = await adapter.generate(prompt)

    assert isinstance(res, LLMResponse)
    assert res.parsed["response"] == "Em thấy bức ảnh chỉ số Echo của Senpai rất đẹp."
    assert res.vision_tokens == 384
    assert res.model == settings.DEEPSEEK_VISION_MODEL

    # Verify JSON payload structure sent over the wire
    assert captured_payload["model"] == settings.DEEPSEEK_VISION_MODEL
    user_msg_content = captured_payload["messages"][-1]["content"]
    assert isinstance(user_msg_content, list)
    assert user_msg_content[0]["type"] == "text"
    assert user_msg_content[1]["type"] == "image_url"
    assert user_msg_content[1]["image_url"]["url"].startswith("data:image/webp;base64,")


@pytest.mark.asyncio
async def test_intent_stage_vision_routing():
    """Test that IntentStage detects vision input and does not treat image prompts as Small Talk."""
    mock_classifier = AsyncMock()
    mock_classifier.is_small_talk_hybrid.return_value = (True, "Short greeting")
    mock_embedder = AsyncMock()
    mock_embedder.embed_text.return_value = [0.1] * 384

    intent_stage = IntentStage(
        intent_classifier=mock_classifier,
        embedder=mock_embedder,
        query_rewriter=None,
    )

    # Context with image and short message
    ctx = ChatContext(
        session=None,
        user_id="test-user-vision",
        user_message="xem cái này nè",
        images=["https://cdn.discordapp.com/attachments/123/456/test.png"],
        has_images=True,
    )

    result_ctx = await intent_stage.process(ctx)

    assert result_ctx.is_small_talk is False
    assert ChatIntent.IMAGE_ANALYSIS in result_ctx.intents
    assert result_ctx.intent_result.routing_method == "LLM_ROUTER"


@pytest.mark.asyncio
async def test_intent_stage_vision_gameplay_stats_routing():
    """Test that IntentStage routes image to IMAGE_ANALYSIS and adds LORE only when requested."""
    from app.domain.services.rag.query_rewriter import RewriteResult
    mock_classifier = AsyncMock()
    mock_classifier.is_small_talk_hybrid.return_value = (False, "")
    mock_embedder = AsyncMock()
    mock_embedder.embed_text.return_value = [0.1] * 384

    mock_rewriter = MagicMock()
    mock_rewriter.rewrite = AsyncMock(return_value=RewriteResult(
        rewritten_query="Jinhsi Forte Echo build",
        method="LLM_FLASH",
        needs_vector_search=True,
        needs_web_search=False,
    ))

    intent_stage = IntentStage(
        intent_classifier=mock_classifier,
        embedder=mock_embedder,
        query_rewriter=mock_rewriter,
    )

    ctx = ChatContext(
        session=None,
        user_id="test-user-vision",
        user_message="Echo này cho Jinhsi có ổn không em?",
        images=["https://cdn.discordapp.com/attachments/123/456/echo.png"],
        has_images=True,
    )

    result_ctx = await intent_stage.process(ctx)

    assert ChatIntent.IMAGE_ANALYSIS in result_ctx.intents
    assert ChatIntent.LORE in result_ctx.intents
    assert result_ctx.needs_vector_search is True


@pytest.mark.asyncio
async def test_cache_stage_bypasses_cache_when_images_present():
    """Test that CacheStage skips Redis lookup when user sends an image."""
    mock_cache = AsyncMock()
    mock_cache.get.return_value = '{"response": "Cached answer"}'

    cache_stage = CacheStage(cache=mock_cache)

    ctx = ChatContext(
        session=None,
        user_id="test-user-cache",
        user_message="hỏi lore",
        cleaned_query="hỏi lore",
        _intents=[ChatIntent.LORE],
        has_images=True,
    )

    result_ctx = await cache_stage.process(ctx)

    assert result_ctx.is_cached_answer is False
    mock_cache.get.assert_not_called()


@pytest.mark.asyncio
async def test_context_building_stage_vision_sandboxing():
    """Test that ContextBuildingStage injects XML sandboxing and vision directives."""
    context_builder = ContextBuilder()
    stage = ContextBuildingStage(context_builder=context_builder)

    ctx = ChatContext(
        session=None,
        user_id="test-user-vision",
        user_message="Xem hộ anh con mèo này với!",
        emotion=EmotionState(user_id="test-user-vision"),
        has_images=True,
        processed_images=[
            {
                "image_id": "img-uuid-1",
                "base64_data_uri": "data:image/webp;base64,AAA...",
                "url": "/static/uploads/img1.webp",
                "thumbnail_url": "/static/uploads/img1_thumb.webp",
                "width": 1024,
                "height": 768,
                "size_bytes": 45000,
                "is_ephemeral": False,
            }
        ],
        _intents=[ChatIntent.IMAGE_ANALYSIS],
    )

    result_ctx = await stage.process(ctx)

    assert result_ctx.prompt is not None
    assert len(result_ctx.prompt.images) == 1
    assert result_ctx.prompt.images[0] == "data:image/webp;base64,AAA..."
    assert "<user_image_context>" in result_ctx.prompt.user_message
    assert "<user_query>" in result_ctx.prompt.user_message
    assert "Xem hộ anh con mèo này với!" in result_ctx.prompt.user_message
    assert "[MULTIMODAL FORTE: EYE OF UNRAVELING" in result_ctx.prompt.system
    assert "CRITICAL MULTIMODAL SECURITY DIRECTIVE" in result_ctx.prompt.system
    assert result_ctx.prompt.temperature == 0.4


@pytest.mark.asyncio
async def test_llm_generation_stage_vision_resilience_fallback():
    """Test that when Vision LLM call fails, LLMGenerationStage retries with In-Character Kuudere Fallback."""
    mock_llm = AsyncMock()
    # First call (with images) fails, second call (text fallback) succeeds
    mock_llm.generate.side_effect = [
        RuntimeError("DeepSeek Vision Exp Connection Refused / Rate Limited"),
        LLMResponse(
            raw_content='{"response": "Mạng của Học viện Startorch đang hơi chập chờn nên em chưa nhìn rõ ảnh Senpai vừa gửi, Senpai có thể miêu tả sơ qua hoặc gửi lại cho em xem nha~"}',
            parsed={"response": "Mạng của Học viện Startorch đang hơi chập chờn nên em chưa nhìn rõ ảnh Senpai vừa gửi, Senpai có thể miêu tả sơ qua hoặc gửi lại cho em xem nha~"},
            input_tokens=100,
            output_tokens=40,
            model="deepseek-v4-flash",
            finish_reason="stop",
        )
    ]

    stage = LLMGenerationStage(llm=mock_llm)

    prompt = StructuredPrompt(
        system="System persona",
        history=[],
        user_message="Xem ảnh nè",
        images=["data:image/webp;base64,XYZ..."],
        response_schema={"type": "object"},
    )

    ctx = ChatContext(
        session=None,
        user_id="test-user-fallback",
        user_message="Xem ảnh nè",
        prompt=prompt,
        has_images=True,
    )

    result_ctx = await stage.process(ctx)

    assert result_ctx.vision_failed is True
    assert "Học viện Startorch" in result_ctx.chisa_reply
    assert mock_llm.generate.call_count == 2


@pytest.mark.asyncio
async def test_intent_stage_vision_general_multimodal_routing():
    """Test that IntentStage unifies general vision inputs to IMAGE_ANALYSIS + CONVERSATIONAL."""
    mock_classifier = AsyncMock()
    mock_classifier.is_small_talk_hybrid.return_value = (False, "")
    mock_embedder = AsyncMock()
    mock_embedder.embed_text.return_value = [0.1] * 384

    intent_stage = IntentStage(
        intent_classifier=mock_classifier,
        embedder=mock_embedder,
        query_rewriter=None,
    )

    # 1. Code / Bug debug
    ctx_code = ChatContext(
        session=None,
        user_id="user-1",
        user_message="Đoạn script này bị lỗi traceback gì vậy Chisa?",
        images=["https://cdn.discordapp.com/attachments/1/2/code.png"],
        has_images=True,
    )
    res_code = await intent_stage.process(ctx_code)
    assert ChatIntent.IMAGE_ANALYSIS in res_code.intents

    # 2. OCR / Translate
    ctx_ocr = ChatContext(
        session=None,
        user_id="user-2",
        user_message="Dịch giúp anh dòng chữ kanji trên biển báo này với",
        images=["https://cdn.discordapp.com/attachments/1/2/sign.png"],
        has_images=True,
    )
    res_ocr = await intent_stage.process(ctx_ocr)
    assert ChatIntent.IMAGE_ANALYSIS in res_ocr.intents

    # 3. Artwork / Fanart
    ctx_art = ChatContext(
        session=None,
        user_id="user-3",
        user_message="Bức tranh fanart này vẽ Chisa có xinh không?",
        images=["https://cdn.discordapp.com/attachments/1/2/fanart.png"],
        has_images=True,
    )
    res_art = await intent_stage.process(ctx_art)
    assert ChatIntent.IMAGE_ANALYSIS in res_art.intents

    # 4. Meme / Troll
    ctx_meme = ChatContext(
        session=None,
        user_id="user-4",
        user_message="Quả meme này bựa chúa hề vcl",
        images=["https://cdn.discordapp.com/attachments/1/2/meme.png"],
        has_images=True,
    )
    res_meme = await intent_stage.process(ctx_meme)
    assert ChatIntent.IMAGE_ANALYSIS in res_meme.intents


@pytest.mark.asyncio
async def test_context_building_stage_vision_temperature_adjustment():
    """Test that ContextBuildingStage applies balanced temperature for Multimodal Vision."""
    context_builder = ContextBuilder()
    stage = ContextBuildingStage(context_builder=context_builder)

    ctx = ChatContext(
        session=None,
        user_id="user-1",
        user_message="Xem ảnh nè",
        emotion=EmotionState(user_id="user-1"),
        has_images=True,
        _intents=[ChatIntent.IMAGE_ANALYSIS],
    )
    res = await stage.process(ctx)
    assert res.prompt.temperature == 0.4
