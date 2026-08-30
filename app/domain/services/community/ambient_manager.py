import math
import time
from typing import Dict, Any, Optional
from app.domain.entities.emotion import EmotionState


class AmbientMoodManager:
    """
    Manages Server-Level Ambient Emotional Resonance using continuous exponential decay.
    
    In a shared community/group environment, Chisa's transient emotional channels
    (joy, sadness, irritation, shyness, curiosity, comfort) form a collective living
    ambient state across all interactions in the server. Relational bonds (trust, attachment)
    remain strictly individual per user.
    """

    KUUDERE_BASELINE: Dict[str, float] = {
        "joy": 0.40,
        "sadness": 0.10,
        "irritation": 0.10,
        "shyness": 0.0,
        "curiosity": 0.20,
        "comfort": 0.50,
    }

    # Half-life of 30 minutes (1800 seconds) for transient mood return to equilibrium
    HALF_LIFE_SECONDS: float = 1800.0
    TAU: float = HALF_LIFE_SECONDS / math.log(2)  # ~2597.07 seconds

    @classmethod
    def calculate_decay(
        cls,
        stored_state: Optional[Dict[str, Any]],
        current_time: Optional[float] = None,
    ) -> Dict[str, float]:
        """
        Applies exponential decay towards the Kuudere baseline:
        E(t) = Baseline + (Stored - Baseline) * exp(-delta_t / tau)
        """
        now = current_time if current_time is not None else time.time()
        if not stored_state or not isinstance(stored_state, dict):
            return dict(cls.KUUDERE_BASELINE)

        last_updated = float(stored_state.get("last_updated_at", now))
        delta_t = max(0.0, now - last_updated)
        decay_factor = math.exp(-delta_t / cls.TAU)

        decayed = {}
        for channel, baseline_val in cls.KUUDERE_BASELINE.items():
            stored_val = float(stored_state.get(channel, baseline_val))
            decayed_val = baseline_val + (stored_val - baseline_val) * decay_factor
            # Clamp between 0.0 and 1.0
            decayed[channel] = max(0.0, min(1.0, round(decayed_val, 4)))

        return decayed

    @classmethod
    def synthesize_ambient_into_emotion(
        cls,
        emotion: EmotionState,
        ambient_mood: Dict[str, float],
    ) -> None:
        """
        Blends the server-level ambient mood into the speaker's transient emotion channels.
        Trust and Attachment remain untouched (strictly individual).
        """
        if not ambient_mood:
            return

        emotion.joy = ambient_mood.get("joy", emotion.joy)
        emotion.sadness = ambient_mood.get("sadness", emotion.sadness)
        emotion.irritation = ambient_mood.get("irritation", emotion.irritation)
        emotion.shyness = ambient_mood.get("shyness", getattr(emotion, "shyness", 0.0))
        emotion.curiosity = ambient_mood.get("curiosity", getattr(emotion, "curiosity", 0.20))
        emotion.comfort = ambient_mood.get("comfort", getattr(emotion, "comfort", 0.50))

    @classmethod
    def extract_ambient_snapshot(
        cls,
        emotion: EmotionState,
        timestamp: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Captures the post-interaction transient emotion channels to persist as the new
        Server-Level Ambient State.
        """
        now = timestamp if timestamp is not None else time.time()
        return {
            "joy": max(0.0, min(1.0, round(emotion.joy, 4))),
            "sadness": max(0.0, min(1.0, round(emotion.sadness, 4))),
            "irritation": max(0.0, min(1.0, round(emotion.irritation, 4))),
            "shyness": max(0.0, min(1.0, round(getattr(emotion, "shyness", 0.0), 4))),
            "curiosity": max(0.0, min(1.0, round(getattr(emotion, "curiosity", 0.20), 4))),
            "comfort": max(0.0, min(1.0, round(getattr(emotion, "comfort", 0.50), 4))),
            "last_updated_at": now,
        }

    @classmethod
    def describe_ambient_mood(cls, ambient: Optional[Dict[str, float]]) -> str:
        """
        Generates a natural, humanized Vietnamese description of the server-level ambient emotional state.
        """
        if not ambient or not isinstance(ambient, dict):
            return "Bầu không khí trong phòng chat đang ở trạng thái điềm tĩnh, êm đềm và thanh thản."

        joy = float(ambient.get("joy", 0.40))
        sadness = float(ambient.get("sadness", 0.10))
        irritation = float(ambient.get("irritation", 0.10))
        comfort = float(ambient.get("comfort", 0.50))
        curiosity = float(ambient.get("curiosity", 0.20))
        shyness = float(ambient.get("shyness", 0.0))

        # 1. Extreme or High Irritation
        if irritation >= 0.40:
            return f"Bầu không khí phòng chat đang có phần căng thẳng, ồn ào và hơi khó chịu (Khó chịu: {irritation:.2f}, Bình yên: {comfort:.2f}). Hãy giữ sự điềm tĩnh và chừng mực."
        if irritation >= 0.20:
            return f"Phòng chat vừa có chút trêu đùa rôm rả xen lẫn phụng phịu hờn dỗi nhẹ (Khó chịu: {irritation:.2f}, Vui vẻ: {joy:.2f})."

        # 2. High Sadness / Melancholy
        if sadness >= 0.40:
            return f"Không gian phòng chat đang lắng đọng, có chút trầm tư và u buồn man mác (Buồn bã: {sadness:.2f}, Bình yên: {comfort:.2f}). Hãy đối thoại với sự dịu dàng, lắng nghe."

        # 3. High Joy / Cheerful Festivity
        if joy >= 0.60 and shyness >= 0.20:
            return f"Bầu không khí phòng chat đang rất nhộn nhịp, ngọt ngào và tràn ngập niềm vui (Vui vẻ: {joy:.2f}, Ngại ngùng: {shyness:.2f})."
        if joy >= 0.50:
            return f"Bầu không khí phòng chat đang rộn ràng, vui tươi và thoải mái (Vui vẻ: {joy:.2f}, Bình yên: {comfort:.2f})."

        # 4. High Curiosity / Analytical Discussions
        if curiosity >= 0.50:
            return f"Mọi người trong phòng đang sôi nổi thảo luận, tìm tòi và chia sẻ kiến thức mới (Hiếu kỳ: {curiosity:.2f}, Bình yên: {comfort:.2f})."

        # 5. High Comfort / Cozy Sanctuary
        if comfort >= 0.60:
            return f"Bầu không khí phòng chat đang rất ấm cúng, êm đềm, thư thái và bình yên (Bình yên: {comfort:.2f}, Vui vẻ: {joy:.2f})."

        # 6. Baseline
        return f"Bầu không khí phòng chat đang ở trạng thái điềm tĩnh, hài hòa và ấm áp ngầm (Bình yên: {comfort:.2f}, Vui vẻ: {joy:.2f})."
