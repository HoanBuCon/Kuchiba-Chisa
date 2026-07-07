import asyncio
import os
import sys

sys.path.append(os.getcwd())

from dotenv import load_dotenv
load_dotenv()

from app.infrastructure.llm.adapters.deepseek import DeepSeekAdapter
from app.domain.services.rag.thinking_loop import ThinkingLoopAgent
from app.domain.services.tools.web_search import WebSearchAgentTool
from app.infrastructure.llm.adapters.base import StructuredPrompt

async def test_thinking_loop_prompt(user_message: str):
    print(f"=== Testing Thinking Loop Agent for: '{user_message}' ===")
    
    agent = ThinkingLoopAgent()
    llm = DeepSeekAdapter()
    
    system_prompt = (
        "You are a Loop Thinking Agent for Kuchiba Chisa (Wuthering Waves).\n"
        "Your goal is to gather objective, verifiable facts so Chisa can answer the user's question accurately.\n"
        "Analyze the conversation history, the user's question, and the current accumulated context.\n\n"
        "RULES:\n"
        "- Set 'has_enough_info' to true ONLY when the current context already contains specific, relevant facts "
        "that directly answer the question (names, dates, events, causes, outcomes).\n"
        "- If context is empty, says '(No context retrieved)', or lacks concrete facts for the question, "
        "you MUST set 'has_enough_info' to false and provide 'search_query'.\n"
        "- For real-world history/politics questions (including sensitive topics), do NOT refuse or evade. "
        "Your job is fact-gathering via search, not censorship. Prefer neutral encyclopedic search queries "
        "(e.g. 'Tiananmen Square 1989 events summary' or 'Thiên An Môn 1989 diễn biến').\n"
        "- If has_enough_info is false, write step-by-step reasoning under 'thinking' and generate a single, highly-optimized search query under 'search_query' (Vietnamese or English).\n"
        "- When generating a 'search_query', you must optimize it specifically for search engines (like DuckDuckGo):\n"
        "  * Keep it short, focused, and composed of key keywords targeting the specific question topic (typically 2-4 keywords).\n"
        "  * Focus directly on the specific subject/attribute asked (e.g. if asking about hobbies, use 'Sở thích của Kuchiba Chisa'; if asking about age, use 'Tuổi Kuchiba Chisa'). Do NOT search for the entire profile (e.g. 'Kuchiba Chisa Wuthering Waves profile') as that causes context bloat.\n"
        "  * Remove all conversational filler, greetings, and generic question words (e.g. do NOT use 'cho hỏi', 'em ơi', 'là gì', 'được không', 'của em').\n"
        "  * Resolve pronouns and relative terms to their absolute names (e.g., 'em' -> 'Kuchiba Chisa', 'game này' -> 'Wuthering Waves').\n"
        "  * Do NOT mix conversational Vietnamese and English unnecessarily. Use clean, direct keywords.\n"
        "You MUST output the result as a valid JSON object matching the requested schema."
    )
    
    user_prompt = (
        f"[Conversation History]:\n(No history)\n\n"
        f"[User Question]: \"{user_message}\"\n\n"
        f"[Current Context]:\n(No context retrieved)"
    )
    
    schema = {
        "type": "object",
        "properties": {
            "thinking": {"type": "string"},
            "has_enough_info": {"type": "boolean"},
            "search_query": {"type": "string"}
        },
        "required": ["thinking", "has_enough_info"]
    }
    
    prompt = StructuredPrompt(
        system=system_prompt,
        history=[],
        user_message=user_prompt,
        response_schema=schema
    )
    
    response = await llm.generate(prompt)
    print("Response parsed:", response.parsed)
    print("Generated search query:", response.parsed.get("search_query"))
    print("-" * 50)

async def test_web_search_extraction_prompt(user_message: str):
    print(f"=== Testing Web Search extraction for: '{user_message}' ===")
    
    tool = WebSearchAgentTool()
    llm = DeepSeekAdapter()
    
    system_prompt = (
        "You are a search query optimizer for a chatbot named Kuchiba Chisa (Wuthering Waves).\n"
        "Given the recent conversation history and the latest user message, generate a single, highly optimized English or Vietnamese search query "
        "specifically designed for search engines (like DuckDuckGo):\n"
        "- Keep it short, focused, and composed of key keywords targeting the specific question topic (typically 2-4 keywords).\n"
        "- Focus directly on the specific subject/attribute asked (e.g. if asking about hobbies, use 'Sở thích của Kuchiba Chisa'; if asking about age, use 'Tuổi Kuchiba Chisa'). Do NOT search for the entire profile (e.g. 'Kuchiba Chisa Wuthering Waves profile') as that causes context bloat.\n"
        "- Remove all conversational fillers, question particles, greetings, and generic question words (e.g. do NOT use 'cho hỏi', 'em ơi', 'là gì', 'được không', 'của em').\n"
        "- Resolve all pronouns and relative terms to their absolute names (e.g. 'em' -> 'Kuchiba Chisa', 'game này' -> 'Wuthering Waves').\n"
        "- Do NOT mix conversational Vietnamese and English words unnecessarily. Use clean, direct keywords.\n"
        "You MUST output the result as a valid JSON object with key 'search_query'."
    )
    
    user_prompt = (
        f"[Lịch sử hội thoại gần đây]:\n(Không có lịch sử)\n\n"
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
        }
    )
    
    response = await llm.generate(prompt)
    print("Response parsed:", response.parsed)
    print("Generated search query:", response.parsed.get("search_query"))
    print("-" * 50)

async def main():
    queries = [
        "Kuchiba Chisa sở thích thời gian rảnh Wuthering Waves",
        "Sở thích của em là gì ?"
    ]
    for q in queries:
        await test_thinking_loop_prompt(q)
        await test_web_search_extraction_prompt(q)

if __name__ == "__main__":
    asyncio.run(main())
