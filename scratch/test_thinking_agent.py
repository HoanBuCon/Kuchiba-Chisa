import asyncio
import os
import sys

# Add project root to sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

from app.domain.services.chat_engine import ChatEngine
from app.domain.services.context_builder import ContextBuilder
from app.domain.services.memory_extractor import MemoryExtractor
from app.infrastructure.llm.adapters.deepseek import DeepSeekAdapter
from scratch.test_summarize import FastEmbedAdapter
from app.infrastructure.database.engine import AsyncSessionFactory, connect_database, disconnect_database
from app.infrastructure.database.repositories.user_repository import SqlAlchemyUserRepository
import uuid

async def main():
    print("=" * 70)
    print("       TESTING INFORMATION ALIGNMENT & LOOP THINKING AGENT")
    print("=" * 70)

    # Connect to DB
    await connect_database()

    try:
        # Initialize dependencies
        embedder = FastEmbedAdapter()
        llm = DeepSeekAdapter()
        context_builder = ContextBuilder()
        # MemoryExtractor needs embedder, llm and qdrant
        from app.infrastructure.vector.qdrant.qdrant_service import qdrant_service
        memory_extractor = MemoryExtractor(embedder=embedder, llm=llm, qdrant=qdrant_service)

        # Initialize ChatEngine
        chat_engine = ChatEngine(
            embedder=embedder,
            llm=llm,
            context_builder=context_builder,
            memory_extractor=memory_extractor
        )

        # Create dummy user
        user_id = str(uuid.uuid4())
        
        async with AsyncSessionFactory() as session:
            # Initialize user in database
            user_repo = SqlAlchemyUserRepository(session)
            await user_repo.get_or_create_user(uuid.UUID(user_id))
            await session.commit()

            # Factual query that will FAIL initial RAG check (requires web search)
            user_message = "Gia xang hom nay o Viet Nam cu the la bao nhieu vay Chisa?"
            print(f"\n[*] Sending user factual query: '{user_message}'")
            
            # Run chat engine cycle
            reply, emotions = await chat_engine.chat(
                session=session,
                user_id=user_id,
                user_message=user_message
            )

            print("\n" + "=" * 50)
            print("[+] Chisa final reply:")
            print(reply)
            print("-" * 50)
            print("[+] New emotion state:")
            print(emotions)
            print("=" * 50)

    finally:
        await disconnect_database()

if __name__ == "__main__":
    asyncio.run(main())
