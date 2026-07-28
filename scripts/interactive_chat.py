import asyncio
import httpx
import uuid
import sys
import os

# Ensure we can run standalone
sys.path.append(os.getcwd())

from app.infrastructure.database.engine import AsyncSessionFactory
from app.infrastructure.database.models.user import User
from sqlalchemy import select

async def get_or_create_temp_user() -> str:
    """Creates a temporary user in the database to test the isolated chat flow."""
    async with AsyncSessionFactory() as session:
        # Check if the temp user already exists
        stmt = select(User).where(User.username == "terminal_temp_user")
        user = (await session.execute(stmt)).scalar_one_or_none()
        
        if not user:
            user = User(id=uuid.uuid4(), username="terminal_temp_user", discord_id="terminal:temp")
            session.add(user)
            await session.commit()
            print(f"[*] Created new Temp User in Database (UUID: {user.id})")
        else:
            print(f"[*] Found existing Temp User in Database (UUID: {user.id})")
            
        return str(user.id)

async def main():
    print("========================================")
    print("🌸 CHISA AI - INTERACTIVE TERMINAL CHAT 🌸")
    print("========================================\n")
    
    # Setup temporary user
    user_id = await get_or_create_temp_user()
    
    url = "http://localhost:8000/api/v1/chat"
    
    print("\n[*] Connecting to API Server...")
    print("[*] Type 'quit' or 'exit' to stop chatting.\n")
    print("-" * 40)
    
    async with httpx.AsyncClient(timeout=120.0) as client:
        while True:
            try:
                user_input = input("👤 You: ")
                if user_input.lower() in ('quit', 'exit'):
                    print("\n🌸 Chisa: Goodbye! See you next time~")
                    break
                    
                if not user_input.strip():
                    continue

                payload = {
                    "user_id": user_id,
                    "message": user_input
                }
                
                # Send to Fastapi
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                
                print(f"🤖 Chisa: {data['response']}\n")
                
            except httpx.HTTPStatusError as e:
                print(f"\n❌ API Error: HTTP {e.response.status_code}")
                print(f"Details: {e.response.text}\n")
            except httpx.RequestError as e:
                print(f"\n❌ Connection Error: Is the Uvicorn server running on port 8000?")
                print(f"Details: {str(e)}\n")
            except KeyboardInterrupt:
                print("\n\n🌸 Chisa: Interrupted! Goodbye~")
                break

if __name__ == "__main__":
    asyncio.run(main())
