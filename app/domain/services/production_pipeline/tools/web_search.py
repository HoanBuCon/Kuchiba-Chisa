import urllib.parse
import re
import httpx
from typing import Any, Dict, List
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.llm.adapters.base import BaseLLMAdapter, StructuredPrompt
from app.domain.interfaces.embedding_provider import IEmbeddingProvider
from app.domain.services.production_pipeline.tools.base import BaseAgentTool
from app.infrastructure.logging.logger import get_logger

log = get_logger(__name__)


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
        history = kwargs.get("history")
        # Level 2b: Optimize query using LLM with context
        search_query = await self._extract_search_query(user_message, llm, history)
        res = await self._web_search(search_query)
        return res

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
            "that resolves pronouns (e.g., 'em' -> 'Kuchiba Chisa', 'game này' -> 'Wuthering Waves') and captures the core search intent.\n"
            "Remove all conversational fillers (e.g., 'tra giúp', 'cho hỏi', 'em ơi').\n"
            "You MUST output the result as a valid JSON object with key 'search_query'."
        )

        user_prompt = (
            f"[Lịch sử hội thoại gần đây]:\n{history_str}\n\n"
            f"[Câu hỏi mới nhất của Senpai]: \"{user_message}\""
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
            response = await llm.generate(prompt)
            parsed = response.parsed or {}
            query = (parsed.get("search_query") or parsed.get("query") or "").strip()
            if query:
                log.info("LLM optimized search query with context", original=user_message, extracted=query)
                return query
        except Exception as e:
            log.warning("LLM query extraction failed, falling back to raw message", error=str(e))
        return user_message

    async def _web_search(self, query: str) -> Dict[str, Any]:
        log.info("Running web search in WebSearchAgentTool", query=query)
        url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
        }

        def _parse_snippets(html: str) -> List[str]:
            patterns = [
                r'<a class="result__snippet"[^>]*>(.*?)</a>',
                r'<div class="result__snippet"[^>]*>(.*?)</div>',
                r'class="result__body"[^>]*>(.*?)</div>',
            ]
            for pattern in patterns:
                raw = re.findall(pattern, html, re.DOTALL)
                if raw:
                    cleaned = []
                    for s in raw:
                        c = re.sub(r'<[^>]+>', '', s)
                        c = (c.replace('&nbsp;', ' ').replace('&amp;', '&')
                               .replace('&lt;', '<').replace('&gt;', '>')
                               .replace('&quot;', '"').replace('&#x27;', "'")
                               .strip())
                        if c:
                            cleaned.append(c)
                    if cleaned:
                        return cleaned
            return []

        def _extract_urls(html: str) -> List[str]:
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

        def _clean_html_to_text(html_content: str) -> str:
            # Remove scripts, styles, and other noise tags
            html_content = re.sub(r'<(script|style|noscript|header|footer|nav|head)[^>]*>.*?</\1>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
            # Replace common elements with space or newline
            html_content = re.sub(r'</?(div|p|br|li|tr)[^>]*>', '\n', html_content)
            # Remove remaining tags
            text = re.sub(r'<[^>]+>', ' ', html_content)
            # Decode entities
            text = (text.replace('&nbsp;', ' ').replace('&amp;', '&')
                        .replace('&lt;', '<').replace('&gt;', '>')
                        .replace('&quot;', '"').replace('&#x27;', "'")
                        .replace('\r', '\n'))
            # Collapse whitespace
            text = re.sub(r'\n\s*\n', '\n\n', text)
            text = re.sub(r'[ \t]+', ' ', text)
            return text.strip()

        try:
            async with httpx.AsyncClient(headers=headers, timeout=12.0, follow_redirects=True) as client:
                response = await client.get(url)
                log.info("DuckDuckGo HTTP response", status_code=response.status_code, query=query)

                if not (200 <= response.status_code < 300):
                    log.warning("DuckDuckGo search failed", status_code=response.status_code)
                    return {"status": "error", "message": f"Không thể kết nối dịch vụ tìm kiếm (Mã lỗi: {response.status_code})."}

                snippets = _parse_snippets(response.text)
                results = snippets[:4]

                if not results:
                    return {"status": "success", "message": "Không tìm thấy kết quả tìm kiếm nào phù hợp trên internet."}

                results_str = "SEARCH SNIPPETS:\n" + "\n".join([f"- {r}" for r in results])
                
                # Fetch page content of top result to extract real numbers/prices
                urls = _extract_urls(response.text)
                fetched_content = []
                for target_url in urls[:2]:
                    # Skip common social media domains that won't have the table/article
                    if any(domain in target_url for domain in ["youtube.com", "facebook.com", "twitter.com", "instagram.com"]):
                        continue
                    try:
                        log.info("Fetching deep page content for search results", url=target_url)
                        page_response = await client.get(target_url, timeout=6.0)
                        if page_response.status_code == 200:
                            cleaned_text = _clean_html_to_text(page_response.text)
                            if len(cleaned_text) > 100:
                                # Truncate content to keep prompt token size reasonable (approx. 1000 chars)
                                content_snippet = cleaned_text[:1000]
                                fetched_content.append(f"SOURCE URL: {target_url}\nCONTENT: {content_snippet}")
                                break # Just get the first successful page to save tokens
                    except Exception as pe:
                        log.warning("Failed to fetch deep page content", url=target_url, error=str(pe))
                
                if fetched_content:
                    results_str += "\n\nDEEP PAGE CONTENT:\n" + "\n\n".join(fetched_content)

                log.info("Web search completed successfully", count=len(results), got_deep_content=bool(fetched_content))
                return {
                    "status": "success",
                    "message": results_str
                }
        except Exception as e:
            log.error("Failed to execute web search in WebSearchAgentTool", error=str(e))
            return {"status": "error", "message": f"Gặp lỗi khi tìm kiếm thông tin: {str(e)}"}
