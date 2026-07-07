from typing import Dict
from app.infrastructure.database.models.emotion_state import EmotionState

class StateManager:
    """
    Manages emotional relationship states, translating raw values into qualitative labels.
    """
    @staticmethod
    def get_qualitative_label(value: float) -> str:
        if value < 0.35:
            return "Low"
        elif value <= 0.70:
            return "Medium"
        else:
            return "High"

    @classmethod
    def get_mood(cls, emotion: EmotionState) -> str:
        # Determine mood based on highest negative/positive emotions or default to calm
        if emotion.sadness > 0.5:
            return "Sad"
        elif emotion.irritation > 0.5:
            return "Annoyed"
        elif emotion.joy > 0.5:
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
