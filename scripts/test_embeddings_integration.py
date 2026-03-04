import asyncio
import os
import sys

# Add project root to path
sys.path.append(os.getcwd())

from app.infrastructure.embeddings.fastembed_adapter import FastEmbedAdapter
from app.infrastructure.vector.qdrant.qdrant_service import qdrant_service, MemoryPayload

async def main():
    print("🚀 Initializing FastEmbed Adapter...")
    adapter = FastEmbedAdapter()
    
    text = "Chisa loves eating strawberry cake."
    print(f"Embedding text: '{text}'")
    
    vector = await adapter.embed_text(text)
    print(f"✅ Generated Vector! Dimension count: {len(vector)}")
    print(f"Sample data (first 5 floats): {vector[:5]}")
    
    assert len(vector) == 384, f"Expected 384 dimensions, got {len(vector)}!"
    
    print("\n🚀 Connecting to Qdrant Docker container...")
    is_healthy = await qdrant_service.health_check()
    if not is_healthy:
        print("❌ Qdrant is offline. Make sure Docker is running.")
        return
        
    print("✅ Qdrant Connected. Creating 'test_fastembed' collection...")
    await qdrant_service.create_collection("test_fastembed", vector_size=384)
    
    print("📦 Creating Payload...")
    import time
    import uuid
    
    point_id = str(uuid.uuid4())
    payload = MemoryPayload(
        user_id="user_test_123",
        conversation_id="conv_test_123",
        memory_type="test_fact",
        importance_score=0.9,
        created_at=int(time.time()),
        text_content=text
    )
    
    print("💾 Upserting Vector to Qdrant...")
    await qdrant_service.upsert_memory("test_fastembed", point_id, vector, payload)
    
    print("🔍 Testing Retrieval...")
    results = await qdrant_service.search_by_user("test_fastembed", vector, "user_test_123")
    
    if results:
        top_result = results[0]
        print(f"✅ Retrieval Success! Got Score: {top_result['score']}")
        print(f"Payload Matched:\n{top_result['payload']}")
    else:
        print("❌ Retrieval failed!")

if __name__ == "__main__":
    asyncio.run(main())
