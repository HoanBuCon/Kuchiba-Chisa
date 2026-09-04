from unittest.mock import patch

import httpx
import pytest

from app.config.settings import settings
from app.domain.interfaces.llm_provider import LLMResponse, StructuredPrompt
from app.domain.services.context_builder import ContextBuilder
from app.infrastructure.llm.adapters.deepseek import DeepSeekAdapter


@pytest.mark.asyncio
@patch("httpx.AsyncClient.post")
async def test_deepseek_adapter_generate_success(mock_post):
    # Sử dụng đối tượng httpx.Response thực tế thay vì AsyncMock để tránh lỗi coroutine
    mock_response = httpx.Response(
        status_code=200,
        json={
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"response": "Hello Senpai!", "sentiment": '
                            '{"reaction": "calm_warmth", "user_stance": "neutral", '
                            '"intensity": 0.5, "variance": 0.0}}'
                        )
                    },
                    "finish_reason": "stop"
                }
            ],
            "usage": {
                "prompt_tokens": 12,
                "completion_tokens": 8
            }
        }
    )
    mock_post.return_value = mock_response
    
    # Khởi tạo adapter với AsyncClient
    adapter = DeepSeekAdapter(http_client=httpx.AsyncClient())
    
    prompt = StructuredPrompt(
        system="Test system",
        history=[],
        user_message="Hello",
        response_schema=ContextBuilder.get_response_schema(),
        retrieved_memories=[],
        retrieved_lore=[],
        rag_decisions={}
    )
    
    res = await adapter.generate(prompt)
    
    assert isinstance(res, LLMResponse)
    assert res.raw_content == (
        '{"response": "Hello Senpai!", "sentiment": {"reaction": "calm_warmth", '
        '"user_stance": "neutral", "intensity": 0.5, "variance": 0.0}}'
    )
    assert res.parsed["response"] == "Hello Senpai!"
    assert res.input_tokens == 12
    assert res.output_tokens == 8
    assert res.model == settings.DEEPSEEK_MODEL
