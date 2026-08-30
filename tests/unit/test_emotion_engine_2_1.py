import pytest
from unittest.mock import patch
from datetime import datetime
from zoneinfo import ZoneInfo
from uuid import uuid4

from app.domain.entities.emotion import EmotionState
from app.domain.services.state_manager import StateManager


def test_circadian_context_morning():
    # Simulate 07:00 AM
    mock_dt = datetime(2026, 8, 20, 7, 0, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))
    with patch("app.domain.services.state_manager.datetime") as mock_datetime:
        mock_datetime.now.return_value = mock_dt
        phase, directive = StateManager.get_circadian_context()
        assert phase == "Morning Refresh"
        assert "sáng sớm" in directive or "trong trẻo" in directive


def test_circadian_context_midnight():
    # Simulate 01:30 AM
    mock_dt = datetime(2026, 8, 20, 1, 30, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))
    with patch("app.domain.services.state_manager.datetime") as mock_datetime:
        mock_datetime.now.return_value = mock_dt
        phase, directive = StateManager.get_circadian_context()
        assert phase == "Midnight Whisper"
        assert "thì thầm" in directive or "đêm khuya" in directive


def test_circadian_context_twilight():
    # Simulate 17:30 (5:30 PM)
    mock_dt = datetime(2026, 8, 20, 17, 30, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))
    with patch("app.domain.services.state_manager.datetime") as mock_datetime:
        mock_datetime.now.return_value = mock_dt
        phase, directive = StateManager.get_circadian_context()
        assert phase == "Twilight Serenity"
        assert "hoàng hôn" in directive or "chiều" in directive


def test_dyad_level_1_sweet_gap_moe():
    state = EmotionState(
        user_id=uuid4(),
        shyness=0.85,
        attachment=0.70,
        joy=0.60,
        trust=0.80
    )
    dyad = StateManager.get_emotional_dyad(state)
    assert dyad is not None
    assert "Sweet Gap Moe" in dyad[0]
    assert "S-senpai..." in dyad[1]


def test_dyad_level_2_vulnerable_confiding():
    state = EmotionState(
        user_id=uuid4(),
        sadness=0.50,
        trust=0.75,
        shyness=0.30,
        attachment=0.30
    )
    dyad = StateManager.get_emotional_dyad(state)
    assert dyad is not None
    assert "Vulnerable Confiding" in dyad[0]
    assert "tựa đầu vào vai" in dyad[1]


def test_dyad_level_3_affectionate_pout():
    state = EmotionState(
        user_id=uuid4(),
        irritation=0.50,
        attachment=0.35,
        trust=0.70,
        shyness=0.40
    )
    dyad = StateManager.get_emotional_dyad(state)
    assert dyad is not None
    assert "Affectionate Pout" in dyad[0]
    assert "dỗi yêu" in dyad[1]


def test_dyad_level_4_flustered_sweetness():
    state = EmotionState(
        user_id=uuid4(),
        joy=0.65,
        shyness=0.60,
        attachment=0.30,
        trust=0.50
    )
    dyad = StateManager.get_emotional_dyad(state)
    assert dyad is not None
    assert "Flustered Sweetness" in dyad[0]
    assert "ngượng chín mặt" in dyad[1]


def test_dyad_level_5_relaxed_wonder():
    state = EmotionState(
        user_id=uuid4(),
        comfort=0.75,
        curiosity=0.65,
        joy=0.20,
        shyness=0.10
    )
    dyad = StateManager.get_emotional_dyad(state)
    assert dyad is not None
    assert "Relaxed Wonder" in dyad[0]
    assert "khám phá" in dyad[1]


def test_dyad_none_fallback():
    state = EmotionState(
        user_id=uuid4(),
        joy=0.10,
        sadness=0.00,
        trust=0.50,
        attachment=0.10,
        irritation=0.00,
        shyness=0.10,
        curiosity=0.20,
        comfort=0.50
    )
    dyad = StateManager.get_emotional_dyad(state)
    assert dyad is None


def test_get_unified_directive_with_dyad_and_circadian():
    state = EmotionState(
        user_id=uuid4(),
        joy=0.60,
        shyness=0.60,
        trust=0.60,
        attachment=0.40
    )
    directive = StateManager.get_unified_directive(state, attachment_val=0.40, elapsed_hours=0.0)
    assert "[CIRCADIAN AMBIENT:" in directive
    assert "[DYAD EMOTION: Flustered Sweetness]" in directive


def test_format_state_with_dyad_mood():
    state = EmotionState(
        user_id=uuid4(),
        shyness=0.85,
        attachment=0.70,
        trust=0.80
    )
    formatted = StateManager.format_state(state, attachment_bonus=0.0, elapsed_hours=0.0)
    assert "- Current Mood: Sweet Gap Moe" in formatted
    assert "[BEHAVIORAL DIRECTIVE]" in formatted


def test_circadian_context_cozy_evening():
    # Simulate 20:00 (8:00 PM)
    mock_dt = datetime(2026, 8, 20, 20, 0, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))
    with patch("app.domain.services.state_manager.datetime") as mock_datetime:
        mock_datetime.now.return_value = mock_dt
        phase, directive = StateManager.get_circadian_context()
        assert phase == "Cozy Evening"
        assert "ấm cúng" in directive or "buổi tối" in directive


def test_resona_3_0_philosophical_loving_case():
    """
    Test case thực tế: Senpai hỏi 'Em có thấy thế giới này thật vô vị nếu thiếu em không?'
    LLM nhận định: reaction='flustered_affection', user_stance='loving', intensity=0.85, variance=-0.25.
    Kiểm tra: Trust PHẢI TĂNG (không được tụt), Shyness tăng, Comfort tăng, Irritation = 0.
    """
    from app.domain.services.emotion_engine import EmotionEngine
    engine = EmotionEngine()
    
    state = EmotionState(
        user_id=uuid4(),
        joy=0.10,
        sadness=0.00,
        trust=0.50,
        irritation=0.00,
        attachment=0.10,
        shyness=0.00,
        curiosity=0.20,
        comfort=0.50
    )
    
    delta = engine.update(
        state,
        sentiment_analysis={
            "reaction": "flustered_affection",
            "user_stance": "loving",
            "intensity": 0.85,
            "variance": -0.25
        }
    )
    
    # 1. Trust TUYỆT ĐỐI KHÔNG TỤT
    assert state.trust > 0.50, f"Expected Trust to increase, got {state.trust}"
    # 2. Shyness tăng mạnh do đỏ mặt / rung động
    assert state.shyness > 0.30, f"Expected high shyness, got {state.shyness}"
    # 3. Comfort tăng do cảm giác ấm áp
    assert state.comfort > 0.50, f"Expected comfort increase, got {state.comfort}"
    # 4. Irritation bằng 0
    assert state.irritation == 0.0, f"Expected irritation 0, got {state.irritation}"
    # 5. Sadness có chút sắc thái man mác triết lý nhẹ
    assert state.sadness > 0.0


def test_resona_3_0_pout_shield_protection():
    """
    Test case: Senpai trêu chọc -> Chisa dỗi yêu (playful_pout).
    Kiểm tra: Irritation tăng nhẹ nhưng Trust được bảo vệ 100% qua Pout Shield.
    """
    from app.domain.services.emotion_engine import EmotionEngine
    engine = EmotionEngine()
    
    state = EmotionState(
        user_id=uuid4(),
        trust=0.70,
        irritation=0.00,
        attachment=0.30
    )
    
    delta = engine.update(
        state,
        sentiment_analysis={
            "reaction": "playful_pout",
            "user_stance": "playful",
            "intensity": 0.80,
            "variance": 0.0
        }
    )
    
    assert state.irritation > 0.10, "Irritation must increase on pout"
    assert state.trust >= 0.70, f"Trust must NOT decrease under Pout Shield, got {state.trust}"


def test_resona_3_0_soulmate_confiding():
    """
    Test case: Senpai tâm sự yếu lòng -> Chisa lắng nghe đồng cảm (melancholic_care).
    Kiểm tra: Trust tăng mạnh và Comfort tăng.
    """
    from app.domain.services.emotion_engine import EmotionEngine
    engine = EmotionEngine()
    
    state = EmotionState(
        user_id=uuid4(),
        trust=0.60,
        comfort=0.50,
        sadness=0.00
    )
    
    delta = engine.update(
        state,
        sentiment_analysis={
            "reaction": "melancholic_care",
            "user_stance": "vulnerable",
            "intensity": 0.80,
            "variance": -0.20
        }
    )
    
    assert state.trust > 0.62, "Trust must increase strongly when confiding"
    assert state.comfort > 0.55, "Comfort must increase when solace is given"


def test_resona_3_1_vulgar_teasing_boundary_breach():
    """
    Test case thực tế người dùng báo cáo:
    User trêu cợt thô tục/khoe khoang phản cảm ("anh vừa đi chơi gái xong...").
    LLM nhận định: reaction='guarded_cold', user_stance='playful', intensity=0.60, variance=-0.20.
    Kiểm tra:
    1. Trust PHẢI GIẢM (không được tăng).
    2. Attachment PHẢI GIẢM hoặc ĐÓNG BĂNG (không được tăng vọt).
    3. Irritation tăng cao.
    4. Không bị nhận nhầm thành dỗi yêu (Affectionate Pout).
    """
    from app.domain.services.emotion_engine import EmotionEngine
    engine = EmotionEngine()

    state = EmotionState(
        user_id=uuid4(),
        joy=0.15,
        sadness=0.00,
        trust=0.50,
        irritation=0.00,
        attachment=0.01,
        shyness=0.02,
        curiosity=0.24,
        comfort=0.55
    )

    delta = engine.update(
        state,
        sentiment_analysis={
            "reaction": "guarded_cold",
            "user_stance": "playful",
            "intensity": 0.60,
            "variance": -0.20
        }
    )

    # Trust must decrease
    assert state.trust < 0.50, f"Trust must decrease on boundary breach, got {state.trust}"
    # Attachment must not increase
    assert state.attachment <= 0.01, f"Attachment must not increase on boundary breach, got {state.attachment}"
    # Irritation must rise
    assert state.irritation >= 0.25, f"Irritation must rise on cold withdrawal, got {state.irritation}"
    # Must NOT be Affectionate Pout
    dyad = StateManager.get_emotional_dyad(state)
    assert dyad is None, f"Expected no affectionate pout dyad, got {dyad}"
    assert StateManager.get_mood(state) == "Annoyed"


def test_resona_3_1_affectionate_pout_new_thresholds():
    """
    Kiểm tra ngưỡng Dỗi yêu mới: Cần CẢ trust >= 0.65 VÀ attachment >= 0.25.
    """
    # Case A: Trust = 0.55 (< 0.65), Attachment = 0.10 (< 0.25), Irritation = 0.48 -> Annoyed
    state_a = EmotionState(
        user_id=uuid4(),
        trust=0.55,
        attachment=0.10,
        irritation=0.48
    )
    assert StateManager.get_emotional_dyad(state_a) is None
    assert StateManager.get_mood(state_a) == "Annoyed"

    # Case B: Trust = 0.70 (>= 0.65), Attachment = 0.30 (>= 0.25), Irritation = 0.48 -> Affectionate Pout
    state_b = EmotionState(
        user_id=uuid4(),
        trust=0.70,
        attachment=0.30,
        irritation=0.48
    )
    dyad_b = StateManager.get_emotional_dyad(state_b)
    assert dyad_b is not None
    assert dyad_b[0] == "Affectionate Pout"
    assert StateManager.get_mood(state_b) == "Playful Pout"

