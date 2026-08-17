import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.infrastructure.database.engine import AsyncSessionFactory, engine
from app.infrastructure.database.models import Base


async def init_db():
    print("Initializing Database Schema...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("ALTER TABLE emotion_state ADD COLUMN IF NOT EXISTS shyness FLOAT DEFAULT 0.0;"))
        await conn.execute(text("ALTER TABLE emotion_state ADD COLUMN IF NOT EXISTS curiosity FLOAT DEFAULT 0.20;"))
        await conn.execute(text("ALTER TABLE emotion_state ADD COLUMN IF NOT EXISTS comfort FLOAT DEFAULT 0.50;"))
    print("Tables & columns migrated successfully via asyncpg!")


if __name__ == "__main__":
    asyncio.run(init_db())
