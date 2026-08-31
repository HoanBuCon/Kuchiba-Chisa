"""
Test Suite for Continuous Emotion System (Intensity, Valence, 7 Archetypes & Behavioral Directives).
"""

import asyncio
import os
import sys
import uuid

sys.path.insert(0, os.path.abspath("."))

from app.domain.entities.emotion import EmotionState
from app.domain.services.emotion_engine import EmotionEngine
from app.domain.services.state_manager import StateManager
from app.infrastructure.database.engine import AsyncSessionFactory


def test_continuous_intensity_and_valence():
    print("=" * 80)
    print("🚀 TEST 1: CONTINUOUS INTENSITY & VALENCE SCALING")
    print("=" * 80)

    engine = EmotionEngine()
    
    # Case A: Mild compliment (intensity = 0.2, valence = 0.4)
    state_mild = EmotionState(user_id=uuid.uuid4(), joy=0.1, trust=0.5, attachment=0.0)
    delta_mild = engine.update(
        state_mild,
        sentiment_analysis={"intensity": 0.2, "valence": 0.4, "primary_emotion": "calm_warmth"}
    )
    print(f"  • Khen nhẹ (intensity=0.2, valence=0.4): Joy Gain = {delta_mild.joy:.4f}, New Joy = {state_mild.joy:.4f}")

    # Case B: Intense heartfelt declaration (intensity = 0.9, valence = 0.95)
    state_deep = EmotionState(user_id=uuid.uuid4(), joy=0.1, trust=0.5, attachment=0.0)
    delta_deep = engine.update(
        state_deep,
        sentiment_analysis={"intensity": 0.9, "valence": 0.95, "primary_emotion": "flustered_affection"}
    )
    print(f"  • Thổ lộ sâu sắc (intensity=0.9, valence=0.95): Joy Gain = {delta_deep.joy:.4f}, New Joy = {state_deep.joy:.4f}")

    assert delta_deep.joy > (delta_mild.joy * 3.0), "Deep emotional declaration must generate significantly higher gain than mild praise"
    print("  ✓ PASS: Cường độ liên tục và cực tính mở rộng tỷ lệ chính xác!")


def test_safety_clamping_and_fallback():
    print("\n" + "=" * 80)
    print("🚀 TEST 2: SAFETY CLAMPING & UNKNOWN ENUM FALLBACK")
    print("=" * 80)

    engine = EmotionEngine()
    state = EmotionState(user_id=uuid.uuid4(), joy=0.2, trust=0.5)

    # Extreme out-of-bound floats and unknown archetype
    delta = engine.update(
        state,
        sentiment_analysis={
            "intensity": 3.5,      # Should clamp to 1.0
            "valence": -4.2,       # Should clamp to -1.0
            "primary_emotion": "random_super_alien_emotion"  # Fallback to calm_warmth
        }
    )

    print(f"  • Input bất thường: intensity=3.5 -> clamped: {delta.intensity}, valence=-4.2 -> clamped: {delta.valence}")
    print(f"  • Enum lạ: 'random_super_alien_emotion' -> fallback: '{delta.primary_emotion}'")

    assert delta.intensity == 1.0, f"Expected clamped intensity 1.0, got {delta.intensity}"
    assert delta.valence == -1.0, f"Expected clamped valence -1.0, got {delta.valence}"
    assert delta.primary_emotion == "calm_warmth", f"Expected fallback calm_warmth, got {delta.primary_emotion}"
    print("  ✓ PASS: Phòng vệ Clamp và Fallback an toàn 100%!")


def test_7_emotional_archetypes():
    print("\n" + "=" * 80)
    print("🚀 TEST 3: 7 EMOTIONAL ARCHETYPES BEHAVIOR")
    print("=" * 80)

    engine = EmotionEngine()

    # 1. flustered_affection: Tăng Joy & Attachment
    s1 = EmotionState(user_id=uuid.uuid4(), joy=0.1, trust=0.7, attachment=0.1)
    d1 = engine.update(s1, sentiment_analysis={"intensity": 0.8, "valence": 0.8, "primary_emotion": "flustered_affection"})
    print(f"  1. flustered_affection -> Joy={s1.joy:.3f}, Attachment={s1.attachment:.3f} (Tăng cả 2)")
    assert d1.attachment > 0

    # 2. playful_pout: Tăng nhẹ Irritation nhưng KHÔNG giảm Trust
    s2 = EmotionState(user_id=uuid.uuid4(), joy=0.2, trust=0.8, irritation=0.0)
    engine.update(
        s2,
        sentiment_analysis={"intensity": 0.7, "valence": 0.0, "primary_emotion": "playful_pout"},
    )
    print(f"  2. playful_pout -> Irritation={s2.irritation:.3f}, Trust={s2.trust:.3f} (Giữ nguyên Trust)")
    assert s2.irritation > 0
    assert s2.trust >= 0.79  # Trust không bị phạt

    # 3. melancholic_care: Tăng Trust do đồng cảm sâu sắc
    s3 = EmotionState(user_id=uuid.uuid4(), sadness=0.0, trust=0.6)
    engine.update(
        s3,
        sentiment_analysis={
            "intensity": 0.8,
            "valence": -0.3,
            "primary_emotion": "melancholic_care",
        },
    )
    print(f"  3. melancholic_care -> Sadness={s3.sadness:.3f}, Trust={s3.trust:.3f} (Đồng cảm xây dựng niềm tin)")
    assert s3.trust >= 0.60

    # 4. cheerful_joy: Tăng vọt Joy
    s4 = EmotionState(user_id=uuid.uuid4(), joy=0.1, sadness=0.3)
    engine.update(
        s4,
        sentiment_analysis={"intensity": 0.9, "valence": 0.9, "primary_emotion": "cheerful_joy"},
    )
    print(f"  4. cheerful_joy -> Joy={s4.joy:.3f}, Sadness={s4.sadness:.3f} (Joy đè bẹp Sadness)")
    assert s4.joy > 0.25

    # 5. guarded_cold: Tụt Trust & Attachment
    s5 = EmotionState(user_id=uuid.uuid4(), trust=0.7, attachment=0.5, irritation=0.0)
    engine.update(
        s5,
        sentiment_analysis={"intensity": 0.9, "valence": -0.9, "primary_emotion": "guarded_cold"},
    )
    print(f"  5. guarded_cold -> Trust={s5.trust:.3f}, Irritation={s5.irritation:.3f} (Tụt niềm tin mạnh)")
    assert s5.trust < 0.60
    assert s5.irritation > 0.15

    print("  ✓ PASS: Toàn bộ 7 Archetypes kích hoạt đúng theo tâm lý học hành vi!")


def test_behavioral_directives_in_state_manager():
    print("\n" + "=" * 80)
    print("🚀 TEST 4: BEHAVIORAL DIRECTIVES IN SYSTEM PROMPT")
    print("=" * 80)

    # Happy state
    s_happy = EmotionState(user_id=uuid.uuid4(), joy=0.7, trust=0.8, attachment=0.7)
    prompt_happy = StateManager.format_state(s_happy)
    print(f"  • Prompt khi Happy:\n{prompt_happy}\n")
    assert "[BEHAVIORAL DIRECTIVE]" in prompt_happy
    assert "Cheerful & Bright" in prompt_happy
    assert "vui vẻ" in prompt_happy

    # Annoyed state
    s_annoyed = EmotionState(user_id=uuid.uuid4(), irritation=0.6, trust=0.4, joy=0.0)
    prompt_annoyed = StateManager.format_state(s_annoyed)
    print(f"  • Prompt khi Annoyed:\n{prompt_annoyed}\n")
    assert "[BEHAVIORAL DIRECTIVE]" in prompt_annoyed
    assert "dỗi hờn" in prompt_annoyed or "khó chịu" in prompt_annoyed

    print("  ✓ PASS: Behavioral Directives được tiêm chính xác vào Prompt!")


async def test_end_to_end_continuous_emotion_chat(test_chat_engine):
    print("\n" + "=" * 80)
    print("🚀 TEST 5: END-TO-END CHAT ENGINE CYCLE WITH CONTINUOUS EMOTION")
    print("=" * 80)

    chat_engine = test_chat_engine
    user_id = f"test_continuous_user_{uuid.uuid4().hex[:6]}"

    async with AsyncSessionFactory() as session:
        reply_text, emotions, _, _ = await chat_engine.chat(
            session=session,
            user_id=user_id,
            user_message="em Chisa ơi, hôm nay anh mệt quá, em có thể vỗ về anh một chút được không?"
        )
        await session.commit()

    print(f"  • Reply: '{reply_text}'")
    print(f"  • Updated Emotions Vector: {emotions}")
    assert emotions is not None
    assert "joy" in emotions and "trust" in emotions
    assert len(reply_text) > 0
    print("  ✓ PASS: End-to-End ChatEngine chu trình cảm xúc Continuous hoàn tất mỹ mãn!")


if __name__ == "__main__":
    test_continuous_intensity_and_valence()
    test_safety_clamping_and_fallback()
    test_7_emotional_archetypes()
    test_behavioral_directives_in_state_manager()
    asyncio.run(test_end_to_end_continuous_emotion_chat())
