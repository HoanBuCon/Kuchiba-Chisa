from app.domain.services.tool_router import KeywordToolRouter


def test_keyword_tool_router_web_search_match():
    tool = KeywordToolRouter.match("tra mạng giúp anh")
    assert tool == "web_search"


def test_keyword_tool_router_conversation_summarizer_match():
    tool = KeywordToolRouter.match("tóm tắt nãy giờ")
    assert tool == "summarize_conversation_memory"


def test_keyword_tool_router_emotion_report_match():
    tool = KeywordToolRouter.match("cho anh xem chỉ số cảm xúc")
    assert tool == "get_emotion_report"


def test_keyword_tool_router_returns_none_for_non_tool_query():
    tool = KeywordToolRouter.match("rover là ai")
    assert tool is None
