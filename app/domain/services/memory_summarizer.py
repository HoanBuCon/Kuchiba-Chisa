import logging
from app.infrastructure.llm.adapters.base import BaseLLMAdapter, StructuredPrompt
from app.domain.services.memory_manager import MemoryManager

log = logging.getLogger(__name__)

class MemorySummarizer:
    """
    Periodically compresses long conversation threads into bullet points
    and injects them into the Qdrant Long-Term Memory as summaries.
    """
    def __init__(self, llm: BaseLLMAdapter, memory_manager: MemoryManager):
        self.llm = llm
        self.memory_manager = memory_manager

    async def summarize_and_store(self, user_id: str, conv_id: str, history: list[dict[str, str]]) -> None:
        """
        Takes the recent conversation history, generates a highly condensed summary 
        using the LLM, and persists it into the LTM via MemoryManager.
        """
        # We only summarize if there is substantial context
        if len(history) < 20: 
            return
            
        log.info(f"Triggering background conversation summarization for User {user_id}")
        
        # Format the last 40 messages max for summarization to avoid token overflow
        recent_history = history[-40:]
        chat_transcript = "\n".join([f"{msg['role'].upper()}: {msg['content']}" for msg in recent_history])
        
        system_instructions = (
            "You are an AI Memory Summarizer. Extract important facts about the user and their relationship with the AI. "
            "Output concise bullet points strictly in Vietnamese. Do not output anything else. "
            "Focus on: personal facts, preferences, emotional events, and relationship progress."
        )
        
        user_prompt = f"Summarize this conversation transcript:\n\n{chat_transcript}"
        
        prompt = StructuredPrompt(
            system_prompt=system_instructions,
            user_message=user_prompt,
            response_schema=None # We want raw text output, not JSON
        )
        
        try:
            response = await self.llm.generate(prompt)
            summary_text = response.raw_response
            
            # Fallback if raw_response is empty but parsed has a string
            if not summary_text and response.parsed and "response" in response.parsed:
                summary_text = response.parsed["response"]
                
            summary_text = summary_text.strip()
                
            if summary_text and len(summary_text) > 20:
                await self.memory_manager.save_conversation_summary(
                    user_id=user_id,
                    conversation_id=conv_id,
                    summary_text=summary_text,
                    importance_score=0.8
                )
                log.info(f"Successfully summarized and stored LTM for user {user_id}")
            else:
                log.warning(f"Summarizer produced empty or very short output for user {user_id}")
                
        except Exception as e:
            log.error(f"Failed to summarize conversation for user {user_id}: {e}")
