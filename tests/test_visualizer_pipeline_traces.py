"""Regression coverage for redacted pipeline trace metadata."""

from __future__ import annotations

import json

import pytest

from app.infrastructure.logging.pipeline_tracker import pipeline_tracker
from scripts.generate_visualizer_traces import generate_10_full_pipeline_traces


@pytest.mark.asyncio
async def test_generated_pipeline_traces_keep_stage_coverage_without_raw_content() -> None:
    """SEC-03 preserves operational trace shape while removing raw evidence."""
    await generate_10_full_pipeline_traces()
    generated = pipeline_tracker.get_traces()[-10:]

    assert len(generated) == 10

    vector_trace = generated[0]
    vector_steps = [step["name"] for step in vector_trace["steps"]]
    assert {
        "initialization",
        "intent_classification",
        "lore_retrieval",
        "thinking_loop_cycle_1",
        "thinking_loop_auto_satisfy",
        "context_building",
        "llm_generation",
        "emotion_update",
    }.issubset(vector_steps)

    web_trace = generated[1]
    web_steps = [step["name"] for step in web_trace["steps"]]
    assert {"web_search", "information_alignment_check"}.issubset(web_steps)

    deep_reasoning_trace = generated[6]
    llm_step = next(
        step for step in deep_reasoning_trace["steps"] if step["name"] == "llm_generation"
    )
    assert llm_step["data"].get("reasoning_tokens", 0) > 0
    assert "reasoning_content" not in llm_step["data"]

    background_trace = generated[7]
    background_steps = [step["name"] for step in background_trace["steps"]]
    assert {"memory_extraction", "summarize_conversation_memory"}.issubset(background_steps)

    serialized = json.dumps(generated)
    assert "user_senpai_honami" not in serialized
    assert "You are Kuchiba Chisa" not in serialized
    assert "Verdant Summit" not in serialized
    assert "reasoning_content" not in serialized
