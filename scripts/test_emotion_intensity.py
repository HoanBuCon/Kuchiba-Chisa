import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.domain.services.emotion_engine import EmotionEngine
from app.infrastructure.database.models.emotion_state import EmotionState


def make_state():
    return EmotionState(joy=0.5, sadness=0.0, trust=0.5, irritation=0.0, attachment=0.5)


def test_intensity_scaling():
    engine = EmotionEngine()

    # ── POSITIVE STIMULUS ────────────────────────────────────────────
    # Case A: Strongly heartfelt (is_neutral=False) — e.g., "Em yêu Chisa lắm!"
    s_pos_intense = make_state()
    d_pos_intense = engine.update(s_pos_intense, is_positive=True, is_neutral=False)

    # Case B: Casual warmth (is_neutral=True) — e.g., "Haha vui quá"
    s_pos_neutral = make_state()
    d_pos_neutral = engine.update(s_pos_neutral, is_positive=True, is_neutral=True)

    print("── POSITIVE STIMULUS TEST ─────────────────────────────")
    print(f"  Heartfelt joy delta  : {d_pos_intense.joy:+.4f}  → joy: {s_pos_intense.joy:.4f}")
    print(f"  Casual joy delta     : {d_pos_neutral.joy:+.4f}  → joy: {s_pos_neutral.joy:.4f}")
    ratio_pos = d_pos_neutral.joy / d_pos_intense.joy if d_pos_intense.joy else 0
    print(f"  Intensity ratio      : {ratio_pos:.2%}  (target ~30%)")
    assert d_pos_neutral.joy < d_pos_intense.joy, "Casual joy gain must be smaller than heartfelt."
    print("  PASS")

    # ── NEGATIVE STIMULUS ───────────────────────────────────────────
    # Case A: Genuinely distressed (is_neutral=False) — real anger/sadness
    s_neg_intense = make_state()
    d_neg_intense = engine.update(s_neg_intense, is_negative=True, is_neutral=False)

    # Case B: Mild complaint (is_neutral=True) — passing grumble
    s_neg_neutral = make_state()
    d_neg_neutral = engine.update(s_neg_neutral, is_negative=True, is_neutral=True)

    print("\n── NEGATIVE STIMULUS TEST ─────────────────────────────")
    print(f"  Intense sadness delta: {d_neg_intense.sadness:+.4f}  → sadness: {s_neg_intense.sadness:.4f}")
    print(f"  Mild sadness delta   : {d_neg_neutral.sadness:+.4f}  → sadness: {s_neg_neutral.sadness:.4f}")
    ratio_neg = d_neg_neutral.sadness / d_neg_intense.sadness if d_neg_intense.sadness else 0
    print(f"  Intensity ratio      : {ratio_neg:.2%}  (target ~35%)")
    assert d_neg_neutral.sadness < d_neg_intense.sadness, "Mild sadness gain must be smaller than intense."
    print("  PASS")

    # ── RUDE STIMULUS ────────────────────────────────────────────────
    # Case A: Clearly hostile insult (is_neutral=False)
    s_rude_intense = make_state()
    d_rude_intense = engine.update(s_rude_intense, is_rude=True, is_neutral=False)

    # Case B: Edge-case rude-ish with low severity (is_neutral=True)
    s_rude_neutral = make_state()
    d_rude_neutral = engine.update(s_rude_neutral, is_rude=True, is_neutral=True)

    print("\n── RUDE STIMULUS TEST ─────────────────────────────────")
    print(f"  Hostile irr delta  : {d_rude_intense.irritation:+.4f}  → irritation: {s_rude_intense.irritation:.4f}")
    print(f"  Mild rude irr delta: {d_rude_neutral.irritation:+.4f}  → irritation: {s_rude_neutral.irritation:.4f}")
    ratio_rude = d_rude_neutral.irritation / d_rude_intense.irritation if d_rude_intense.irritation else 0
    print(f"  Intensity ratio      : {ratio_rude:.2%}  (target ~55%)")
    assert d_rude_neutral.irritation < d_rude_intense.irritation, "Mild rude irritation must be smaller than hostile."
    print("  PASS")

    # ── PURE NEUTRAL (no flags) ──────────────────────────────────────
    s_pure = make_state()
    d_pure = engine.update(s_pure, is_neutral=True)
    print("\n── PURE NEUTRAL (only decay) ──────────────────────────")
    print(f"  Joy delta (decay only): {d_pure.joy:+.4f}")
    assert d_pure.joy < 0, "Pure neutral should only show decay (joy > baseline moves toward baseline)."
    print("  PASS — decay-only as expected")

    print("\n✓ All intensity scaling tests passed.")


if __name__ == "__main__":
    test_intensity_scaling()
