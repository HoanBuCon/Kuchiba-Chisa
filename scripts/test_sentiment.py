import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config.settings import settings
from app.infrastructure.database.engine import AsyncSessionFactory
from app.infrastructure.llm.adapters.groq import GroqAdapter
from app.infrastructure.llm.adapters.base import StructuredPrompt
from sqlalchemy import select

async def test_classify_with_history():
    user_id = "81d42de4-d5d3-43ee-9a37-fa72fb461839"
    adapter = GroqAdapter()
    
    async with AsyncSessionFactory() as session:
        from app.infrastructure.database.models.message import Message
        import uuid
        
        result = await session.execute(
            select(Message)
            .where(Message.user_id == uuid.UUID(user_id))
            .order_by(Message.created_at.desc())
            .limit(15)
        )
        msgs = result.scalars().all()
        history = [{"role": m.role.value, "content": m.content} for m in reversed(msgs)]
        
        last_user_msg = next((m for m in reversed(history) if m['role'] == "user"), None)
        
        if not last_user_msg:
            print("No user message in history to test.")
            return
            
        print(f"Testing classification with actual user message: {last_user_msg['content']}")
        
        # Mimic _classify_emotion
        short_history = history[-4:] if len(history) >= 4 else history
        history_text = "\\n".join([f"{m['role']}: {m['content']}" for m in short_history])
        
        prompt = StructuredPrompt(
            system="""You are a strict conversational sentiment classifier for an Anime AI Chatbot named Chisa.
Analyze the user's latest message IN CONTEXT of the previous conversation. 
You must output a JSON with exactly three boolean flags:
- "is_positive": True if the user is complimenting, showing affection, teasing playfully, or expressing happiness/gratitude towards Chisa.
- "is_negative": True if the user is expressing genuine sadness, actual anger, complaining about Chisa, or saying Chisa did something wrong. IMPORTANT: Do NOT mark True for Vietnamese mock-frustration slang (e.g., 'thiệt tình', 'chịu chết', 'bó tay', 'cạn lời', 'hết cứu') used playfully.
- "is_rude": True ONLY if the user is using explicit insults, hate speech, or severe hostility (e.g., "ngu", "chết đi", "rác rưởi").

Output purely valid JSON. No markdown wrappers.""",
            history=[],
            user_message=f"Context History:\\n{history_text}\\n\\nLatest User Message: {last_user_msg['content']}",
            response_schema={
                "type": "object",
                "properties": {
                    "is_positive": {"type": "boolean"},
                    "is_negative": {"type": "boolean"},
                    "is_rude": {"type": "boolean"}
                },
                "required": ["is_positive", "is_negative", "is_rude"]
            },
            max_tokens=100,
            temperature=0.0
        )
        
        try:
            original_model = adapter._model
            adapter._model = "llama-3.1-8b-instant"
            print("Sending to Groq...")
            response = await adapter.generate(prompt)
            print(f"Success! Parsed JSON: {response.parsed}")
        except Exception as e:
            print(f"EXCEPTION CAUGHT: {repr(e)}")

if __name__ == "__main__":
    asyncio.run(test_classify_with_history())
