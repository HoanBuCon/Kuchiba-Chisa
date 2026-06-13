import asyncio
import httpx
import sys
import os
import uuid

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Ensure we can run standalone
sys.path.append(os.getcwd())

from app.infrastructure.database.engine import AsyncSessionFactory
from app.infrastructure.database.models.user import User
from sqlalchemy import select

async def setup_users() -> str:
    """Creates dummy user and returns UUID"""
    async with AsyncSessionFactory() as session:
        stmt = select(User).where(User.username == "test_pipeline_user")
        existing = (await session.execute(stmt)).scalars().first()
        
        if not existing:
            u = User(id=uuid.uuid4(), username="test_pipeline_user", discord_id="999")
            session.add(u)
            await session.commit()
            print(f"[+] Created test user: {u.id}")
            return str(u.id)
        else:
            print(f"[i] Found existing test user: {existing.id}")
            return str(existing.id)

async def test_chat(client: httpx.AsyncClient, url: str, user_id: str, message: str, pipeline: str) -> None:
    print(f"\n---> Message [{pipeline.upper()}]: '{message}'")
    payload = {
        "user_id": user_id,
        "message": message,
        "pipeline": pipeline
    }
    try:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
        print(f"🤖 Chisa ({pipeline}): {data['response']}")
        if data.get("emotions"):
            print(f"   Emotions: {data['emotions']}")
    except Exception as e:
        print(f"[FAIL] Chat failed: {e}")
        if hasattr(e, 'response') and e.response:
            print(e.response.text)

async def main():
    print("=" * 60)
    print(" PIPELINE ROUTING AND PRODUCTION PIPELINE VERIFICATION")
    print("=" * 60)
    
    user_id = await setup_users()
    url = "http://127.0.0.1:8000/api/v1/chat"
    clear_url = f"http://127.0.0.1:8000/api/v1/chat/clear/{user_id}"
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        # 1. Clear user memory first to ensure clean state
        print("\n[1] Clearing user memory to ensure fresh start...")
        try:
            res = await client.delete(clear_url)
            print(f"    Status: {res.json().get('message')}")
        except Exception as e:
            print(f"    Failed to clear memory: {e}")
            
        await asyncio.sleep(5)

        # 2. Test Legacy Pipeline
        print("\n[2] Testing Legacy Pipeline...")
        await test_chat(client, url, user_id, "Chào Chía Chía!", "legacy")
        await asyncio.sleep(20)
        
        # 3. Test Production Pipeline - Small Talk (OTHER)
        print("\n[3] Testing Production Pipeline - Small Talk...")
        await test_chat(client, url, user_id, "Chào em, hôm nay trời đẹp thế!", "production")
        await asyncio.sleep(20)
        
        # 4. Test Production Pipeline - Character Lore (CHARACTER_LORE)
        print("\n[4] Testing Production Pipeline - Character Lore RAG...")
        await test_chat(client, url, user_id, "Giới thiệu bản thân đi em. Em sử dụng vũ khí gì?", "production")
        await asyncio.sleep(20)
        
        # 5. Test Production Pipeline - World Lore (WORLD_LORE)
        print("\n[5] Testing Production Pipeline - World Lore RAG...")
        await test_chat(client, url, user_id, "Sonoro Sphere là cái gì thế hả em?", "production")
        await asyncio.sleep(20)
        
        # 6. Test Production Pipeline - Story Lore (STORY_LORE)
        print("\n[6] Testing Production Pipeline - Story Lore RAG...")
        await test_chat(client, url, user_id, "Kể cho anh nghe về cốt truyện của Chapter 3 đi.", "production")
        await asyncio.sleep(20)
        
        # 7. Test Production Pipeline - Fact Sharing (should extract memory)
        print("\n[7] Sharing a new personal fact (should trigger memory extraction)...")
        await test_chat(client, url, user_id, "Ngày mai anh chuẩn bị phỏng vấn ở Viettel đấy.", "production")
        
        # Wait a moment for background fact extraction task to complete
        print("\n[i] Waiting 15 seconds for background memory extraction to run...")
        await asyncio.sleep(15)
        
        # 8. Test Production Pipeline - Memory Recall (MEMORY)
        print("\n[8] Testing Recall of Extracted Memory...")
        await test_chat(client, url, user_id, "Ngày mai anh làm gì em nhớ không?", "production")

if __name__ == "__main__":
    asyncio.run(main())
