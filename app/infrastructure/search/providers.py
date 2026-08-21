import urllib.parse
import re
import asyncio
import httpx
from typing import Optional, List

from app.domain.interfaces.search_provider import ISearchProvider, SearchResult
from app.config.settings import settings
from app.infrastructure.logging.logger import get_logger

log = get_logger(__name__)

COMMON_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
}

class TavilySearchProvider(ISearchProvider):
    def __init__(self, http_client: httpx.AsyncClient):
        self._http_client = http_client

    @property
    def name(self) -> str:
        return "tavily"

    async def search(self, query: str) -> Optional[SearchResult]:
        if not (settings.ENABLE_PAID_SEARCH and settings.TAVILY_API_KEY):
            return None
        
        try:
            log.info("Trying Tavily Search API...")
            res = await self._http_client.post(
                "https://api.tavily.com/search",
                json={"api_key": settings.TAVILY_API_KEY, "query": query, "max_results": 4},
                timeout=3.5,
                headers=COMMON_HEADERS
            )
            if res.status_code == 200:
                data = res.json()
                results = data.get("results", [])
                snippets = [r.get("content", "") for r in results if r.get("content")]
                urls = [r.get("url", "") for r in results if r.get("url")]
                if snippets:
                    log.info("Tavily Search API succeeded")
                    return SearchResult(snippets=snippets, urls=urls, provider=self.name)
        except Exception as ex:
            log.warning("Tavily Search failed", error=str(ex))
        return None

class SerperSearchProvider(ISearchProvider):
    def __init__(self, http_client: httpx.AsyncClient):
        self._http_client = http_client

    @property
    def name(self) -> str:
        return "serper"

    async def search(self, query: str) -> Optional[SearchResult]:
        if not (settings.ENABLE_PAID_SEARCH and settings.SERPER_API_KEY):
            return None
            
        try:
            log.info("Trying Serper Search API...")
            headers = {**COMMON_HEADERS, "X-API-KEY": settings.SERPER_API_KEY, "Content-Type": "application/json"}
            res = await self._http_client.post(
                "https://google.serper.dev/search",
                headers=headers,
                json={"q": query, "num": 4},
                timeout=3.5
            )
            if res.status_code == 200:
                data = res.json()
                results = data.get("organic", [])
                snippets = [r.get("snippet", "") for r in results if r.get("snippet")]
                urls = [r.get("link", "") for r in results if r.get("link")]
                if snippets:
                    log.info("Serper Search API succeeded")
                    return SearchResult(snippets=snippets, urls=urls, provider=self.name)
        except Exception as ex:
            log.warning("Serper Search failed", error=str(ex))
        return None

class DDGScraperSearchProvider(ISearchProvider):
    def __init__(self, http_client: httpx.AsyncClient):
        self._http_client = http_client

    @property
    def name(self) -> str:
        return "html_scraper"

    def _parse_snippets(self, html: str) -> List[str]:
        patterns = [
            r'<a class="result__snippet"[^>]*>(.*?)</a>',
            r'<div class="result__snippet"[^>]*>(.*?)</div>',
            r'class="result__body"[^>]*>(.*?)</div>',
        ]
        for pattern in patterns:
            raw = re.findall(pattern, html, re.DOTALL)
            if raw:
                cleaned = []
                import html as html_lib
                for s in raw:
                    c = re.sub(r'<[^>]+>', '', s)
                    c = html_lib.unescape(c)
                    c = re.sub(r'\s+', ' ', c).strip()
                    if c and len(c) >= 25:
                        cleaned.append(c)
                if cleaned:
                    return cleaned
        return []

    def _extract_urls(self, html: str) -> List[str]:
        urls = []
        matches = re.findall(r'href="([^"]*uddg=[^"]*)"', html)
        for m in matches:
            try:
                parsed = urllib.parse.urlparse(m)
                query_params = urllib.parse.parse_qs(parsed.query)
                if 'uddg' in query_params:
                    u = query_params['uddg'][0]
                    if u not in urls:
                        urls.append(u)
            except Exception:
                pass
        if not urls:
            matches = re.findall(r'href="(https?://[^"]+)"', html)
            for m in matches:
                if "duckduckgo.com" not in m and m not in urls:
                    urls.append(m)
        return urls

    async def search(self, query: str) -> Optional[SearchResult]:
        try:
            log.info("Running DDG HTML scraper fallback...")
            url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
            response = await self._http_client.get(url, timeout=5.0, headers=COMMON_HEADERS)
            if 200 <= response.status_code < 300:
                snippets = self._parse_snippets(response.text)
                urls = self._extract_urls(response.text)
                if snippets:
                    log.info("DDG HTML scraper fallback succeeded")
                    return SearchResult(snippets=snippets, urls=urls, provider=self.name)
        except Exception as ex:
            log.error("DDG HTML scraper failed", error=str(ex))
        return None
