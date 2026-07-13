import asyncio
import sys
import os

sys.path.append(os.getcwd())

from app.infrastructure.vector.qdrant.qdrant_service import qdrant_service
from app.config.settings import settings

async def main():
    print(f"Initializing Qdrant collections for dimension {settings.QDRANT_EMBEDDING_DIM}...")
    await qdrant_service.initialize_all_collections()

if __name__ == "__main__":
    asyncio.run(main())
