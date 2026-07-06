import pytest
from unittest.mock import AsyncMock, patch
import httpx
from app.config.settings import settings
from app.infrastructure.llm.adapters.deepseek import DeepSeekAdapter
from app.infrastructure.llm.adapters.base import StructuredPrompt, LLMResponse

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
                        "content": '{"response": "Hello Senpai!", "user_sentiment": {"is_positive": true}, "chisa_sentiment": {"is_happy": true}}'
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
    
    # Khởi tạo adapter
    adapter = DeepSeekAdapter()
    
    prompt = StructuredPrompt(
        system="Test system",
        history=[],
        user_message="Hello",
        response_schema={"type": "object"},
        retrieved_memories=[],
        retrieved_lore=[],
        rag_decisions={}
    )
    
    res = await adapter.generate(prompt)
    
    assert isinstance(res, LLMResponse)
    assert res.raw_content == '{"response": "Hello Senpai!", "user_sentiment": {"is_positive": true}, "chisa_sentiment": {"is_happy": true}}'
    assert res.parsed["response"] == "Hello Senpai!"
    assert res.input_tokens == 12
    assert res.output_tokens == 8
    assert res.model == settings.DEEPSEEK_MODEL
