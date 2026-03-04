import asyncio
import httpx
import sys
import os
import uuid

# Ensure we can run standalone
sys.path.append(os.getcwd())

from app.infrastructure.database.engine import AsyncSessionFactory
from app.infrastructure.database.models.user import User
from sqlalchemy import select

async def setup_users() -> tuple[str, str]:
    """Creates dummy users and returns their UUIDs"""
    async with AsyncSessionFactory() as session:
        # Check if they exist to avoid unique constraint errors on re-runs
        stmt = select(User).where(User.username.in_(["test_discord_user", "test_web_user"]))
        existing = (await session.execute(stmt)).scalars().all()
        
        user_ids = []
        if len(existing) < 2:
            u1 = User(id=uuid.uuid4(), username="test_discord_user", discord_id="123")
            u2 = User(id=uuid.uuid4(), username="test_web_user")
            session.add_all([u1, u2])
            await session.commit()
            print(f"Created dummy users: {u1.id}, {u2.id}")
            return str(u1.id), str(u2.id)
        else:
            print(f"Found existing dummy users: {existing[0].id}, {existing[1].id}")
            return str(existing[0].id), str(existing[1].id)


async def main():
    print("🚀 Testing Chisa API /chat Endpoint...")
    
    uid_1, uid_2 = await setup_users()
    
    url = "http://localhost:8000/api/v1/chat"
    
    payload_user1 = {
        "user_id": uid_1,
        "message": "Hello Chisa! I'm feeling a bit down today..."
    }
    
    payload_user2 = {
        "user_id": uid_2,
        "message": "Hey Chisa, I just got a promotion at work!"
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        # Test User 1
        print(f"\n=== Testing User 1 ({uid_1}) ===")
        print(f"Message: {payload_user1['message']}")
        try:
            response = await client.post(url, json=payload_user1)
            response.raise_for_status()
            data = response.json()
            print(f"🤖 Chisa: {data['response']}")
        except Exception as e:
            print(f"❌ Failed: {e}")
            if hasattr(e, 'response') and e.response:
                print(e.response.text)
                
        # Test User 2
        print(f"\n=== Testing User 2 ({uid_2}) ===")
        print(f"Message: {payload_user2['message']}")
        try:
            response = await client.post(url, json=payload_user2)
            response.raise_for_status()
            data = response.json()
            print(f"🤖 Chisa: {data['response']}")
        except Exception as e:
            print(f"❌ Failed: {e}")
            if hasattr(e, 'response') and e.response:
                print(e.response.text)

if __name__ == "__main__":
    asyncio.run(main())
