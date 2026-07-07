import sys
import os
import json
sys.path.append(os.getcwd())

# Force UTF-8 encoding
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.config.settings import settings
from app.infrastructure.embeddings.fastembed_adapter import FastEmbedAdapter
from app.infrastructure.llm.adapters.deepseek import DeepSeekAdapter
from app.domain.services.context_builder import ContextBuilder
from app.domain.services.state_manager import StateManager
from app.domain.services.memory_extractor import MemoryExtractor
from app.domain.services.chat_engine import ChatEngine
from app.domain.services.rag.retriever_lore import LoreRetriever
from app.infrastructure.vector.qdrant.qdrant_service import qdrant_service

async def debug_response():
    # Setup database
    database_url = settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
    engine = create_async_engine(database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    # Initialize components
    embedder = FastEmbedAdapter()
    llm = DeepSeekAdapter()
    context_builder = ContextBuilder()
    memory_extractor = MemoryExtractor(llm=llm, embedder=embedder, qdrant=qdrant_service)
    
    chat_engine = ChatEngine(
        embedder=embedder,
        llm=llm,
        context_builder=context_builder,
        memory_extractor=memory_extractor
    )
    
    user_id = "bb153b44-03e9-4376-974f-6373d50223c1"
    user_message = "Cái vòng ở cổ em dùng làm gì?"
    
    async with async_session() as session:
        query_vector = await embedder.embed_text(user_message)
        intents = await chat_engine.intent_classifier.classify(user_message, query_vector)
        print("Matched Intents:", [i.value for i in intents])
        
        # Retrieve lore
        lore_retriever = LoreRetriever()
        lore_chunks = await lore_retriever.retrieve_lore_parent_child(
            collection="character_lore",
            query_vector=query_vector,
            query_text=user_message,
            top_k=6,
            score_threshold=0.35
        )
        print("Retrieved lore chunks count:", len(lore_chunks))
        
        # Build prompt using REAL history and stats from database
        history = await chat_engine.get_history(session, user_id)
        stats = await chat_engine.get_history(session, user_id) # ensure user stats exist
        emotion = await chat_engine.get_emotion_state(session, user_id)
        
        # Assemble custom prompt with format_section at the VERY END of the system prompt
        state_section = StateManager.format_state(emotion, 0.0)
        
        lore_text = ""
        if lore_chunks:
            lore_text = "[LORE]\n" + "\n".join([f"- {l}" for l in lore_chunks])
            
        format_section = (
            "[OUTPUT FORMAT]\n"
            "Bạn BẮT BUỘC phải phản hồi dưới dạng một đối tượng JSON tuân thủ định dạng sau:\n"
            "{\n"
            '  "response": "câu thoại phản hồi của Chisa (chứa cảm xúc phù hợp, viết bằng tiếng Việt)",\n'
            '  "user_sentiment": {\n'
            '    "is_positive": true/false,\n'
            '    "is_negative": true/false,\n'
            '    "is_rude": true/false,\n'
            '    "is_neutral": true/false\n'
            '  },\n'
            '  "chisa_sentiment": {\n'
            '    "is_sad": true/false,\n'
            '    "is_happy": true/false,\n'
            '    "is_annoyed": true/false,\n'
            '    "is_flustered": true/false\n'
            '  }\n'
            "}"
        )
        
        system_parts = [
            "[PERSONA]",
            chat_engine.context_builder.PERSONA_TEXT,
            "",
            state_section
        ]
        if lore_text:
            system_parts.extend(["", lore_text])
            
        # Put format section at the very end
        system_parts.extend(["", format_section])
        
        system_prompt = "\n".join(system_parts)
        
        # Call DeepSeek via HTTPX with json_object response format
        url = f"{llm._base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {llm._api_key}"
        }
        
        messages = [
            {"role": "system", "content": system_prompt},
        ]
        # Include history with assistant messages formatted as JSON
        for h in history:
            role = h.get("role")
            content = h.get("content")
            if role == "assistant" and not content.strip().startswith("{"):
                assistant_json = {
                    "response": content,
                    "user_sentiment": {
                        "is_positive": False,
                        "is_negative": False,
                        "is_rude": False,
                        "is_neutral": True
                    },
                    "chisa_sentiment": {
                        "is_sad": False,
                        "is_happy": False,
                        "is_annoyed": False,
                        "is_flustered": False
                    }
                }
                content = json.dumps(assistant_json, ensure_ascii=False)
            messages.append({"role": role, "content": content})
            
        messages.append({"role": "user", "content": user_message})
        
        payload = {
            "model": llm._model,
            "messages": messages,
            "max_tokens": llm._max_tokens,
            "temperature": llm._temperature,
            "response_format": {"type": "json_object"}
        }
        
        import httpx
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            print("\nHTTP Status:", response.status_code)
            res_json = response.json()
            choice = res_json["choices"][0]
            content = choice["message"].get("content")
            reasoning = choice["message"].get("reasoning_content")
            print("Reasoning Content:")
            print(reasoning)
            print("\nContent:")
            print(content)
            if content:
                try:
                    json.loads(content)
                    print("\nResult: VALID JSON")
                except Exception as e:
                    print("\nResult: INVALID JSON -", str(e))
            else:
                print("\nResult: CONTENT IS EMPTY/NONE")

if __name__ == "__main__":
    asyncio.run(debug_response())
