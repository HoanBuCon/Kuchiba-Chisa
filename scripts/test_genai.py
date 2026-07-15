import asyncio
from google import genai
from app.config.settings import settings

def main():
    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    models = list(client.models.list())
    for m in models:
        print(m.name)
            
main()
