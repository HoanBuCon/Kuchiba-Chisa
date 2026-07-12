import urllib.parse
import re
import httpx
from typing import Any, Dict, List
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.llm.adapters.base import BaseLLMAdapter, StructuredPrompt
from app.domain.interfaces.embedding_provider import IEmbeddingProvider
from app.domain.services.tools.base import BaseAgentTool
from app.config.settings import settings
from app.infrastructure.logging.logger import get_logger

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
        ]

    async def execute(
        self,
        session: AsyncSession,
        user_id: str,
        user_message: str,
        llm: BaseLLMAdapter,
        embedder: IEmbeddingProvider,
        **kwargs
    ) -> Dict[str, Any]:
        import hashlib
        import json
        import asyncio
        from app.infrastructure.cache.redis.redis_service import redis_service

        history = kwargs.get("history")
        bypass_optimize = kwargs.get("bypass_optimize", False)
        
        if bypass_optimize:
            search_query = user_message
        else:
            # Level 2b: Optimize query using LLM with context
            search_query = await self._extract_search_query(user_message, llm, history)
            
        search_query = self._sanitize_query(search_query)
        log.info("Sanitized search query", query=search_query)

        # ── Redis Cache Lookup ──
        h = hashlib.md5(search_query.strip().lower().encode("utf-8")).hexdigest()
        cache_key = f"chisa:search_cache:{h}"
        try:
            cached = await redis_service.get(cache_key)
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
                await redis_service.set(cache_key, json.dumps(res), ttl=7200)
            except Exception as e:
                log.warning("Failed to save search result to cache", error=str(e))

        return res

    def _sanitize_query(self, query: str) -> str:
        """Sanitizes search query, removing noise and limiting to max 6 keywords."""
        cleaned = re.sub(r'[^\w\sÀ-ỹ\-\.]', ' ', query)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        words = cleaned.split()
        if len(words) > 6:
            return " ".join(words[:6])
        return cleaned

    async def _extract_search_query(
        self,
        user_message: str,
        llm: BaseLLMAdapter,
        history: List[Dict[str, str]] = None
    ) -> str:
        """
        Extract and clean search query from natural language query using recent conversation context.
        """
        import json
        
        # 1. Rút gọn history: lấy tối đa 3 lượt hội thoại gần nhất (tương ứng tối đa 6 messages)
        recent_history = history[-6:] if history else []
        history_lines = []
        for msg in recent_history:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            
            # Trích xuất phần response thô nếu assistant dùng JSON mode
            if role == "assistant" and content.strip().startswith("{"):
                try:
                    parsed = json.loads(content)
                    content = parsed.get("response", content)
                except Exception:
                    pass
            history_lines.append(f"{role.upper()}: {content}")
        
        history_str = "\n".join(history_lines) if history_lines else "(Không có lịch sử)"

        # 2. Compact system prompt tối ưu hóa token
        system_prompt = (
            "You are a search query optimizer for a chatbot named Kuchiba Chisa (Wuthering Waves).\n"
            "Given the recent conversation history and the latest user message, generate a single, highly optimized English or Vietnamese search query "
            "specifically designed for search engines (like DuckDuckGo):\n"
            "- Keep it short, focused, and composed of key keywords targeting the specific question topic (typically 2-4 keywords).\n"
            "- Focus directly on the specific subject/attribute asked (e.g. if asking about hobbies, use 'Sở thích của Kuchiba Chisa'; if asking about age, use 'Tuổi Kuchiba Chisa').\n"
            "- Remove all conversational fillers, question particles, greetings, and generic question words (e.g. do NOT use 'cho hỏi', 'em ơi', 'là gì', 'được không', 'của em').\n"
            "- Resolve all pronouns and relative terms to their absolute names (e.g. 'em' -> 'Kuchiba Chisa', 'game này' -> 'The Games user was talking about').\n"
            "- Do NOT mix conversational Vietnamese and English words unnecessarily. Use clean, direct keywords.\n"
            "You MUST output the result as a valid JSON object with key 'search_query'."
        )

        user_prompt = (
            f"[Recent Conversation History]:\n{history_str}\n\n"
            f"[Latest User Message]: \"{user_message}\""
        )

        prompt = StructuredPrompt(
            system=system_prompt,
            history=[],
            user_message=user_prompt,
            response_schema={
                "type": "object",
                "properties": {
                    "search_query": {"type": "string"}
                },
                "required": ["search_query"]
            },
            retrieved_memories=[],
            retrieved_lore=[],
            rag_decisions={}
        )

        try:
            from app.infrastructure.logging.llm_logger import llm_call_purpose
            llm_call_purpose.set("web_search_query_extract")
            response = await llm.generate(prompt)
            parsed = response.parsed or {}
            query = (parsed.get("search_query") or parsed.get("query") or "").strip()
            if query:
                log.info("LLM optimized search query with context", original=user_message, extracted=query)
                return query
        except Exception as e:
            log.warning("LLM query extraction failed, falling back to raw message", error=str(e))
        return user_message

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
                    c = html_lib.unescape(c).strip()
                    if c:
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

    def _clean_html_to_text(self, html_content: str) -> str:
        # Remove scripts, styles, and other noise tags
        html_content = re.sub(r'<(script|style|noscript|header|footer|nav|head)[^>]*>.*?</\1>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
        # Replace common elements with space or newline
        html_content = re.sub(r'</?(div|p|br|li|tr)[^>]*>', '\n', html_content)
        # Remove remaining tags
        text = re.sub(r'<[^>]+>', ' ', html_content)
        # Decode entities
        import html as html_lib
        text = html_lib.unescape(text).replace('\r', '\n')
        # Collapse whitespace
        text = re.sub(r'\n\s*\n', '\n\n', text)
        text = re.sub(r'[ \t]+', ' ', text)
        return text.strip()

    async def _web_search(self, query: str) -> Dict[str, Any]:
        import asyncio
        log.info("Executing resilient web search provider chain", query=query)
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
        }

        async with httpx.AsyncClient(headers=headers, timeout=10.0, follow_redirects=True) as client:
            snippets = []
            urls = []
            provider = "none"

            # 1. Try Tavily (Free monthly tier)
            if settings.ENABLE_PAID_SEARCH and settings.TAVILY_API_KEY:
                try:
                    log.info("Trying Tavily Search API...")
                    res = await client.post(
                        "https://api.tavily.com/search",
                        json={"api_key": settings.TAVILY_API_KEY, "query": query, "max_results": 4},
                        timeout=3.5
                    )
                    if res.status_code == 200:
                        data = res.json()
                        results = data.get("results", [])
                        snippets = [r.get("content", "") for r in results if r.get("content")]
                        urls = [r.get("url", "") for r in results if r.get("url")]
                        provider = "tavily"
                        log.info("Tavily Search API succeeded")
                except Exception as ex:
                    log.warning("Tavily Search failed, trying next provider", error=str(ex))

            # 2. Try Serper (Free monthly tier)
            if not snippets and settings.ENABLE_PAID_SEARCH and settings.SERPER_API_KEY:
                try:
                    log.info("Trying Serper Search API...")
                    res = await client.post(
                        "https://google.serper.dev/search",
                        headers={"X-API-KEY": settings.SERPER_API_KEY, "Content-Type": "application/json"},
                        json={"q": query, "num": 4},
                        timeout=3.5
                    )
                    if res.status_code == 200:
                        data = res.json()
                        results = data.get("organic", [])
                        snippets = [r.get("snippet", "") for r in results if r.get("snippet")]
                        urls = [r.get("link", "") for r in results if r.get("link")]
                        provider = "serper"
                        log.info("Serper Search API succeeded")
                except Exception as ex:
                    log.warning("Serper Search failed, trying next provider", error=str(ex))

            # 3. Try duckduckgo_search library (Free, unlimited)
            if not snippets:
                try:
                    log.info("Trying duckduckgo_search library...")
                    from duckduckgo_search import DDGS
                    def _ddg_sync(q):
                        with DDGS() as ddgs:
                            return list(ddgs.text(q, max_results=4))
                    ddg_res = await asyncio.to_thread(_ddg_sync, query)
                    if ddg_res:
                        snippets = [r.get("body", "") for r in ddg_res if r.get("body")]
                        urls = [r.get("href", "") for r in ddg_res if r.get("href")]
                        provider = "duckduckgo_lib"
                        log.info("duckduckgo_search library succeeded")
                except Exception as ex:
                    log.warning("duckduckgo_search library failed, trying HTML scraper fallback", error=str(ex))

            # 4. Fallback to DDG HTML Scraper
            if not snippets:
                try:
                    log.info("Running DDG HTML scraper fallback...")
                    url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
                    response = await client.get(url, timeout=5.0)
                    if 200 <= response.status_code < 300:
                        snippets = self._parse_snippets(response.text)
                        urls = self._extract_urls(response.text)
                        provider = "html_scraper"
                        log.info("DDG HTML scraper fallback succeeded")
                except Exception as ex:
                    log.error("DDG HTML scraper failed", error=str(ex))

            if not snippets:
                return {
                    "status": "success",
                    "message": "Không tìm thấy kết quả tìm kiếm nào phù hợp trên internet.",
                    "search_query": query,
                    "snippets": [],
                    "source_urls": [],
                }

            results = snippets[:4]
            results_str = f"SEARCH SNIPPETS ({provider}):\n" + "\n".join([f"- {r}" for r in results])

            # Parallel Deep Page Crawling (Load tolerant and fast)
            filtered_urls = [
                u for u in urls[:3]
                if not any(domain in u for domain in ["youtube.com", "facebook.com", "twitter.com", "instagram.com", "tiktok.com"])
            ][:2]

            fetched_content = []
            deep_page_url = None
            deep_page_preview = None

            if filtered_urls:
                async def fetch_page(target_url: str):
                    try:
                        log.info("Fetching deep page in parallel", url=target_url)
                        # Set strict 2.0s timeout to prevent thread blocking
                        page_response = await client.get(target_url, timeout=2.0)
                        if page_response.status_code == 200:
                            cleaned_text = self._clean_html_to_text(page_response.text)
                            if len(cleaned_text) > 100:
                                return target_url, cleaned_text[:1000]
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
                        break # Grab first successful page to conserve token budget

            if fetched_content:
                results_str += "\n\nDEEP PAGE CONTENT:\n" + "\n\n".join(fetched_content)

            log.info("Resilient web search completed", provider=provider, count=len(results), got_deep_content=bool(fetched_content))
            return {
                "status": "success",
                "message": results_str,
                "search_query": query,
                "snippets": results,
                "source_urls": urls[:4],
                "deep_page_url": deep_page_url,
                "deep_page_preview": deep_page_preview,
            }
