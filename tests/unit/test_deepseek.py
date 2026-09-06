import json
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


@pytest.mark.asyncio
@patch("httpx.AsyncClient.post")
async def test_deepseek_uses_forced_tool_for_grounded_output_contract(mock_post):
    arguments = (
        '{"decision":"answer","claims":[{"text":"Jinhsi is Magistrate.",'
        '"evidence_id":"lore:jinhsi","evidence_quote":'
        '"Jinhsi is Magistrate."}],"sentiment":{}}'
    )
    mock_post.return_value = httpx.Response(
        status_code=200,
        json={
            "choices": [{
                "message": {
                    "content": None,
                    "tool_calls": [{
                        "type": "function",
                        "function": {
                            "name": "submit_grounded_answer",
                            "arguments": arguments,
                        },
                    }],
                },
                "finish_reason": "tool_calls",
            }],
            "usage": {"prompt_tokens": 10, "completion_tokens": 8},
        },
    )
    adapter = DeepSeekAdapter(http_client=httpx.AsyncClient())
    schema = {
        "type": "object",
        "properties": {
            "decision": {"type": "string"},
            "claims": {"type": "array"},
            "sentiment": {"type": "object"},
        },
        "required": ["decision", "claims", "sentiment"],
        "additionalProperties": False,
    }
    prompt = StructuredPrompt(
        system="unchanged system",
        history=[],
        user_message="Who is Jinhsi?",
        response_schema=schema,
        output_contract_name="submit_grounded_answer",
        rag_decisions={"use_deep_thinking": True},
    )

    result = await adapter.generate(prompt)

    payload = mock_post.await_args.kwargs["json"]
    assert payload["tools"][0]["function"]["parameters"] == schema
    assert payload["tool_choice"]["function"]["name"] == "submit_grounded_answer"
    assert "response_format" not in payload
    assert payload["thinking"] == {"type": "disabled"}
    assert result.parsed["claims"][0]["evidence_id"] == "lore:jinhsi"


@pytest.mark.asyncio
async def test_deepseek_stream_collects_grounded_tool_arguments() -> None:
    arguments = '{"decision":"abstain","claims":[],"sentiment":{}}'

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = request.read().decode()
        assert '"tool_choice"' in payload
        event_payload = {
            "choices": [{
                "delta": {
                    "tool_calls": [{
                        "index": 0,
                        "function": {
                            "name": "submit_grounded_answer",
                            "arguments": arguments,
                        },
                    }]
                }
            }]
        }
        event = f"data: {json.dumps(event_payload)}\n\ndata: [DONE]\n\n"
        return httpx.Response(200, text=event)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = DeepSeekAdapter(http_client=client)
    prompt = StructuredPrompt(
        system="unchanged system",
        history=[],
        user_message="Who is Jinhsi?",
        response_schema={"type": "object"},
        output_contract_name="submit_grounded_answer",
    )

    chunks = [chunk async for chunk in adapter.stream(prompt)]
    await client.aclose()

    assert "".join(chunks) == arguments
