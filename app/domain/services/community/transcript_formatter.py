from typing import List, Optional
from app.domain.entities.community import CommunityMessage
from app.domain.services.context_budget_manager import TokenEstimator


class ChannelTranscriptFormatter:
    """
    Formats multi-user community chat messages into a structured,
    speaker-aware dialogue transcript for LLM context injection.
    """

    @staticmethod
    def format_message(msg: CommunityMessage) -> str:
        """Format a single message turn with timestamp, speaker and reply context."""
        time_str = msg.created_at.strftime("%H:%M") if msg.created_at else "Now"
        speaker_tag = f"<{msg.speaker_name}>"

        reply_info = ""
        if msg.reply_to_speaker:
            reply_info = f" [Replying to @{msg.reply_to_speaker}]"

        return f"[{time_str}] {speaker_tag}{reply_info}: {msg.content}"

    @classmethod
    def format_transcript(
        cls,
        messages: List[CommunityMessage],
        max_tokens: int = 1200,
        token_estimator: Optional[TokenEstimator] = None,
    ) -> str:
        """
        Format a sequence of community messages into a rolling transcript,
        trimming from the oldest turns if exceeding the token budget.
        """
        if not messages:
            return ""

        estimator = token_estimator or TokenEstimator
        formatted_lines = [cls.format_message(m) for m in messages]

        # Check total tokens and trim oldest messages if necessary
        full_text = "\n".join(formatted_lines)
        if estimator.estimate(full_text) <= max_tokens:
            return full_text

        # Trim oldest turns while preserving newest turns
        trimmed_lines: List[str] = []
        running_token_count = 0

        for line in reversed(formatted_lines):
            line_tokens = estimator.estimate(line + "\n")
            if running_token_count + line_tokens > max_tokens:
                break
            trimmed_lines.insert(0, line)
            running_token_count += line_tokens

        return "\n".join(trimmed_lines)
