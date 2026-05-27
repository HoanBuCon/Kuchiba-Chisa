import pytest
import time
from app.infrastructure.database.models.emotion_state import EmotionState
from app.domain.services.emotion_engine import EmotionEngine

def test_emotion_engine_homeostasis_decay():
    engine = EmotionEngine()
    
    # 1. Create a state with highly elevated emotions
    now_ms = int(time.time() * 1000)
    state = EmotionState(
        joy=0.8,
        sadness=0.7,
        trust=0.8,
        irritation=0.9,
        attachment=0.5,
        updated_at=now_ms - (3 * 3600 * 1000)  # 3 hours ago
    )
    
    # Run a decay/homeostasis turn without new triggers
    delta = engine.update(
        state,
        is_positive=False,
        is_negative=False,
        is_rude=False,
        is_neutral=True
    )
    
    # Emotions should decay towards baselines:
    # baselines: joy=0.10, sadness=0.00, trust=0.50, irritation=0.00
    assert state.joy < 0.8
    assert state.sadness < 0.7
    assert state.trust < 0.8
    assert state.irritation < 0.9
    # attachment has a decay rate of 0.00, but grows slowly when trust is > 0.6 and not rude/negative
    assert state.attachment == pytest.approx(0.505)

def test_emotion_engine_user_sentiment_stimulus():
    engine = EmotionEngine()
    
    # Joyous state after positive message
    now_ms = int(time.time() * 1000)
    state = EmotionState(
        joy=0.1,
        sadness=0.0,
        trust=0.5,
        irritation=0.0,
        attachment=0.1,
        updated_at=now_ms
    )
    
    engine.update(state, is_positive=True, is_neutral=False)
    assert state.joy > 0.1
    assert state.trust > 0.5

    # Melancholic/sad state after negative message
    state2 = EmotionState(
        joy=0.1,
        sadness=0.0,
        trust=0.5,
        irritation=0.0,
        attachment=0.1,
        updated_at=now_ms
    )
    engine.update(state2, is_negative=True, is_neutral=False)
    assert state2.sadness > 0.0
    assert state2.joy < 0.1

def test_emotion_engine_chisa_self_sentiment():
    engine = EmotionEngine()
    now_ms = int(time.time() * 1000)
    
    # Test sadness trigger
    state_sad = EmotionState(
        joy=0.1,
        sadness=0.0,
        trust=0.5,
        irritation=0.0,
        attachment=0.1,
        updated_at=now_ms
    )
    engine.update(state_sad, chisa_sad=True)
    assert state_sad.sadness >= 0.12

    # Test annoyed trigger
    state_annoyed = EmotionState(
        joy=0.1,
        sadness=0.0,
        trust=0.5,
        irritation=0.0,
        attachment=0.1,
        updated_at=now_ms
    )
    engine.update(state_annoyed, chisa_annoyed=True)
    assert state_annoyed.irritation >= 0.10

    # Test happy trigger
    state_happy = EmotionState(
        joy=0.1,
        sadness=0.0,
        trust=0.5,
        irritation=0.0,
        attachment=0.1,
        updated_at=now_ms
    )
    engine.update(state_happy, chisa_happy=True)
    assert state_happy.joy > 0.1

    # Test flustered (Tsundere peak) trigger
    state_flustered = EmotionState(
        joy=0.1,
        sadness=0.0,
        trust=0.5,
        irritation=0.0,
        attachment=0.1,
        updated_at=now_ms
    )
    engine.update(state_flustered, chisa_flustered=True)
    assert state_flustered.joy > 0.1
    # Attachment grows on flustered tsundere peak
    assert state_flustered.attachment > 0.1
