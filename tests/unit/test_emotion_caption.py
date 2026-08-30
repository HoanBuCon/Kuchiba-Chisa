import pytest
from app.domain.entities.emotion import EmotionState
from app.domain.services.state_manager import StateManager


def test_caption_sweet_gap_moe():
    state = EmotionState(
        user_id="test_user",
        trust=0.75,
        attachment=0.70,
        shyness=0.85,
        joy=0.50,
        sadness=0.0,
        irritation=0.0,
        curiosity=0.30,
        comfort=0.60
    )
    caption = StateManager.get_emotion_summary_caption(state)
    assert "ngượng ngùng cực điểm" in caption
    assert "Kuudere" in caption


def test_caption_vulnerable_confiding():
    state = EmotionState(
        user_id="test_user",
        trust=0.75,
        attachment=0.50,
        sadness=0.55,
        irritation=0.0,
        joy=0.10,
        shyness=0.20,
        curiosity=0.20,
        comfort=0.50
    )
    caption = StateManager.get_emotion_summary_caption(state)
    assert "xúc động" in caption
    assert "vai Senpai" in caption


def test_caption_affectionate_pout():
    state = EmotionState(
        user_id="test_user",
        trust=0.70,
        attachment=0.30,
        irritation=0.50,
        joy=0.25,
        sadness=0.05,
        shyness=0.10,
        curiosity=0.30,
        comfort=0.55
    )
    caption = StateManager.get_emotion_summary_caption(state)
    assert "phồng má dỗi yêu" in caption


def test_caption_flustered_sweetness():
    state = EmotionState(
        user_id="test_user",
        trust=0.60,
        attachment=0.30,
        joy=0.60,
        shyness=0.60,
        sadness=0.0,
        irritation=0.0,
        curiosity=0.30,
        comfort=0.50
    )
    caption = StateManager.get_emotion_summary_caption(state)
    assert "ngập tràn hạnh phúc vừa ngượng chín mặt" in caption


def test_caption_relaxed_wonder():
    state = EmotionState(
        user_id="test_user",
        trust=0.60,
        attachment=0.30,
        comfort=0.75,
        curiosity=0.65,
        joy=0.40,
        sadness=0.0,
        irritation=0.0,
        shyness=0.10
    )
    caption = StateManager.get_emotion_summary_caption(state)
    assert "say sưa cùng Senpai khám phá" in caption


def test_caption_severe_irritation_hostile():
    state = EmotionState(
        user_id="test_user",
        trust=0.30,
        attachment=0.0,
        irritation=0.75,
        joy=0.0,
        sadness=0.20,
        shyness=0.0,
        curiosity=0.10,
        comfort=0.15
    )
    caption = StateManager.get_emotion_summary_caption(state)
    assert "cực kỳ tức giận" in caption or "rào chắn phòng thủ" in caption


def test_caption_mild_pout():
    state = EmotionState(
        user_id="test_user",
        trust=0.55,
        attachment=0.10,
        irritation=0.20,
        joy=0.30,
        sadness=0.05,
        shyness=0.10,
        curiosity=0.30,
        comfort=0.55
    )
    caption = StateManager.get_emotion_summary_caption(state)
    assert "phụng phịu dỗi nhẹ" in caption


def test_caption_inseparable_bond():
    state = EmotionState(
        user_id="test_user",
        trust=0.95,
        attachment=0.92,
        joy=0.50,
        sadness=0.0,
        irritation=0.0,
        shyness=0.20,
        curiosity=0.30,
        comfort=0.60
    )
    caption = StateManager.get_emotion_summary_caption(state)
    assert "lý do tồn tại duy nhất" in caption or "gắn kết trọn đời" in caption


def test_caption_baseline_calm():
    state = EmotionState(
        user_id="test_user",
        trust=0.50,
        attachment=0.02,
        joy=0.40,
        sadness=0.10,
        irritation=0.05,
        shyness=0.05,
        curiosity=0.25,
        comfort=0.55
    )
    caption = StateManager.get_emotion_summary_caption(state)
    assert "Kuudere điềm tĩnh" in caption


def test_caption_irritation_never_leaks_chill():
    # Even if comfort is 0.75, if irritation is 0.45 and attachment is low, Chisa MUST be annoyed/pouting, NOT chill
    state = EmotionState(
        user_id="test_user",
        trust=0.60,
        attachment=0.02,
        joy=0.30,
        sadness=0.10,
        irritation=0.45,
        shyness=0.05,
        curiosity=0.25,
        comfort=0.75
    )
    caption = StateManager.get_emotion_summary_caption(state)
    assert "khó chịu" in caption or "bực bội" in caption or "giận dỗi" in caption
    assert "thư thái" not in caption
    assert "bình yên" not in caption
    assert "Kuudere điềm tĩnh" not in caption


def test_caption_pure_annoyance_with_high_trust():
    # Irritation 0.75 with Trust 0.60 -> Must be angry/indignant
    state = EmotionState(
        user_id="test_user",
        trust=0.60,
        attachment=0.10,
        joy=0.10,
        sadness=0.10,
        irritation=0.75,
        shyness=0.0,
        curiosity=0.10,
        comfort=0.20
    )
    caption = StateManager.get_emotion_summary_caption(state)
    assert "khó chịu" in caption or "bức xúc" in caption or "tức giận" in caption
