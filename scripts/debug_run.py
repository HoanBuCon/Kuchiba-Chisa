import asyncio
import aiohttp
from scripts.scan_and_crawl_clean_wiki import scan_and_classify_pages, USER_AGENT

async def main():
    headers = {"User-Agent": USER_AGENT}
    async with aiohttp.ClientSession(headers=headers) as session:
        clean, excl = await scan_and_classify_pages(session, "Resonators")
        print(f"Clean count: {len(clean)}, Excluded count: {len(excl)}")
        for p in clean[:5]:
            print(f"  - {p['title']}")

if __name__ == "__main__":
    asyncio.run(main())
