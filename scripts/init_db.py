import os
import sys

# Setup PATH for local imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from app.infrastructure.database.models import Base
from app.config.settings import settings

def init_db():
    print("Initializing Database Schema...")
    # Convert async URL to sync URL for creation
    db_url = str(settings.DATABASE_URL).replace("+asyncpg", "+psycopg2")

    print(f"Connecting to: {db_url.split('@')[1]}")  # Hide password in output
    engine = create_engine(db_url)
    
    # Create tables
    Base.metadata.create_all(bind=engine)
    print("Tables created successfully!")

if __name__ == "__main__":
    init_db()
