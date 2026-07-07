import asyncio
import os
import sys
import uuid
import time
from sqlalchemy import select, func, delete

# Add project root to sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

from app.config.settings import settings
from app.infrastructure.database.engine import AsyncSessionFactory, engine
from app.infrastructure.database.models.conversation import Conversation
from app.infrastructure.database.models.message import Message, MessageRole
from app.infrastructure.database.models.user import User
from app.infrastructure.database.models.emotion_state import EmotionState
from app.infrastructure.database.models.user_stats import UserStats

from app.domain.services.chat_engine import ChatEngine
from app.domain.interfaces.embedding_provider import IEmbeddingProvider
from app.infrastructure.llm.adapters.deepseek import DeepSeekAdapter
from app.domain.services.context_builder import ContextBuilder
from app.domain.services.memory_extractor import MemoryExtractor

class FastEmbedAdapter(IEmbeddingProvider):
    def __init__(self):
        from fastembed import TextEmbedding
        self.model = TextEmbedding(model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")

    async def embed_text(self, text: str) -> list[float]:
        embeddings = list(self.model.embed([text]))
        return embeddings[0].tolist()

async def clear_test_data(session, user_uuid):
    print("[*] Clearing existing test data for UUID:", user_uuid)
    await session.execute(delete(Message).where(Message.user_id == user_uuid))
    await session.execute(delete(Conversation).where(Conversation.user_id == user_uuid))
    await session.execute(delete(EmotionState).where(EmotionState.user_id == user_uuid))
    await session.execute(delete(UserStats).where(UserStats.user_id == user_uuid))
    await session.commit()

async def main():
    print("=" * 60)
    print("      TESTING CONVERSATION SUMMARIZATION FEATURES")
    print("=" * 60)
    
    user_id = "aa153b44-03e9-4376-974f-6373d50223c1"
    user_uuid = uuid.UUID(user_id)

    # Initialize components
    embedder = FastEmbedAdapter()
    llm = DeepSeekAdapter()
    context_builder = ContextBuilder()
    from app.infrastructure.vector.qdrant.qdrant_service import qdrant_service
    memory_extractor = MemoryExtractor(llm=llm, embedder=embedder, qdrant=qdrant_service)

    chat_engine = ChatEngine(
        embedder=embedder,
        llm=llm,
        context_builder=context_builder,
        memory_extractor=memory_extractor
    )

    async with AsyncSessionFactory() as session:
        # Step 1: Clean test data
        await clear_test_data(session, user_uuid)

        # Create user & stats & initial emotion using repositories
        from app.infrastructure.database.repositories.user_repository import SqlAlchemyUserRepository
        from app.infrastructure.database.repositories.emotion_repository import SqlAlchemyEmotionRepository
        user_repo = SqlAlchemyUserRepository(session)
        emotion_repo = SqlAlchemyEmotionRepository(session)
        await user_repo.get_or_create_user(user_uuid)
        await user_repo.get_user_stats(user_uuid)
        await emotion_repo.get_emotion_state(user_uuid)

        # Step 2: Test Manual Summarization when conversation has NO messages
        print("\n--- TEST 1: Manual summarization on empty conversation ---")
        reply, updated_emotions = await chat_engine.chat(session, user_id, "Tóm tắt cuộc trò chuyện nãy giờ đi em")
        print("🤖 Chisa Reply:", reply)
        
        # Step 3: Insert some messages to make a history
        print("\n--- Inserting mock messages ---")
        conv_id_stmt = select(Conversation).where(Conversation.user_id == user_uuid).order_by(Conversation.started_at.desc()).limit(1)
        conv = (await session.execute(conv_id_stmt)).scalar_one()
        
        mock_messages = [
            ("user", "Chào em Chisa, hôm nay anh đi học về mệt quá."),
            ("assistant", "Thương Senpai quá. Senpai hãy nghỉ ngơi đi nhé, để em pha trà Pocky cho anh."),
            ("user", "Anh thích ăn vị dâu tây đấy."),
            ("assistant", "Dạ, em biết rồi. Em sẽ chuẩn bị vị dâu tây ngọt ngào cho Senpai ạ."),
            ("user", "Em có thích nuôi mèo không Chisa?"),
            ("assistant", "Em rất thích nuôi những chú mèo con mềm mại, chơi với chúng giúp em giảm rủi ro overclocking."),
        ]
        
        for role, text in mock_messages:
            enum_role = MessageRole.USER if role == "user" else MessageRole.ASSISTANT
            msg = Message(
                id=uuid.uuid4(),
                conversation_id=conv.id,
                user_id=user_uuid,
                role=enum_role,
                content=text,
                is_success=True
            )
            session.add(msg)
        await session.commit()

        # Step 4: Test Manual Summarization with history
        print("\n--- TEST 2: Manual summarization with history ---")
        reply, updated_emotions = await chat_engine.chat(session, user_id, "Em tóm tắt cuộc trò chuyện của chúng ta nãy giờ đi")
        print("🤖 Chisa Reply:")
        print(reply)
        
        # Refresh and check summary from DB
        await session.refresh(conv)
        print("\n[+] Conversation summary in DB after Test 2:")
        print(conv.summary)
        assert conv.summary is not None, "Conversation summary should be populated!"

        # Step 5: Test Auto-Summarization
        # Let's insert more messages to exceed 20 messages limit
        print("\n--- Inserting 20 more messages to trigger Auto-Summarize ---")
        # Clear existing summary
        conv.summary = None
        await session.commit()
        
        for i in range(15):
            msg_u = Message(
                id=uuid.uuid4(),
                conversation_id=conv.id,
                user_id=user_uuid,
                role=MessageRole.USER,
                content=f"Tin nhắn thứ {i} của user",
                is_success=True
            )
            msg_a = Message(
                id=uuid.uuid4(),
                conversation_id=conv.id,
                user_id=user_uuid,
                role=MessageRole.ASSISTANT,
                content=f"Tin nhắn thứ {i} của Chisa",
                is_success=True
            )
            session.add(msg_u)
            session.add(msg_a)
        await session.commit()

        # Count messages to verify
        msg_count = (await session.execute(select(func.count(Message.id)).where(Message.conversation_id == conv.id))).scalar()
        print(f"Total messages now: {msg_count}")
        
        print("\n--- TEST 3: Sending a normal query to trigger auto-summarization ---")
        # Send a normal query, which should NOT route to tool but should trigger auto-summarize background task
        reply, updated_emotions = await chat_engine.chat(session, user_id, "Hôm nay em ăn gì chưa Chisa?")
        print("🤖 Chisa Reply:", reply)
        
        print("[*] Waiting 5 seconds for background auto-summarize task to finish...")
        await asyncio.sleep(5.0)

        # Refresh database session and query conversation summary
        async with AsyncSessionFactory() as fresh_session:
            fresh_conv = (await fresh_session.execute(select(Conversation).where(Conversation.id == conv.id))).scalar_one()
            print("\n[+] Conversation summary in DB after Auto-summarize:")
            print(fresh_conv.summary)
            assert fresh_conv.summary is not None, "Conversation summary should be auto-generated in the background!"
            print("\n[✓] Auto-summarization test passed successfully!")

        # Clean up
        await clear_test_data(session, user_uuid)

if __name__ == "__main__":
    asyncio.run(main())
