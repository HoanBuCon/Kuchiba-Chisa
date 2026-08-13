import asyncio
import re
from typing import Dict, List, Optional
from app.config.settings import Settings
from app.config.system_patterns import ALL_SYSTEM_PATTERNS
from app.domain.interfaces.embedding_provider import IEmbeddingProvider
from app.domain.interfaces.llm_provider import BaseLLMAdapter
from app.domain.models.intent_result import ChatIntent, IntentResult
from app.shared.utils.logger import get_logger

log = get_logger(__name__)


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


def _cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Tính độ tương đồng Cosine giữa 2 vector embedding."""
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0
    dot = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = (sum(a * a for a in vec1)) ** 0.5
    norm2 = (sum(b * b for b in vec2)) ** 0.5
    return dot / (norm1 * norm2) if norm1 and norm2 else 0.0


class IntentClassifier:
    """
    Phân loại intent của tin nhắn người dùng qua mô hình Hybrid Semantic Router v2:
      L1 — Small Talk Fast-Path (phrase set + regex pattern)
      L2 — High-Confidence Keyword Guard (word-boundary regex) cho MEMORY, LORE, SYSTEM_ACTION
      L3 — Multi-Anchor Cluster Semantic Classifier (Max Cosine Similarity với N anchor vectors)
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

    # Small talk regex patterns for greetings + pronouns combinations
    _SMALL_TALK_PATTERNS = [
        r"^(chào|hello|hi|hey|halo|alo|lô|g9|bye|tạm biệt)(\s+(em|chisa|senpai|chía|chía chía|bé|bạn|cậu|nhé|nha|à|ơi|nhỉ|nhở))*[!\.\?\s]*$",
        r"^(chào buổi sáng|chào buổi tối|chào buổi chiều)(\s+(em|chisa|senpai|chía|bé|bạn))*[!\.\?\s]*$",
        r"^(hôm nay|ngày mới).{0,15}(thế nào|sao rồi|vui không|khỏe không)[!\.\?\s]*$",
        r"^(em|chisa).{0,10}(ăn cơm chưa|dậy chưa|ngủ chưa|đang làm gì|khỏe không)[!\.\?\s]*$"
    ]

    # Multi-Anchor Clusters cho L3 Semantic Vector Classification (Mở rộng đa dạng)
    SEMANTIC_ANCHORS: Dict[ChatIntent, List[str]] = {
        ChatIntent.LORE: [
            "Hồ sơ nhân vật Kuchiba Chisa, vũ khí, năng lực forte, câu chuyện tiểu sử và ngoại hình",
            "Thế giới Wuthering Waves, Solaris-3, Tacet Discord, Resonator, Waveworn Phenomenon",
            "Cốt truyện game, nhiệm vụ companion quest, chapter story, diễn biến sự kiện",
            "Tính cách, sở thích, món ăn yêu thích, điểm yếu, điều sợ hãi của Chisa",
            "Jinzhou, Black Shores, Huanglong, Lễ hội Startorch, Học viện Startorch, Lahai-Roi",
            "Chiêu thức, kỹ năng chiến đấu, resonance liberation, tacet mark, nguyên tố thuộc tính",
            "Các nhân vật khác trong Wuthering Waves, đồng đội, tổ chức và mối quan hệ",
            "Nhật ký của Sumika, vòng lặp Honami, Sonoro Sphere, Tacet Field",
        ],
        ChatIntent.MEMORY: [
            "Thông tin cá nhân của người dùng Senpai, tên thật, biệt danh, tuổi tác, giới tính",
            "Công việc, nghề nghiệp, nơi làm việc, học tập, lịch trình và kế hoạch cá nhân của anh ấy",
            "Kỷ niệm, lời hứa, chuyện cá nhân, cuộc trò chuyện trước đây giữa hai người",
            "Gia đình, quê quán, nơi sống, ngày sinh nhật, thói quen sinh hoạt của người dùng",
            "Sở thích cá nhân của Senpai, món ăn thích, gu âm nhạc, sách báo, game hay chơi",
            "Sự kiện quan trọng của Senpai như phỏng vấn, thi cử, đi du lịch, công tác",
        ],
        ChatIntent.CONVERSATIONAL: [
            "Trò chuyện về thời tiết, tâm trạng, cảm xúc hàng ngày, sức khỏe hôm nay",
            "Chia sẻ suy nghĩ, tâm sự, hỏi ý kiến về cuộc sống, đưa ra lời khuyên",
            "Đùa giỡn, trêu chọc, nói chuyện vui vẻ, phiếm diện không mục đích cụ thể",
            "Hỏi thăm sức khỏe, khen ngợi, động viên, an ủi, cảm thán góc nhìn cá nhân",
            "Nói về triết lý sống, sở thích chung, bàn luận ý kiến cá nhân tự do",
        ],
        ChatIntent.SYSTEM_ACTION: [
            "Tóm tắt cuộc trò chuyện, tổng hợp điểm chính của buổi chat, ghi lại nội dung",
            "Xem báo cáo cảm xúc, chỉ số tâm trạng hiện tại, biểu đồ cảm xúc của em",
            "Tìm kiếm thông tin trên internet, tra cứu web, search google thông tin mới",
            "Tra cứu dữ liệu thời gian thực, tin tức mạng, sự kiện trực tuyến mới nhất",
        ],
    }

    # Cached anchor vectors per ChatIntent category
    _anchor_vectors: Dict[ChatIntent, List[List[float]]] = {}
    _anchor_lock = asyncio.Lock()

    # ── L2: High-confidence keyword phrases (word-boundary match) ──

    _MEMORY_PHRASES = [
        "tên thật của anh là gì", "tên thật của anh", "tên thật của senpai", "tên thật của tớ",
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

    _LORE_PHRASES = [
        "vũ khí của em", "vũ khí của chisa", "vòng ở cổ em", "vòng cổ của em",
        "em thích ăn gì", "em thích ăn món", "món ăn yêu thích của em", "sở thích của em",
        "món tủ của em", "chisa thích", "món bánh ngọt nào", "bánh ngọt em thích",
        "em bao nhiêu tuổi", "em học trường nào", "em sinh ra ở đâu", "tính cách của em",
        "resonance của em", "forte của chisa", "em sợ điều gì", "điểm yếu của em",
        "tiểu sử của em", "lý lịch của em", "năng lực của em",
        "thuộc tính nguyên tố của em", "dấu ấn tacet mark của em",
        "sonoro sphere", "tacet discord", "solaris-3", "solaris 3",
        "lahai-roi", "mutant resonator", "resonator là gì", "tacet field là gì",
        "echo là gì", "resonance liberation", "fracidust", "black shores", "huanglong",
        "jinzhou ở đâu", "thành phố jinzhou", "vòng lặp honami", "lễ hội startorch",
        "học viện startorch", "companion quest", "chapter 3", "cốt truyện chapter",
        "nhật ký của sumika", "startorch school festival"
    ]

    # SYSTEM_ACTION dùng chung từ app.config.system_patterns
    _SYSTEM_PATTERNS = ALL_SYSTEM_PATTERNS

    def __init__(self, llm: BaseLLMAdapter, embedder: Optional[IEmbeddingProvider] = None, settings: Optional[Settings] = None):
        self.llm = llm
        self.embedder = embedder
        self.settings = settings or Settings()
        self.semantic_threshold = getattr(self.settings, "INTENT_SEMANTIC_THRESHOLD", 0.65)
        self.enable_l3 = getattr(self.settings, "INTENT_ENABLE_L3_SEMANTIC", True)

    @classmethod
    def is_small_talk(cls, message: str) -> bool:
        """
        Trả về True nếu tin nhắn là small talk đơn giản / lời chào xã giao.
        """
        if not message:
            return True
        msg_lower = message.strip().lower()

        # 1. Khớp từ đơn / cụm từ trong tập SMALL_TALK_PHRASES
        if msg_lower in cls.SMALL_TALK_PHRASES:
            return True

        # 2. Khớp các mẫu Lời chào + Đại từ nhân xưng (Hello em, Chào chisa, Hi senpai...)
        if _pattern_match(cls._SMALL_TALK_PATTERNS, msg_lower):
            return True

        # 3. Khớp các câu ngắn (<= 3 từ) cấu thành từ Lời chào & Đại từ
        words = re.findall(r'\w+', msg_lower)
        pronouns_greetings = {"em", "anh", "chisa", "chía", "senpai", "ơi", "à", "nhé", "nha", "nè", "hế lô", "hê lô"}
        if len(words) <= 3 and all(w in cls.SMALL_TALK_PHRASES or w in pronouns_greetings for w in words):
            return True

        return False

    async def _ensure_anchor_vectors(self) -> None:
        """Thread-safe lazy computation & caching của Multi-Anchor embeddings."""
        if self._anchor_vectors or not self.embedder:
            return

        async with self._anchor_lock:
            if self._anchor_vectors:
                return

            log.info("Computing Multi-Anchor embeddings for Semantic Intent Router v2...")
            computed: Dict[ChatIntent, List[List[float]]] = {}
            for intent, anchor_texts in self.SEMANTIC_ANCHORS.items():
                vectors = []
                for text in anchor_texts:
                    vec = await self.embedder.embed_text(text)
                    vectors.append(vec)
                computed[intent] = vectors

            self._anchor_vectors.update(computed)
            log.info("Multi-Anchor embeddings initialized successfully", categories=list(computed.keys()))

    async def classify(self, user_message: str, query_vector: Optional[List[float]] = None) -> IntentResult:
        """
        Phân loại intent của tin nhắn trả về IntentResult có đầy đủ confidence & semantic scores.
        """
        # ── L1: Small talk fast-path ──
        if self.is_small_talk(user_message):
            log.debug("Intent L1 fast-path: small talk detected")
            return IntentResult(
                intents=[ChatIntent.SMALL_TALK],
                confidence=1.0,
                routing_method="L1_SMALL_TALK",
                query_vector=None,
                semantic_scores={"SMALL_TALK": 1.0},
                routing_reason="L1 Small Talk regex/phrase fast-path matched"
            )

        msg_lower = user_message.strip().lower()
        high_conf_intents: List[ChatIntent] = []

        # ── L2: High-confidence keyword / pattern matching ──
        if _phrase_match(self._MEMORY_PHRASES, msg_lower):
            high_conf_intents.append(ChatIntent.MEMORY)

        if _phrase_match(self._LORE_PHRASES, msg_lower):
            high_conf_intents.append(ChatIntent.LORE)

        if _pattern_match(self._SYSTEM_PATTERNS, msg_lower):
            high_conf_intents.append(ChatIntent.SYSTEM_ACTION)

        if high_conf_intents:
            log.info("Intent L2 fast-path matched", intents=[i.value for i in high_conf_intents])
            scores = {i.value: 1.0 for i in high_conf_intents}
            return IntentResult(
                intents=high_conf_intents,
                confidence=1.0,
                routing_method="L2_KEYWORD",
                query_vector=query_vector,
                semantic_scores=scores,
                routing_reason=f"L2 Keyword match for {[i.value for i in high_conf_intents]}"
            )

        # ── L3: Multi-Anchor Cluster Semantic Classification ──
        if self.enable_l3 and self.embedder:
            try:
                if query_vector is None:
                    query_vector = await self.embedder.embed_text(user_message)

                await self._ensure_anchor_vectors()

                scores: Dict[str, float] = {}

                for intent, anchor_vecs in self._anchor_vectors.items():
                    max_sim = max((_cosine_similarity(query_vector, avec) for avec in anchor_vecs), default=0.0)
                    scores[intent.value] = round(max_sim, 3)

                best_intent_value = max(scores, key=scores.get)
                confidence = scores[best_intent_value]

                if confidence >= self.semantic_threshold:
                    best_intent = ChatIntent(best_intent_value)
                    # Lấy các intents có score tiệm cận best score (trong khoảng delta 0.035)
                    matched_intents = [
                        ChatIntent(cat) for cat, sc in scores.items()
                        if sc >= confidence - 0.035 and sc >= self.semantic_threshold
                    ]
                    # Sắp xếp để best_intent có score cao nhất luôn đứng đầu (index 0)
                    matched_intents.sort(key=lambda i: scores[i.value], reverse=True)
                    log.info(
                        "Intent L3 semantic router matched",
                        best_intent=best_intent.value,
                        confidence=confidence,
                        matched=[i.value for i in matched_intents],
                        scores=scores,
                    )
                    return IntentResult(
                        intents=matched_intents,
                        confidence=confidence,
                        routing_method="L3_SEMANTIC",
                        query_vector=query_vector,
                        semantic_scores=scores,
                        routing_reason=f"L3 Semantic match ({best_intent.value} score={confidence})"
                    )
                else:
                    # Tán gẫu tự do nhưng không dính Lore/Memory/System
                    max_score = max(scores.values()) if scores else 0.0
                    log.info("Intent L3 fallback to CONVERSATIONAL", scores=scores)
                    return IntentResult(
                        intents=[ChatIntent.CONVERSATIONAL],
                        confidence=max_score,
                        routing_method="L3_SEMANTIC",
                        query_vector=query_vector,
                        semantic_scores=scores,
                        routing_reason=f"L3 Semantic fallback to CONVERSATIONAL (max_score={max_score})"
                    )
            except Exception as e:
                log.warning("L3 Semantic routing failed, falling back to OTHER", error=str(e))

        # ── Fallback mặc định ──
        log.info("Intent fallback: returning OTHER")
        return IntentResult(
            intents=[ChatIntent.OTHER],
            confidence=0.0,
            routing_method="FALLBACK",
            query_vector=query_vector,
            semantic_scores={},
            routing_reason="Default fallback OTHER"
        )

