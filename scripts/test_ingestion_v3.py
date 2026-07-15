import asyncio
import os
import sys

sys.path.append(os.getcwd())

from app.domain.entities.wiki import DownloadedPage
from app.infrastructure.tasks.ingestion_tasks import _async_process_page

async def run_test():
    # 1. Create a dummy markdown file
    test_file_path = "data/raw_wiki/test_page.md"
    os.makedirs(os.path.dirname(test_file_path), exist_ok=True)
    
    with open(test_file_path, "w", encoding="utf-8") as f:
        f.write("""
{{Infobox character
|name = Jiyan
|region = Huanglong
|faction = Midnight Rangers
}}

Jiyan is the leader of the Midnight Rangers.

## Combat
Jiyan uses a Broadblade. He is very strong.

## Voice Lines
- "Hello there."
- "Let's move."
""")

    # 2. Create a dummy DownloadedPage
    page = DownloadedPage(
        page_id=999999,
        title="Jiyan",
        revision_id=101,
        url="https://wutheringwaves.fandom.com/wiki/Jiyan",
        file_path=test_file_path
    )
    
    from app.infrastructure.vector.qdrant.qdrant_service import qdrant_service
    await qdrant_service.initialize_all_collections()

    print(f"Running V3 Pipeline for {page.title} (Page ID: {page.page_id})")
    
    # 3. Run the pipeline
    await _async_process_page(page)
    
    print("Test finished. Check logs for details.")

if __name__ == "__main__":
    asyncio.run(run_test())
