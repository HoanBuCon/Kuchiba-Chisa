from app.domain.entities.emotion import EmotionState
from app.domain.tuning.memory import EmotionTuning

class StateManager:
    """
    Manages emotional relationship states, translating raw values into qualitative labels.
    """
    @staticmethod
    def get_qualitative_label(value: float) -> str:
        if value < EmotionTuning.LABEL_THRESHOLD_LOW:
            return "Low"
        elif value <= EmotionTuning.LABEL_THRESHOLD_MEDIUM:
            return "Medium"
        else:
            return "High"

    @classmethod
    def get_mood(cls, emotion: EmotionState) -> str:
        # Determine mood based on highest negative/positive emotions or default to calm
        if emotion.sadness > EmotionTuning.MOOD_THRESHOLD:
            return "Sad"
        elif emotion.irritation > EmotionTuning.MOOD_THRESHOLD:
            return "Annoyed"
        elif emotion.joy > EmotionTuning.MOOD_THRESHOLD:
            return "Happy"
        return "Calm"

    @classmethod
    def format_state(cls, emotion: EmotionState, attachment_bonus: float = 0.0) -> str:
        trust_label = cls.get_qualitative_label(emotion.trust)
        affection_val = emotion.attachment + attachment_bonus
        affection_label = cls.get_qualitative_label(affection_val)
        mood_label = cls.get_mood(emotion)
        
        return (
            "[CURRENT STATE]\n"
            f"Trust: {trust_label}\n"
            f"Affection: {affection_label}\n"
            f"Mood: {mood_label}"
        )
