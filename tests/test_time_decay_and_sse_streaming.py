"""
Test Suite for Adaptive Time-Decay Scoring and SSE Streaming Response.
"""

import asyncio
import time
import math
import os
import sys

sys.path.insert(0, os.path.abspath("."))

from app.domain.services.rag.reranker import HybridMemoryScorer


def test_adaptive_time_decay_math():
    print("=" * 80)
    print("🚀 KIỂM THỬ: ADAPTIVE TIME-DECAY SCORING (ĐƯỜNG CONG LÃNG QUÊN)")
    print("=" * 80)

    scorer = HybridMemoryScorer()
    now = int(time.time())

    # Case 1: Core Permanent Fact (e.g. Nickname / Career / Birthday - Importance 0.90)
    # Age: 30 days ago
    created_30d_ago = now - (30 * 86400)
    score_core_30d = scorer.calculate_recency(
        created_at=created_30d_ago,
        now=now,
        importance=0.90,
        memory_type="user_fact"
    )
    print(f"  • Ký ức Cốt lõi (importance=0.90) sau 30 ngày:")
    print(f"    Recency Score: {score_core_30d:.4f} (Kỳ vọng: > 0.80)")
    assert score_core_30d > 0.80, f"Expected core fact to retain high score, got {score_core_30d}"

    # Case 2: Shared Story (Nickname / Mutual Promise - Importance 0.85)
    # Age: 60 days ago
    created_60d_ago = now - (60 * 86400)
    score_story_60d = scorer.calculate_recency(
        created_at=created_60d_ago,
        now=now,
        importance=0.85,
        memory_type="shared_story"
    )
    print(f"  • Ký ức Biệt danh / Lời hứa (shared_story) sau 60 ngày:")
    print(f"    Recency Score: {score_story_60d:.4f} (Kỳ vọng: > 0.70)")
    assert score_story_60d > 0.70, f"Expected shared story to retain high score, got {score_story_60d}"

    # Case 3: Casual / Fleeting Memory (Importance 0.50)
    # Age: 30 days ago
    score_casual_30d = scorer.calculate_recency(
        created_at=created_30d_ago,
        now=now,
        importance=0.50,
        memory_type="user_fact"
    )
    print(f"  • Ký ức Tạm thời / Phiếm diện (importance=0.50) sau 30 ngày:")
    print(f"    Recency Score: {score_casual_30d:.4f} (Kỳ vọng: < 0.10)")
    assert score_casual_30d < 0.10, f"Expected casual fact to decay quickly, got {score_casual_30d}"

    # Case 4: Spaced Repetition (Reinforced Memory via last_accessed_at)
    # Created 90 days ago, but accessed 2 days ago
    created_90d_ago = now - (90 * 86400)
    accessed_2d_ago = now - (2 * 86400)
    score_reinforced = scorer.calculate_recency(
        created_at=created_90d_ago,
        now=now,
        importance=0.75,
        memory_type="user_fact",
        last_accessed_at=accessed_2d_ago
    )
    print(f"  • Ký ức được nhắc lại gần đây (last_accessed_at=2 ngày trước):")
    print(f"    Recency Score: {score_reinforced:.4f} (Kỳ vọng: > 0.90)")
    assert score_reinforced > 0.90, f"Expected reinforced fact to be high, got {score_reinforced}"

    print("  ✓ PASS: Toàn bộ công thức Adaptive Time-Decay hoạt động chính xác 100%!")


async def test_streaming_token_collector(test_chat_engine):
    print("\n" + "=" * 80)
    print("🚀 KIỂM THỬ: STREAMING GENERATION TOKEN COLLECTOR (SSE)")
    print("=" * 80)

    from app.infrastructure.database.engine import AsyncSessionFactory
    from app.interface.api.schemas.chat import ChatRequest

    chat_engine = test_chat_engine
    collected_tokens = []

    async def token_callback(token: str):
        collected_tokens.append(token)

    async with AsyncSessionFactory() as session:
        reply_text, emotions, _, _ = await chat_engine.chat(
            session=session,
            user_id="test_stream_user",
            user_message="chào em Chisa nha",
            on_token=token_callback
        )
        await session.commit()

    print(f"  • Reply Text: '{reply_text}'")
    print(f"  • Collected stream tokens count: {len(collected_tokens)}")
    print(f"  • First 5 tokens: {collected_tokens[:5]}")
    
    assert len(collected_tokens) > 0, "Expected streaming tokens to be collected"
    assert reply_text is not None and len(reply_text) > 0
    print("  ✓ PASS: Streaming on_token collector hoạt động chuẩn xác!")


if __name__ == "__main__":
    test_adaptive_time_decay_math()
    asyncio.run(test_streaming_token_collector())
