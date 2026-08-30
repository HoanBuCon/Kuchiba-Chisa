import time
from typing import List, Optional, Any, Dict
from app.domain.interfaces.llm_provider import BaseLLMAdapter, StructuredPrompt
from app.domain.interfaces.cache_provider import ICacheProvider
from app.domain.services.community.transcript_formatter import ChannelTranscriptFormatter
from app.shared.utils.logger import get_logger

log = get_logger(__name__)


class CommunityTopicSummarizer:
    """
    Background worker that maintains a rolling topic summary for community channels in Redis.
    Triggered every 30 messages in a community channel to preserve multi-turn discussion context.
    """

    SUMMARY_TTL_SECONDS = 7 * 24 * 3600  # 7 days
    SUMMARIZE_INTERVAL = 30

    def __init__(self, llm: BaseLLMAdapter, cache: ICacheProvider):
        self.llm = llm
        self.cache = cache
        self.SUMMARY_SCHEMA = {
            "type": "object",
            "properties": {
                "topic_summary": {
                    "type": "string",
                    "description": "Concise standalone narrative summary in Vietnamese describing key topics, group decisions, and recent channel dynamics (50-80 words)."
                }
            },
            "required": ["topic_summary"]
        }

    def _counter_key(self, channel_id: str) -> str:
        return f"chisa:channel:{channel_id}:msg_count"

    def _summary_key(self, channel_id: str) -> str:
        return f"chisa:channel:{channel_id}:topic_summary"

    async def increment_message_count(self, channel_id: str) -> int:
        """Increment message counter for the channel in Redis."""
        key = self._counter_key(channel_id)
        try:
            val = await self.cache.get(key)
            count = (int(val) if val else 0) + 1
            await self.cache.set(key, str(count), ttl=self.SUMMARY_TTL_SECONDS)
            return count
        except Exception as e:
            log.warning("Failed to increment channel message counter in Redis", channel_id=channel_id, error=str(e))
            return 1

    async def get_topic_summary(self, channel_id: str) -> Optional[str]:
        """Fetch active topic summary from Redis."""
        if not channel_id:
            return None
        key = self._summary_key(channel_id)
        try:
            summary = await self.cache.get(key)
            return summary.strip() if summary else None
        except Exception as e:
            log.warning("Failed to fetch channel topic summary from Redis", channel_id=channel_id, error=str(e))
            return None

    async def summarize_channel_topic(
        self,
        channel_id: str,
        guild_id: str,
        messages: List[Any],
    ) -> Optional[str]:
        """
        Background execution: Calls LLM to summarize recent community discussion, merging with prior summary.
        """
        if not messages:
            return None

        log.info("Starting community topic summarization...", channel_id=channel_id, guild_id=guild_id)
        formatted_transcript = ChannelTranscriptFormatter.format_transcript(
            messages=messages,
            max_tokens=1000,
            use_smart_compression=True
        )

        if not formatted_transcript:
            return None

        previous_summary = await self.get_topic_summary(channel_id)

        if previous_summary:
            system_prompt = (
                "You are a Community Topic Summarizer for an anime AI Companion (Kuchiba Chisa) in a Discord Server.\n"
                "Your job is to UPDATE the rolling channel discussion summary by integrating new conversation messages into the previous summary.\n\n"
                "CRITICAL RULES:\n"
                "1. Output a standalone, concise narrative in Vietnamese (50-80 words) describing: what members are discussing, shared gaming/life events, or group plans.\n"
                "2. Retain important ongoing context from the previous summary while prioritizing newest discussions.\n"
                "3. Do not include individual timestamps or roleplay metadata. Focus on group topics.\n"
                "Return valid JSON matching schema: {\"topic_summary\": \"...\"}"
            )
            user_message = f"Previous summary:\n{previous_summary}\n\nNew recent channel messages:\n{formatted_transcript}"
        else:
            system_prompt = (
                "You are a Community Topic Summarizer for an anime AI Companion (Kuchiba Chisa) in a Discord Server.\n"
                "Analyze the channel discussion transcript and provide a concise narrative summary in Vietnamese (50-80 words).\n\n"
                "CRITICAL RULES:\n"
                "1. Summarize the key topics members are discussing, any ongoing banter, game matches, or server plans.\n"
                "2. Output must be a clear, standalone paragraph in Vietnamese.\n"
                "Return valid JSON matching schema: {\"topic_summary\": \"...\"}"
            )
            user_message = f"Channel messages transcript:\n{formatted_transcript}"

        prompt = StructuredPrompt(
            system=system_prompt,
            history=[],
            user_message=user_message,
            response_schema=self.SUMMARY_SCHEMA,
            temperature=0.3,
            retrieved_memories=[],
            retrieved_lore=[],
            rag_decisions={"use_deep_thinking": False}
        )

        try:
            from app.domain.context import llm_call_purpose
            llm_call_purpose.set("community_topic_summarize")
            response = await self.llm.generate(prompt)
            parsed = response.parsed or {}
            summary_text = str(parsed.get("topic_summary", "")).strip()

            if summary_text:
                await self.cache.set(
                    self._summary_key(channel_id),
                    summary_text,
                    ttl=self.SUMMARY_TTL_SECONDS
                )
                log.info("Community topic summary updated in Redis", channel_id=channel_id, summary_length=len(summary_text))
                return summary_text
            else:
                log.warning("Topic summarizer produced empty summary", channel_id=channel_id)
                return None
        except Exception as e:
            log.error("Failed to summarize community topic", channel_id=channel_id, error=str(e))
            return None
