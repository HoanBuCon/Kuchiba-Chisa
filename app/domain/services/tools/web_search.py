import re
from typing import Any, Dict, List, Callable, Awaitable
from app.domain.interfaces.llm_provider import BaseLLMAdapter, StructuredPrompt
from app.domain.interfaces.embedding_provider import IEmbeddingProvider
from app.domain.services.tools.base import BaseAgentTool
from app.domain.tuning.rag import RAGTuning
from app.config.settings import settings
from app.shared.utils.logger import get_logger

log = get_logger(__name__)


def web_search_trace_payload(
    res: Dict[str, Any],
    *,
    source: str,
    original_message: str = "",
) -> Dict[str, Any]:
    """Chuẩn hóa payload cho pipeline visualizer."""
    return {
        "source": source,
        "original_message": original_message,
        "optimized_query": res.get("optimized_query") or res.get("search_query") or "",
        "status": res.get("status", "unknown"),
        "provider": res.get("provider", "unknown"),
        "snippets": res.get("snippets") or [],
        "source_urls": res.get("source_urls") or [],
        "deep_page_url": res.get("deep_page_url"),
        "deep_page_preview": res.get("deep_page_preview"),
        "full_result": res.get("message", ""),
    }


class WebSearchAgentTool(BaseAgentTool):
    """
    Agent tool for performing DuckDuckGo searches and query optimization.
    """
    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return "Tìm kiếm thông tin cập nhật hoặc thông tin thực tế mới nhất trên Internet qua DuckDuckGo."

    @property
    def anchors(self) -> List[str]:
        return [
            # --- Ra lệnh tìm kiếm tường minh ---
            "tra mạng giúp anh tin tức này",
            "tìm kiếm internet xem thế nào",
            "lên mạng tìm hiểu xem sao",
            "search google giúp anh với",
            "tra cứu giúp anh sự kiện này",
            "em tìm giúp anh thông tin này trên mạng",
            "lên web xem thử xem sao",
            "check giúp anh cái này đi",
            "xem thử trên mạng xem có gì không",
            "kiểm tra xem trên internet có thông tin gì chưa",
            "tìm xem bây giờ có gì mới không",
            "tra xem sự kiện này thế nào",
            "tra cứu google xem tin tức wuthering waves hôm nay",
            "search thông tin sự kiện mới trên mạng giúp anh",
            "tra giúp anh tin tức này",
            # --- Thông tin thực tế / thời gian thực ---
            "khi nào game cập nhật phiên bản mới nhất",
            "phiên bản tiếp theo ra mắt bao giờ vậy",
            "banner mới nhất hiện tại là nhân vật nào",
            "lịch sự kiện tháng này thế nào",
            "tin tức mới nhất về wuthering waves",
            "phiên bản 3.5 ra bao giờ vậy",
            "lịch update game tháng tới ra sao",
            "sự kiện game gần đây có gì mới không",
            "thông tin leak về nhân vật sắp ra",
            "patch note phiên bản mới có gì thay đổi",
            "có nhiều ưu đãi gì trong sự kiện này không",
            "giải thưởng của giải đấu wuthering waves hiện tại là gì",
            "cập nhật mới nhất của wuthering waves có những gì",
            "tìm kiếm xem sự kiện leak có gì không",
            "lên mạng tìm hiểu thông tin wuthering waves",
        ]

    async def execute(
        self,
        user_id: str,
        user_message: str,
        llm: BaseLLMAdapter,
        embedder: IEmbeddingProvider,
        **kwargs
    ) -> Dict[str, Any]:
        import hashlib
        import json
        import asyncio

        cache = kwargs.get("cache")
        
        search_query = user_message.strip()
        log.info("Executing search query", query=search_query)

        # ── Redis Cache Lookup ──
        h = hashlib.md5(search_query.encode("utf-8")).hexdigest()
        cache_key = f"chisa:search_cache:{h}"
        try:
            cached = None
            if cache:
                cached = await cache.get(cache_key)

            if cached:
                log.info("Redis search cache hit ✓", query=search_query)
                res = json.loads(cached)
                res["optimized_query"] = search_query
                return res
        except Exception as e:
            log.warning("Failed to read from search cache", error=str(e))

        # Execute search and cache results
        res = await self._web_search(search_query)
        res["optimized_query"] = search_query

        if res.get("status") == "success":
            try:
                # Cache successful search results for 2 hours (7200s)
                if cache:
                    await cache.set(cache_key, json.dumps(res), ttl=7200)
            except Exception as e:
                log.warning("Failed to save search result to cache", error=str(e))

        return res


    @staticmethod
    def _clean_html_to_text(html: str) -> str:
        """
        Industry-Standard Web Content Extractor (Trafilatura + Link-Density Fallback).
        Extracts high-signal article body, tables, and facts while stripping boilerplate, 
        navbars, menus, and footers without any language hardcoding.
        """
        if not html:
            return ""
        
        # 1. Primary: Trafilatura (State-of-the-art Content Extractor for LLM/NLP pipelines)
        try:
            import trafilatura
            extracted = trafilatura.extract(
                html,
                include_comments=False,
                include_tables=True,
                no_fallback=False
            )
            if extracted and len(extracted.strip()) >= 50:
                return extracted.strip()
        except Exception:
            pass

        # 2. Fallback: First-Principles Link-to-Text Density Extractor
        import html as html_module
        text = re.sub(r"<!--.*?-->", " ", html, flags=re.DOTALL)
        text = re.sub(
            r"<(script|style|nav|header|footer|aside|noscript|form|svg|button|iframe|select|option)[^>]*>.*?</\1>",
            " ",
            text,
            flags=re.DOTALL | re.IGNORECASE,
        )
        
        paragraphs = []
        h1_match = re.search(r"<h1[^>]*>(.*?)</h1>", text, flags=re.DOTALL | re.IGNORECASE)
        if h1_match:
            t = re.sub(r"<[^>]+>", " ", h1_match.group(1))
            t = html_module.unescape(t).strip()
            if len(t) >= 15:
                paragraphs.append(t)
        
        p_matches = re.findall(r"<p[^>]*>(.*?)</p>", text, flags=re.DOTALL | re.IGNORECASE)
        for p in p_matches:
            p_text = re.sub(r"<[^>]+>", " ", p)
            p_text = html_module.unescape(p_text)
            p_text = re.sub(r"\s+", " ", p_text).strip()
            
            if len(p_text) < 40:
                continue
            
            link_texts = re.findall(r"<a[^>]*>(.*?)</a>", p, flags=re.DOTALL | re.IGNORECASE)
            link_chars = sum(len(re.sub(r"<[^>]+>", "", lt).strip()) for lt in link_texts)
            link_density = link_chars / max(1, len(p_text))
            
            if link_density > 0.40:
                continue
                
            paragraphs.append(p_text)
        
        if paragraphs:
            return "\n\n".join(paragraphs)
        
        text = re.sub(r"<[^>]+>", " ", text)
        text = html_module.unescape(text)
        return re.sub(r"\s+", " ", text).strip()

    def __init__(
        self,
        providers: List['ISearchProvider'] = None,
        page_fetcher: Callable[[str], Awaitable[str]] = None
    ):
        super().__init__()
        if providers is None:
            self.providers = []
        else:
            self.providers = providers
        self.page_fetcher = page_fetcher

    async def _web_search(self, query: str) -> Dict[str, Any]:
        import asyncio
        log.info("Executing resilient web search provider chain", query=query)
        
        snippets = []
        urls = []
        provider_name = "none"
        
        for provider in self.providers:
            result = await provider.search(query)
            if result:
                snippets = result.snippets
                urls = result.urls
                provider_name = result.provider
                break

        if not snippets:
            return {
                "status": "no_results",
                "message": "Không tìm thấy kết quả tìm kiếm nào phù hợp trên internet.",
                "search_query": query,
                "snippets": [],
                "source_urls": [],
                "provider": provider_name,
            }

        results = snippets[:4]
        results_str = f"SEARCH SNIPPETS ({provider_name}):\n" + "\n".join([f"- {r}" for r in results])

        # Parallel Deep Page Crawling (Load tolerant and fast, up to 3 candidate URLs in parallel)
        filtered_urls = [
            u for u in urls[:5]
            if not any(domain in u for domain in ["youtube.com", "facebook.com", "twitter.com", "instagram.com", "tiktok.com"])
        ][:3]

        fetched_content = []
        deep_page_url = None
        deep_page_preview = None

        if filtered_urls and self.page_fetcher:
            async def fetch_page(target_url: str):
                try:
                    log.info("Fetching deep page in parallel", url=target_url)
                    html = await asyncio.wait_for(self.page_fetcher(target_url), timeout=3.5)
                    if html:
                        cleaned_text = self._clean_html_to_text(html)
                        # Filter out robot policy blocks or captcha error messages
                        is_blocked = any(err in cleaned_text.lower() for err in [
                            "please set a user-agent",
                            "robot policy",
                            "403 forbidden",
                            "access denied",
                            "attention required",
                            "cloudflare",
                            "just a moment..."
                        ])
                        if len(cleaned_text) >= 150 and not is_blocked:
                            return target_url, cleaned_text[:1500]
                except asyncio.TimeoutError:
                    log.warning("Deep page fetch timed out after 3.5s", url=target_url)
                except Exception as pe:
                    log.warning("Failed parallel deep page fetch", url=target_url, error=str(pe))
                return None

            tasks = [fetch_page(u) for u in filtered_urls]
            fetch_results = await asyncio.gather(*tasks)

            for f_res in fetch_results:
                if f_res:
                    target_url, content_snippet = f_res
                    deep_page_url = target_url
                    deep_page_preview = content_snippet
                    fetched_content.append(f"SOURCE URL: {target_url}\nCONTENT: {content_snippet}")
                    break  # Grab first successful high-quality page to conserve token budget

            if fetched_content:
                results_str += "\n\nDEEP PAGE CONTENT:\n" + "\n\n".join(fetched_content)

        log.info("Resilient web search completed", provider=provider_name, count=len(results), got_deep_content=bool(fetched_content))
        return {
            "status": "success",
            "message": results_str,
            "search_query": query,
            "snippets": results,
            "source_urls": urls[:4],
            "deep_page_url": deep_page_url,
            "deep_page_preview": deep_page_preview,
            "provider": provider_name,
        }
