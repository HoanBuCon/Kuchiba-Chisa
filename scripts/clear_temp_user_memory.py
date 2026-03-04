import asyncio
import sys
import os

sys.path.append(os.getcwd())

from app.infrastructure.database.engine import AsyncSessionFactory
from app.infrastructure.database.models.user import User
from app.infrastructure.database.models.message import Message
from app.infrastructure.database.models.conversation import Conversation
from app.infrastructure.database.models.emotion_state import EmotionState
from app.infrastructure.database.models.user_stats import UserStats
from app.infrastructure.vector.qdrant.qdrant_service import get_qdrant_client
from sqlalchemy import select, delete

async def main():
    async with AsyncSessionFactory() as session:
        # Find temp user
        stmt = select(User).where(User.username == "terminal_temp_user")
        user = (await session.execute(stmt)).scalar_one_or_none()
        
        if not user:
            print("❌ No terminal_temp_user found in database. You need to chat via interactive_chat.py first!")
            return
            
        user_id = str(user.id)
        print(f"[*] Found terminal_temp_user (UUID: {user_id})")
        
        # 1. Clear PostgreSQL Short-Term Memory
        print("[*] Wiping Short-Term Memory and Conversations (PostgreSQL)...")
        await session.execute(delete(Message).where(Message.user_id == user.id))
        await session.execute(delete(Conversation).where(Conversation.user_id == user.id))
        
        # 2. Reset Emotions and Stats back to baseline (0.0)
        print("[*] Resetting Emotional State & User Stats attachment...")
        await session.execute(delete(EmotionState).where(EmotionState.user_id == user.id))
        await session.execute(delete(UserStats).where(UserStats.user_id == user.id))
        
        await session.commit()
        
        # 3. Clear Qdrant Long-Term Memory
        print("[*] Wiping Long-Term Memory Vectors (Qdrant)...")
        try:
            from qdrant_client.http import models
            client = get_qdrant_client()
            
            collections = [
                "emotional_memories", 
                "conversation_summaries", 
                "persona_embeddings", 
                "user_facts"
            ]
            
            for col in collections:
                try:
                    await client.delete(
                        collection_name=col,
                        points_selector=models.FilterSelector(
                            filter=models.Filter(
                                must=[
                                    models.FieldCondition(
                                        key="user_id", 
                                        match=models.MatchValue(value=user_id)
                                    )
                                ]
                            )
                        )
                    )
                    print(f"    - Cleared assigned vectors in `{col}`")
                except Exception as e:
                    pass
        except Exception as q_err:
            print(f"⚠️ Warning: Could not clear Qdrant vectors: {q_err}")

        print("\n✅ Successfully wiped all memory, emotions, and stats for terminal_temp_user!")
        print("You can now start a totally fresh conversation where Chisa won't remember anything.")

if __name__ == "__main__":
    asyncio.run(main())
