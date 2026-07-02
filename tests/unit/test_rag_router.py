import pytest
from app.domain.services.rag_router import RAGRouter

def test_rag_router_small_talk():
    # Exactly small talk phrase
    assert RAGRouter.should_retrieve("haha") == {"use_lore": False, "use_memory": False}
    # Too short
    assert RAGRouter.should_retrieve("hi") == {"use_lore": False, "use_memory": False}

def test_rag_router_memory_triggers():
    # Word boundary match
    assert RAGRouter.should_retrieve("Em có nhớ anh không?")["use_memory"] is True
    # Substring mismatch should NOT trigger (e.g. nhóm, nhờ)
    assert RAGRouter.should_retrieve("Em đi cùng nhóm bạn nha")["use_memory"] is False
    assert RAGRouter.should_retrieve("Nhờ em giúp anh việc này")["use_memory"] is False

def test_rag_router_lore_triggers():
    # Lore is always True for non-small talk messages
    assert RAGRouter.should_retrieve("Em ở học viện Startorch hả?")["use_lore"] is True
    assert RAGRouter.should_retrieve("Anh muốn kéo dài cuộc trò chuyện này")["use_lore"] is True
    assert RAGRouter.should_retrieve("Cây kéo của em dùng làm gì?")["use_lore"] is True

def test_rag_router_fallback():
    # Fallback tests reflect that any non-small talk message has use_lore=True
    long_msg = "Hôm nay thời tiết ở chỗ của anh rất là đẹp luôn đó bạn ơi, anh vừa mới đi dạo một vòng quanh công viên xong nè"
    res = RAGRouter.should_retrieve(long_msg)
    assert res == {"use_lore": True, "use_memory": False}

    # Message not long enough and no explicit triggers still has use_lore=True since it's not small talk
    medium_msg = "Hôm nay thời tiết đẹp quá em ơi, đi chơi không nè?"
    res = RAGRouter.should_retrieve(medium_msg)
    assert res == {"use_lore": True, "use_memory": False}
