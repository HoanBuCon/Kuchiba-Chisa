import asyncio
import uuid
import sys
import os

sys.path.append(os.getcwd())

from app.infrastructure.database.engine import AsyncSessionFactory
from app.infrastructure.database.models.user import User
from app.domain.services.chat_engine import ChatEngine
from app.infrastructure.llm.adapters.groq import GroqAdapter
from app.infrastructure.embeddings.fastembed_adapter import FastEmbedAdapter
from sqlalchemy import select

async def main():
    async with AsyncSessionFactory() as session:
        # Fetch an existing user UUID
        stmt = select(User).limit(1)
        user = (await session.execute(stmt)).scalar_one_or_none()
        if not user:
            print("No users found.")
            return
            
        print(f"Testing ChatEngine with User ID: {user.id}")
        
        embedder = FastEmbedAdapter()
        llm = GroqAdapter()
        engine = ChatEngine(embedder, llm)
        
        try:
            print("Triggering chat()...")
            response = await engine.chat(session, str(user.id), "Hello Chisa")
            print(f"Success! Response: {response}")
        except Exception as e:
            print("================ EXCEPTION ================")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
