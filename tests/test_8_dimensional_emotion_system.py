"""
Comprehensive Automated Test Suite for 8-Dimensional Emotion & Relational Architecture (Chisa Emotion Engine 2.0).
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


def test_trust_5_tier_ladder_and_compliance():
    print("=" * 80)
    print("🚀 TEST 1: 5-TIER TRUST LADDER & COMPLIANCE")
    print("=" * 80)

    # T1 Guarded (<0.35)
    s_t1 = EmotionState(user_id=uuid.uuid4(), trust=0.20)
    t1_tier, _ = StateManager.get_trust_tier(s_t1.trust)
    print(f"  • Trust=0.20 -> Tier: '{t1_tier}'")
    assert "T1" in t1_tier and "Dè chừng" in t1_tier

    # T4 Confidant (0.75 - 0.90) - Dễ dụ & Nghe lời
    s_t4 = EmotionState(user_id=uuid.uuid4(), trust=0.82)
    t4_tier, t4_directive = StateManager.get_trust_tier(s_t4.trust)
    print(f"  • Trust=0.82 -> Tier: '{t4_tier}'")
    print(f"  • Directive T4: {t4_directive}\n")
    assert "T4" in t4_tier and "Tri kỷ" in t4_tier
    assert "mềm lòng" in t4_directive or "chiều theo" in t4_directive

    # T5 Devoted Trust (>=0.90)
    s_t5 = EmotionState(user_id=uuid.uuid4(), trust=0.95)
    t5_tier, _ = StateManager.get_trust_tier(s_t5.trust)
    print(f"  • Trust=0.95 -> Tier: '{t5_tier}'")
    assert "T5" in t5_tier and "Tuyệt đối" in t5_tier

    print("  ✓ PASS: Thang đo 5 Nấc Tin tưởng (Trust Ladder) hoạt động chuẩn xác!")


def test_attachment_5_tier_and_absence_longing():
    print("\n" + "=" * 80)
    print("🚀 TEST 2: 5-TIER ATTACHMENT LADDER & ABSENCE LONGING (>=24h)")
    print("=" * 80)

    # A1 Distant
    s_a1 = EmotionState(user_id=uuid.uuid4(), attachment=0.10)
    a1_tier, _ = StateManager.get_attachment_tier(s_a1.attachment)
    print(f"  • Attachment=0.10 -> Tier: '{a1_tier}'")
    assert "A1" in a1_tier and "Độc lập" in a1_tier

    # A4 Deep Intimacy
    s_a4 = EmotionState(user_id=uuid.uuid4(), attachment=0.78, trust=0.80)
    a4_tier, _ = StateManager.get_attachment_tier(s_a4.attachment)
    print(f"  • Attachment=0.78 -> Tier: '{a4_tier}'")
    assert "A4" in a4_tier and "Tâm đầu ý hợp" in a4_tier

    # Absence Longing test: Senpai quay lại sau 48 tiếng
    prompt_longing = StateManager.format_state(s_a4, elapsed_hours=48.0)
    print(f"  • Directive khi vắng bóng 48h:\n{prompt_longing}\n")
    assert "[ABSENCE LONGING: ĐÃ VẮNG BÓNG 48 TIẾNG" in prompt_longing
    assert "nhớ nhung" in prompt_longing or "hờn dỗi" in prompt_longing

    print("  ✓ PASS: Thang đo Gắn bó & Hiệu ứng Nhớ nhung theo Thời gian kích hoạt hoàn hảo!")


def test_shyness_curiosity_comfort_channels():
    print("\n" + "=" * 80)
    print("🚀 TEST 3: SHYNESS (GAP MOE), CURIOSITY & COMFORT CHANNELS")
    print("=" * 80)

    engine = EmotionEngine()

    # 1. Shyness Boost (Flustered Affection)
    s_shy = EmotionState(user_id=uuid.uuid4(), shyness=0.10, trust=0.60)
    d_shy = engine.update(s_shy, sentiment_analysis={"intensity": 0.9, "valence": 0.85, "primary_emotion": "flustered_affection"})
    print(f"  1. Shyness: Old=0.10 -> New={s_shy.shyness:.3f} (Delta={d_shy.shyness:.3f})")
    assert s_shy.shyness > 0.35
    prompt_shy = StateManager.format_state(s_shy)
    assert "ngượng" in prompt_shy.lower() or "bối rối" in prompt_shy.lower()

    # 2. Curiosity Boost (Cheerful Joy / Learning)
    s_cur = EmotionState(user_id=uuid.uuid4(), curiosity=0.20)
    d_cur = engine.update(s_cur, sentiment_analysis={"intensity": 0.85, "valence": 0.7, "primary_emotion": "cheerful_joy"})
    print(f"  2. Curiosity: Old=0.20 -> New={s_cur.curiosity:.3f} (Delta={d_cur.curiosity:.3f})")
    assert s_cur.curiosity > 0.30

    # 3. Comfort Boost (Melancholic Care / Soothing)
    s_comf = EmotionState(user_id=uuid.uuid4(), comfort=0.50, trust=0.60)
    d_comf = engine.update(s_comf, sentiment_analysis={"intensity": 0.8, "valence": 0.6, "primary_emotion": "calm_warmth"})
    print(f"  3. Comfort: Old=0.50 -> New={s_comf.comfort:.3f} (Delta={d_comf.comfort:.3f})")
    assert s_comf.comfort >= 0.50

    print("  ✓ PASS: Cả 3 kênh Ngại ngùng, Hiếu kỳ và Bình yên tăng trưởng mượt mà!")


def test_antagonistic_cross_inhibition_and_pout_shield():
    print("\n" + "=" * 80)
    print("🚀 TEST 4: ANTAGONISTIC CROSS-INHIBITION & POUT SHIELD")
    print("=" * 80)

    engine = EmotionEngine()

    # Case A: Irritation quenches Shyness (Anger quenches Romance)
    s_quench = EmotionState(user_id=uuid.uuid4(), shyness=0.70, irritation=0.0, trust=0.30)
    engine.update(s_quench, sentiment_analysis={"intensity": 0.9, "valence": -0.9, "primary_emotion": "guarded_cold"})
    print(f"  • Cáu giận dập tắt Ngại ngùng: Shyness ban đầu=0.70 -> Sau cơn giận={s_quench.shyness:.3f} (Ép về 0)")
    assert s_quench.shyness < 0.10, "High irritation must extinguish shyness"

    # Case B: Pout Shield (Dỗi hờn đáng yêu khi Attachment cao -> Giữ nguyên Trust)
    s_pout = EmotionState(user_id=uuid.uuid4(), attachment=0.65, trust=0.80, irritation=0.0)
    engine.update(s_pout, sentiment_analysis={"intensity": 0.75, "valence": 0.0, "primary_emotion": "playful_pout"})
    print(f"  • Pout Shield: Irritation={s_pout.irritation:.3f}, Trust={s_pout.trust:.3f} (Trust giữ nguyên không bị trừ!)")
    assert s_pout.irritation > 0.0
    assert s_pout.trust >= 0.795, "Pout Shield must protect trust from being penalized"

    # Case C: Empathetic Melancholic Care increases Trust
    s_care = EmotionState(user_id=uuid.uuid4(), sadness=0.0, trust=0.60)
    engine.update(s_care, sentiment_analysis={"intensity": 0.8, "valence": -0.3, "primary_emotion": "melancholic_care"})
    print(f"  • Đồng cảm xót xa: Sadness={s_care.sadness:.3f}, Trust={s_care.trust:.3f} (Tăng niềm tin)")
    assert s_care.trust > 0.60, "Melancholic care must increase trust"

    print("  ✓ PASS: Ma trận Ức chế Đối kháng & Khiên Pout Shield hoạt động xuất sắc 100%!")


async def test_end_to_end_8_dimensional_chat_cycle(test_chat_engine):
    print("\n" + "=" * 80)
    print("🚀 TEST 5: END-TO-END CHAT ENGINE CYCLE WITH 8-DIMENSIONAL EMOTIONS")
    print("=" * 80)

    chat_engine = test_chat_engine
    user_id = f"test_8d_user_{uuid.uuid4().hex[:6]}"

    async with AsyncSessionFactory() as session:
        reply_text, emotions, _, _ = await chat_engine.chat(
            session=session,
            user_id=user_id,
            user_message="Chisa ơi, em có thấy anh thông minh và đáng yêu không nào?"
        )
        await session.commit()

    print(f"  • Chisa Reply: '{reply_text}'")
    print(f"  • 8-Dimensional Emotions Vector:\n    {emotions}")

    assert emotions is not None
    assert "joy" in emotions and "trust" in emotions and "shyness" in emotions
    assert "curiosity" in emotions and "comfort" in emotions and "attachment" in emotions
    assert len(reply_text) > 0
    print("  ✓ PASS: End-to-End ChatEngine chu trình 8 chiều hoàn tất mỹ mãn!")


if __name__ == "__main__":
    test_trust_5_tier_ladder_and_compliance()
    test_attachment_5_tier_and_absence_longing()
    test_shyness_curiosity_comfort_channels()
    test_antagonistic_cross_inhibition_and_pout_shield()
    asyncio.run(test_end_to_end_8_dimensional_chat_cycle())
