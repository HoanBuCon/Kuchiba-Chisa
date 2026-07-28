import aiohttp
import asyncio
import time
from typing import AsyncGenerator
from datetime import datetime
from app.domain.entities.wiki import WikiPage, WikiRevision
from app.domain.interfaces.wiki_client import IWikiClient
from app.shared.utils.logger import get_logger

log = get_logger(__name__)

class MediaWikiClient(IWikiClient):
    """
    Concrete implementation of IWikiClient using Fandom's MediaWiki API.
    """
    
    def __init__(self, base_url: str = "https://wutheringwaves.fandom.com/api.php", req_per_second: float = 2.0):
        self.base_url = base_url
        self.delay = 1.0 / req_per_second
        self._last_req_time = 0.0
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

    async def _throttle(self):
        now = time.time()
        elapsed = now - self._last_req_time
        if elapsed < self.delay:
            await asyncio.sleep(self.delay - elapsed)
        self._last_req_time = time.time()

    async def get_all_pages(self) -> AsyncGenerator[WikiPage, None]:
        import time
        log.info("Starting enumeration of all wiki pages via MediaWiki API")
        
        apfrom = None
        
        async with aiohttp.ClientSession() as session:
            while True:
                await self._throttle()
                params = {
                    "action": "query",
                    "format": "json",
                    "generator": "allpages",
                    "gaplimit": "50",
                    "prop": "revisions",
                    "rvprop": "ids|timestamp"
                }
                if apfrom:
                    params["gapfrom"] = apfrom

                try:
                    async with session.get(self.base_url, params=params) as response:
                        response.raise_for_status()
                        data = await response.json()
                        
                        pages = data.get("query", {}).get("pages", {})
                        for page_id_str, page_info in pages.items():
                            page_id = int(page_id_str)
                            if page_id < 0:
                                continue # Missing page
                                
                            title = page_info.get("title", "")
                            revisions = page_info.get("revisions", [])
                            
                            if not revisions:
                                continue
                                
                            latest_rev = revisions[0]
                            rev_id = latest_rev.get("revid", 0)
                            timestamp_str = latest_rev.get("timestamp", "")
                            
                            try:
                                timestamp = datetime.strptime(timestamp_str, "%Y-%m-%dT%H:%M:%SZ")
                            except ValueError:
                                timestamp = datetime.utcnow()
                            
                            yield WikiPage(
                                page_id=page_id,
                                title=title,
                                latest_revision_id=rev_id,
                                last_updated=timestamp
                            )
                            
                        # Pagination
                        continue_data = data.get("continue")
                        if not continue_data or "gapcontinue" not in continue_data:
                            break
                        apfrom = continue_data["gapcontinue"]
                        
                except Exception as e:
                    log.error("Failed to fetch all pages page batch", error=str(e))
                    raise e

    async def download_page(self, page_id: int) -> WikiRevision:
        import time
        await self._throttle()
        
        params = {
            "action": "query",
            "format": "json",
            "prop": "revisions",
            "pageids": str(page_id),
            "rvprop": "ids|timestamp|content",
            "rvslots": "main"
        }
        
        async with aiohttp.ClientSession(headers=self.headers) as session:
            async with session.get(self.base_url, params=params) as response:
                response.raise_for_status()
                data = await response.json()
                
                pages = data.get("query", {}).get("pages", {})
                page_info = pages.get(str(page_id))
                
                if not page_info:
                    raise ValueError(f"Page ID {page_id} not found in MediaWiki response.")
                    
                title = page_info.get("title", "")
                revisions = page_info.get("revisions", [])
                
                if not revisions:
                    raise ValueError(f"No revisions found for page ID {page_id}.")
                    
                latest_rev = revisions[0]
                rev_id = latest_rev.get("revid", 0)
                timestamp_str = latest_rev.get("timestamp", "")
                
                try:
                    timestamp = datetime.strptime(timestamp_str, "%Y-%m-%dT%H:%M:%SZ")
                except ValueError:
                    timestamp = datetime.utcnow()
                
                content = ""
                slots = latest_rev.get("slots", {})
                if "main" in slots:
                    content = slots["main"].get("*", "")
                else:
                    # Fallback for older MW versions
                    content = latest_rev.get("*", "")
                
                return WikiRevision(
                    page_id=page_id,
                    title=title,
                    revision_id=rev_id,
                    content=content,
                    timestamp=timestamp
                )
