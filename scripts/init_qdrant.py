import asyncio
import sys
import os

sys.path.append(os.getcwd())

from app.infrastructure.vector.qdrant.qdrant_service import qdrant_service

async def main():
    print("Initializing Qdrant collections for dimension 384...")
    await qdrant_service.initialize_all_collections()

if __name__ == "__main__":
    asyncio.run(main())
