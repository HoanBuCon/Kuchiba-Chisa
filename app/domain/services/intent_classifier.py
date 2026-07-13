import enum
import re
from typing import List, Optional
from app.infrastructure.llm.adapters.base import BaseLLMAdapter
from app.domain.interfaces.embedding_provider import IEmbeddingProvider
from app.infrastructure.logging.logger import get_logger

log = get_logger(__name__)


class ChatIntent(str, enum.Enum):
    CHARACTER_LORE = "CHARACTER_LORE"
    WORLD_LORE = "WORLD_LORE"
    STORY_LORE = "STORY_LORE"
    MEMORY = "MEMORY"
    OTHER = "OTHER"
    SYSTEM_ACTION = "SYSTEM_ACTION"


def _phrase_match(phrases: List[str], text: str) -> bool:
    """
    Kiểm tra xem text có chứa bất kỳ phrase nào trong danh sách không,
    sử dụng lookahead/lookbehind để tránh match sai bên trong từ khác.
    Tiếng Việt không có word-boundary ASCII chuẩn nên dùng (?<!\\w)..(?!\\w).
    """
    for phrase in phrases:
        if re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", text):
            return True
    return False


def _pattern_match(patterns: List[str], text: str) -> bool:
    """Kiểm tra text khớp với bất kỳ regex pattern nào trong danh sách."""
    for pattern in patterns:
        if re.search(pattern, text):
            return True
    return False


class IntentClassifier:
    """
    Phân loại intent của tin nhắn người dùng qua 4 lớp lọc:
      L1 — Small Talk Fast-Path (phrase set + độ dài)
      L2 — High-Confidence Keyword Guard (word-boundary regex)
      L3 — Semantic Router (Cosine Similarity + Anchor Bonus + Margin Guard)
      L4 — Fallback (trả OTHER nếu không có gì khớp)
    """

    SMALL_TALK_PHRASES = {
        "haha", "ok", "ừ", "hi", "vâng", "dạ", "chào", "đúng rồi",
        "thế à", "vậy hả", "à", "ừm", "cảm ơn", "bye", "tạm biệt",
        "hí hí", "hihi", "hehe", "ê", "hey", "alo", "lô", "lô lô",
        "dạ vâng", "dạ đúng rồi", "chuẩn", "chuẩn luôn", "chính xác",
        "uầy", "chà", "wow", "oh", "ô", "ôi", "haiz", "hầy", "hic",
        "hic hic", "huhu", "ahihi", "kaka", "kkk", "lol", "lmao", "hello", "halo",
        "bye bye", "g9", "ngủ ngon", "thế á", "vậy á", "thế hả", "thế nhở",
        "thank", "thanks", "tks", "ty", "thx", "được thôi", "được", "ừm hửm",
        "hửm", "hử", "gì cơ", "sao cơ", "sao thế", "ừ thế", "thế thôi",
        "okay", "nha", "nhé", "nè", "nhen", "hén", "đấy", "đó", "thế", "vậy"
    }

    # ── L2: High-confidence keyword phrases (dùng word-boundary match) ──

    # MEMORY: Gắn với tên / biệt danh / thông tin cá nhân của Senpai
    _MEMORY_PHRASES = [
        "tên anh là gì", "tên tớ là gì", "tên mình là gì",
        "biệt danh của anh", "sở thích của anh",
        "ngày mai anh làm gì", "ngày mai anh đi",
        "hôm trước anh bảo", "hôm qua anh nói",
        "ngày mai anh phỏng vấn", "nhớ biệt danh của anh",
        "tên anh là", "tên tớ là", "tên mình là",
        "anh đang học gì", "anh làm nghề gì", "công việc của anh",
        "ông anh tên gì", "senpai tên gì", "ước mơ của anh", "anh hứa gì với em",
        "anh thích nghe nhạc gì", "anh sinh năm bao nhiêu", "quê anh ở đâu",
        "anh thích đọc sách gì", "gia đình của anh", "anh quen em thế nào"
    ]

    # CHARACTER_LORE: Chỉ bắt khi đề cập rõ "của em" / "của chisa"
    _CHARACTER_PHRASES = [
        "vũ khí của em", "vũ khí của chisa",
        "vòng ở cổ em", "vòng cổ của em",
        "cái vòng ở cổ", "vòng cổ của chisa",
        "em thích ăn gì", "sở thích của em",
        "em thích ăn vặt", "món tủ của em",
        "chisa thích", "cây kéo của em", "chiếc kéo của em",
        "em bao nhiêu tuổi", "em học trường nào",
        "em sinh ra ở đâu", "tính cách của em",
        "resonance của em", "forte của chisa",
        "em sợ điều gì", "điểm yếu của em",
        "em bao tuổi rồi", "tiểu sử của em", "lý lịch của em", "năng lực của em",
        "em ăn được ớt không", "món em ghét nhất", "sở thích lúc rảnh của em",
        "em thích mèo không", "thiết bị ở cổ em", "vòng cổ của em",
        "thuộc tính nguyên tố của em", "dấu ấn tacet mark của em"
    ]

    # WORLD_LORE: Thuật ngữ đặc thù thế giới game — bắt chính xác
    _WORLD_PHRASES = [
        "sonoro sphere", "tacet discord", "solaris-3", "solaris 3",
        "lahai-roi", "lahai roi", "mutant resonator",
        "resonator là gì", "tacet field là gì",
        "echo là gì", "resonance liberation",
        "fracidust", "black shores", "huanglong",
        "tacet discord là cái gì", "mutant resonator là sao",
        "lahai-roi ở vùng nào", "solaris 3 là hành tinh nào",
        "jinzhou ở đâu", "huanglong là gì", "fracidust là thế nào",
        "echo là cái gì", "thành phố jinzhou", "thế giới solaris"
    ]

    # STORY_LORE: Sự kiện / arc cốt truyện cụ thể
    _STORY_PHRASES = [
        "vòng lặp honami", "vòng lặp của honami",
        "lễ hội startorch", "học viện startorch",
        "companion quest", "chapter 3", "chương 3",
        "cốt truyện chapter", "câu chuyện của sumika",
        "nhật ký của sumika", "sự kiện startorch",
        "di thư của sumika", "cuốn sổ của sumika",
        "vòng lặp honami là sao", "chapter 3 cốt truyện",
        "lễ hội startorch có gì", "startorch school festival"
    ]

    # SYSTEM_ACTION: Lệnh tường minh — bắt bằng regex pattern (linh hoạt hơn phrase match)
    _SYSTEM_PATTERNS = [
        # Tóm tắt cuộc trò chuyện
        r"tóm tắt.{0,15}(cuộc trò chuyện|hội thoại|nãy giờ|buổi chat|session)",
        r"(tổng hợp|tổng kết).{0,15}(cuộc trò chuyện|những gì|điểm chính|nãy giờ)",
        r"em ghi lại.{0,15}(điểm chính|những gì|cuộc trò chuyện)",
        r"cho anh xem tóm tắt",
        # Báo cáo cảm xúc
        r"(cho anh xem|xuất|hiển thị|xem).{0,15}(chỉ số cảm xúc|bảng đo cảm xúc|báo cáo cảm xúc)",
        r"(em đang cảm thấy thế nào|tâm trạng của em).{0,10}(theo số liệu|theo chỉ số)",
        r"(chỉ số|bảng đo|báo cáo).{0,10}cảm xúc.{0,10}(của em|hiện tại)",
        # Web search tường minh
        r"(tra mạng|lên mạng|tra cứu trên internet|lên web).{0,25}",
        r"search google.{0,20}",
        r"(em tìm kiếm|em tra|em tìm).{0,10}(trên internet|trên mạng|giúp anh)",
        r"(tìm giúp|tra giúp).{0,10}(anh|tớ|mình).{0,10}(trên|mạng|internet)",
    ]

    def __init__(self, llm: BaseLLMAdapter, embedder: Optional[IEmbeddingProvider] = None):
        self.llm = llm
        self.embedder = embedder
        self.semantic_router = None
        if embedder:
            from app.domain.services.semantic_router import SemanticRouter
            self.semantic_router = SemanticRouter(embedder=embedder)

    @classmethod
    def is_small_talk(cls, message: str) -> bool:
        """
        Trả về True nếu tin nhắn là small talk đơn giản,
        không cần kích hoạt bất kỳ pipeline RAG nào.
        """
        msg_lower = message.strip().lower()
        return len(msg_lower) < 8 or msg_lower in cls.SMALL_TALK_PHRASES

    async def classify(self, user_message: str, query_vector: Optional[List[float]] = None) -> tuple[List["ChatIntent"], Optional[List[float]]]:
        # ── L1: Small talk detection ──
        if self.is_small_talk(user_message):
            log.debug("Intent fast-path: small talk detected", user_message=user_message)
            return [ChatIntent.OTHER], None

        msg_lower = user_message.strip().lower()
        high_conf_intents: List[ChatIntent] = []

        # ── L2: High-confidence keyword / pattern matching ──

        if _phrase_match(self._MEMORY_PHRASES, msg_lower):
            high_conf_intents.append(ChatIntent.MEMORY)

        if _phrase_match(self._CHARACTER_PHRASES, msg_lower):
            high_conf_intents.append(ChatIntent.CHARACTER_LORE)

        if _phrase_match(self._WORLD_PHRASES, msg_lower):
            high_conf_intents.append(ChatIntent.WORLD_LORE)

        if _phrase_match(self._STORY_PHRASES, msg_lower):
            high_conf_intents.append(ChatIntent.STORY_LORE)

        # SYSTEM_ACTION dùng regex pattern (linh hoạt hơn)
        if _pattern_match(self._SYSTEM_PATTERNS, msg_lower):
            high_conf_intents.append(ChatIntent.SYSTEM_ACTION)

        if high_conf_intents:
            log.info(
                "Intent fast-path: high confidence rules matched",
                intents=[i.value for i in high_conf_intents],
                user_message=user_message,
            )
            return high_conf_intents, None

        # ── L3: Semantic Router ──
        if self.semantic_router:
            try:
                # Lazy embedding generation for semantic routing
                if query_vector is None and self.embedder:
                    from app.shared.utils.query_cleaner import clean_query_for_rag
                    cleaned = clean_query_for_rag(user_message)
                    query_vector = await self.embedder.embed_text(cleaned)

                matched_intents = await self.semantic_router.classify(user_message, query_vector)
                if matched_intents:
                    log.info(
                        "Semantic router matched intents",
                        intents=[i.value for i in matched_intents],
                        user_message=user_message,
                    )
                    return matched_intents, query_vector
            except Exception as e:
                log.warning("Semantic Router classification failed, falling back to OTHER", error=str(e))

        # ── L4: Fallback ──
        log.info("Intent fallback: no rule or semantic match, returning OTHER", user_message=user_message)
        return [ChatIntent.OTHER], query_vector
