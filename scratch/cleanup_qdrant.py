import asyncio
from qdrant_client import AsyncQdrantClient

async def main():
    client = AsyncQdrantClient(url="http://localhost:6333")
    try:
        collections_response = await client.get_collections()
        for col in collections_response.collections:
            print(f"Deleting collection: {col.name}")
            await client.delete_collection(col.name)
        print("All collections deleted successfully.")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(main())
