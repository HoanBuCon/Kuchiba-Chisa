import asyncio
import sys
import os

sys.path.append(os.getcwd())

from qdrant_client import AsyncQdrantClient
from app.config.settings import settings

async def main():
    client = AsyncQdrantClient(url=settings.QDRANT_URL, timeout=10)
    collections = ["emotional_memories", "conversation_summaries", "persona_embeddings", "user_facts"]
    for col in collections:
        try:
            await client.delete_collection(col)
            print(f"Deleted collection: {col}")
        except Exception as e:
            print(f"Failed to delete {col}: {e}")

if __name__ == "__main__":
    asyncio.run(main())
