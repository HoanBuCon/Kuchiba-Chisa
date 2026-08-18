# -*- coding: utf-8 -*-
"""
Test Suite: Visualizer Token Breakdown & LLM Telemetry Accuracy
Verifies fine-grained token decomposition across System Prompt, Context Lore,
Memories, Search Data, History, User Message, CoT Reasoning, and Output.
"""

import os
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import asyncio
import pytest
from app.domain.interfaces.llm_provider import StructuredPrompt, LLMResponse
from app.infrastructure.logging.llm_logger import compute_token_breakdown, log_llm_transaction
from app.infrastructure.logging.pipeline_tracker import pipeline_tracker
from app.shared.utils.token_estimator import TokenEstimator

def test_token_breakdown_full_rag_and_cot():
    """Verify accurate decomposition of a full RAG prompt with CoT reasoning and memories."""
    system_prompt = (
        "You are Kuchiba Chisa, a Kuudere assistant.\n"
        "[CHISA'S CANONICAL PERSONALITY & TRAITS]\n"
        "- Thích ăn socola đen, uống trà và ngắm hoàng hôn Honami.\n\n"
        "[CONVERSATION SUMMARY]\n"
        "Senpai đã hỏi về vũ khí của Jiyan trước đó.\n\n"
        "[MEMORIES — REFERENCE DATA START]\n"
        "- Senpai thích uống trà xanh không đường\n"
        "[MEMORIES — REFERENCE DATA END]\n\n"
        "[LORE — REFERENCE DATA START]\n"
        "- Jiyan sử dụng vũ khí Broadblade mang tên Verdant Summit trong Wuthering Waves.\n"
        "- Jiyan là Tướng quân của Midnight Rangers tại Jinzhou.\n"
        "[LORE — REFERENCE DATA END]\n\n"
        "[SEARCH DATA — REFERENCE DATA START]\n"
        "Thông tin bổ sung từ internet về kỹ năng của Jiyan\n"
        "[SEARCH DATA — REFERENCE DATA END]\n\n"
        "[OUTPUT FORMAT]\n"
        "Output valid JSON matching schema."
    )
    
    history = [
        {"role": "user", "content": "Jiyan là ai vậy em?"},
        {"role": "assistant", "content": "Jiyan là Tướng quân Midnight Rangers."}
    ]
    
    user_message = "Vũ khí của anh ấy tên là gì và có mạnh không?"
    
    raw_response = (
        "<think>\n"
        "Người dùng đang hỏi về vũ khí của Jiyan. Dựa trên Lore được cung cấp, vũ khí là Verdant Summit (Broadblade).\n"
        "Cần trả lời theo phong cách Kuudere của Chisa, ngắn gọn, chu đáo.\n"
        "</think>\n"
        '{"response": "Vũ khí của Tướng quân Jiyan là thanh Broadblade mang tên Verdant Summit, rất dũng mãnh và uy lực ạ."}'
    )
    
    prompt = StructuredPrompt(
        system=system_prompt,
        history=history,
        user_message=user_message,
        response_schema={"type": "object"},
        retrieved_lore=[
            "Jiyan sử dụng vũ khí Broadblade mang tên Verdant Summit trong Wuthering Waves.",
            "Jiyan là Tướng quân của Midnight Rangers tại Jinzhou."
        ],
        retrieved_memories=["Senpai thích uống trà xanh không đường"]
    )
    
    response = LLMResponse(
        raw_content=raw_response,
        parsed={"response": "Vũ khí của Tướng quân Jiyan là thanh Broadblade mang tên Verdant Summit, rất dũng mãnh và uy lực ạ."},
        input_tokens=TokenEstimator.estimate(system_prompt) + TokenEstimator.estimate_messages(history) + TokenEstimator.estimate(user_message),
        output_tokens=TokenEstimator.estimate(raw_response),
        reasoning_content=(
            "Người dùng đang hỏi về vũ khí của Jiyan. Dựa trên Lore được cung cấp, vũ khí là Verdant Summit (Broadblade).\n"
            "Cần trả lời theo phong cách Kuudere của Chisa, ngắn gọn, chu đáo."
        ),
        model="deepseek-reasoner"
    )
    
    breakdown = compute_token_breakdown(prompt, response)
    
    print("\n[RESULT] Token Breakdown Analysis:")
    for k, v in breakdown.items():
        print(f"  • {k:25s}: {v}")
        
    assert breakdown["system_prompt"] > 0, "System prompt tokens must be > 0"
    assert breakdown["context_lore"] > 0, "Context lore tokens must be > 0"
    assert breakdown["context_memories"] > 0, "Context memories tokens must be > 0"
    assert breakdown["context_web_search"] > 0, "Web search tokens must be > 0"
    assert breakdown["conversation_summary"] > 0, "Conversation summary tokens must be > 0"
    assert breakdown["conversation_history"] > 0, "Conversation history tokens must be > 0"
    assert breakdown["user_message"] > 0, "User message tokens must be > 0"
    assert breakdown["reasoning_cot"] > 0, "CoT reasoning tokens must be > 0"
    assert breakdown["completion_output"] > 0, "Completion output tokens must be > 0"
    assert breakdown["total_tokens"] == breakdown["total_input"] + breakdown["total_output"] + breakdown["reasoning_cot"]
    
    print("\n✅ PASS: Token breakdown correctly decomposes all 8 distinct prompt components!")


@pytest.mark.asyncio
async def test_pipeline_tracker_step_integration():
    """Verify log_llm_transaction attaches token_breakdown to pipeline tracker."""
    pipeline_tracker.start_trace(user_id="test_user", message="Test message", pipeline="chat_pipeline")
    
    prompt = StructuredPrompt(
        system="System prompt for testing",
        history=[],
        user_message="Hello Chisa",
        response_schema={"type": "object"}
    )
    response = LLMResponse(
        raw_content='{"response": "Hello Senpai"}',
        parsed={"response": "Hello Senpai"},
        input_tokens=15,
        output_tokens=8,
        model="deepseek-chat"
    )
    
    await log_llm_transaction(prompt, response)
    
    trace = pipeline_tracker.end_trace()
    assert trace is not None
    
    llm_step = next((s for s in trace["steps"] if s["name"] == "llm_generation"), None)
    assert llm_step is not None, "llm_generation step must exist in trace"
    assert "token_breakdown" in llm_step["data"], "token_breakdown must be recorded in step data"
    assert llm_step["data"]["token_breakdown"]["total_tokens"] > 0
    
    print("✅ PASS: pipeline_tracker records fine-grained token_breakdown payload successfully!")

if __name__ == "__main__":
    test_token_breakdown_full_rag_and_cot()
    asyncio.run(test_pipeline_tracker_step_integration())
    print("\n🎉 ALL TOKEN BREAKDOWN VISUALIZER TESTS PASSED!")
