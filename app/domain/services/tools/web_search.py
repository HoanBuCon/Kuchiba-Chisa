import urllib.parse
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

        history = kwargs.get("history")
        cache = kwargs.get("cache")
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

    def _sanitize_query(self, query: str) -> str:
        """Sanitizes search query, removing noise and limiting to max keywords."""
        cleaned = re.sub(r'[^\w\sÀ-ỹ\-\.]', ' ', query)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        words = cleaned.split()
        if len(words) > RAGTuning.MAX_SANITIZED_KEYWORDS:
            return " ".join(words[:RAGTuning.MAX_SANITIZED_KEYWORDS])
        return " ".join(words)

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
            "- Keep it focused and keyword-based. Strip out conversational fillers, greetings, punctuation, and generic question words (e.g., 'cho hỏi', 'em ơi', 'là gì', 'được không', 'của em', 'vậy em', 'nhé').\n"
            "- Resolve pronouns and relative terms to their absolute names (e.g., 'em' -> 'Kuchiba Chisa', 'game này' -> 'Wuthering Waves').\n"
            "- CRITICAL FOR RELEVANCE: Retain all distinct semantic constraints from the user's question. Do NOT over-truncate. A high-quality query must combine: (1) the primary Subject/Entity, (2) the target Action/Attribute, and (3) key qualifiers (such as Location, Nationality, or specific Industry). Omitting any of these distinct constraints makes the search too broad and yields useless results.\n"
            "- Focus on semantic completeness: include all distinct constraints in a concise manner (typically 4 to 8 search terms). Do not search for a broad profile if the user asks about a very specific attribute.\n"
            "- Keep the language consistent: use clean, direct keywords matching the language of the query. Do NOT mix conversational Vietnamese and English.\n"
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
            from app.domain.context import llm_call_purpose
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
                "status": "success",
                "message": "Không tìm thấy kết quả tìm kiếm nào phù hợp trên internet.",
                "search_query": query,
                "snippets": [],
                "source_urls": [],
            }

        results = snippets[:4]
        results_str = f"SEARCH SNIPPETS ({provider_name}):\n" + "\n".join([f"- {r}" for r in results])

        # Parallel Deep Page Crawling (Load tolerant and fast)
        filtered_urls = [
            u for u in urls[:3]
            if not any(domain in u for domain in ["youtube.com", "facebook.com", "twitter.com", "instagram.com", "tiktok.com"])
        ][:2]

        fetched_content = []
        deep_page_url = None
        deep_page_preview = None

        if filtered_urls:
            if self.page_fetcher:
                async def fetch_page(target_url: str):
                    try:
                        log.info("Fetching deep page in parallel", url=target_url)
                        html = await self.page_fetcher(target_url)
                        if html:
                            cleaned_text = self._clean_html_to_text(html)
                            if len(cleaned_text) > 100:
                                return target_url, cleaned_text[:1000]
                    except Exception as pe:
                        log.warning("Failed parallel deep page fetch", url=target_url, error=str(pe))
                    return None
            else:
                async def fetch_page(target_url: str):
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
