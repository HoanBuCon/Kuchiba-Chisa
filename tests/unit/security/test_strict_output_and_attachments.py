"""SEC-06 regressions for provider output validation and attachment sinks."""

from __future__ import annotations

import json
from typing import cast

import pytest

from app.application.security.json_schema import (
    StructuredOutputValidationError,
    validate_structured_output,
)
from app.domain.interfaces.llm_provider import BaseLLMAdapter, LLMInvalidResponseError
from app.domain.services.attachment_manifest import resolve_attachment_manifests
from app.domain.services.context_builder import ContextBuilder
from app.infrastructure.llm.adapters.deepseek import DeepSeekAdapter
from app.infrastructure.llm.adapters.gemini import GeminiAdapter
from app.infrastructure.llm.adapters.groq import GroqAdapter


def _valid_chat_output() -> dict[str, object]:
    return {
        "response": "A deterministic response.",
        "sentiment": {
            "reaction": "neutral",
            "user_stance": "neutral",
            "intensity": 0.5,
            "variance": 0.0,
        },
    }


def test_chat_schema_rejects_extra_model_attachment_url_and_invalid_enum() -> None:
    schema = ContextBuilder.get_response_schema()
    malicious_attachment = _valid_chat_output() | {
        "attached_images": ["file:///etc/passwd"],
    }
    with pytest.raises(StructuredOutputValidationError, match="undeclared"):
        validate_structured_output(malicious_attachment, schema)

    invalid_enum = _valid_chat_output()
    sentiment = cast(dict[str, object], invalid_enum["sentiment"])
    invalid_enum["sentiment"] = sentiment | {"reaction": "system_override"}
    with pytest.raises(StructuredOutputValidationError, match="allowed enum"):
        validate_structured_output(invalid_enum, schema)


def test_evidence_bound_schema_rejects_omitted_or_unapproved_citations() -> None:
    schema = ContextBuilder.get_response_schema(evidence_ids=["lore:approved"])

    with pytest.raises(StructuredOutputValidationError, match="missing required"):
        validate_structured_output(_valid_chat_output(), schema)
    with pytest.raises(StructuredOutputValidationError, match="allowed enum"):
        validate_structured_output(
            _valid_chat_output() | {"citations": ["lore:attacker-controlled"]}, schema
        )

    validated = validate_structured_output(
        _valid_chat_output() | {"citations": ["lore:approved"]}, schema
    )
    assert validated["citations"] == ["lore:approved"]


@pytest.mark.asyncio
@pytest.mark.parametrize("adapter_type", [DeepSeekAdapter, GeminiAdapter, GroqAdapter])
async def test_all_adapters_apply_strict_schema_validation(
    adapter_type: type[BaseLLMAdapter],
) -> None:
    adapter = cast(BaseLLMAdapter, adapter_type.__new__(adapter_type))
    schema = ContextBuilder.get_response_schema()

    result = await adapter.validate_response(json.dumps(_valid_chat_output()), schema)
    assert result == _valid_chat_output()

    with pytest.raises(LLMInvalidResponseError, match="undeclared"):
        await adapter.validate_response(
            json.dumps(_valid_chat_output() | {"attached_images": ["/tmp/secret"]}), schema
        )


def test_manifest_resolution_rejects_untrusted_urls_paths_and_ids() -> None:
    trusted_id = "b" * 32
    manifests = resolve_attachment_manifests(
        [
            {
                "image_id": trusted_id,
                "url": f"/static/uploads/2026/09/{trusted_id}.webp",
                "score": 0.9,
            },
            {"image_id": "invalid", "url": "/static/uploads/x.webp", "score": 0.99},
            {
                "image_id": "c" * 32,
                "url": "https://attacker.invalid/image.webp",
                "score": 0.99,
            },
            {
                "image_id": "d" * 32,
                "url": "/static/uploads/../../secrets.webp",
                "score": 0.99,
            },
        ]
    )

    assert [(item.attachment_id, item.delivery_url) for item in manifests] == [
        (trusted_id, f"/static/uploads/2026/09/{trusted_id}.webp")
    ]
