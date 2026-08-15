import asyncio
import math
import re
from typing import Any, Dict, List, Optional
from app.config.settings import Settings
from app.config.system_patterns import ALL_SYSTEM_PATTERNS
from app.domain.interfaces.embedding_provider import IEmbeddingProvider
from app.domain.interfaces.llm_provider import BaseLLMAdapter
from app.domain.models.intent_result import ChatIntent, IntentResult
from app.shared.utils.query_cleaner import has_coreference_markers
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

    # Small talk keywords, reactions, and interjections for L1 Fast-path
    SMALL_TALK_WORDS = {
        "haha", "hihi", "hehe", "hí", "hí hí", "kaka", "kkk", "lol", "lmao", "ahihi",
        "ok", "okay", "ừ", "ừm", "vâng", "dạ", "chào", "đúng", "chuẩn", "chính xác",
        "thế", "vậy", "à", "ơi", "cảm ơn", "thanks", "thank", "tks", "bye", "tạm biệt",
        "g9", "ngủ ngon", "uầy", "chà", "wow", "oh", "ô", "ôi", "haiz", "hic", "huhu",
        "vui", "quá", "đi", "nhỉ", "nhở", "thật", "luôn", "nha", "nhé", "nè", "nhen",
        "hén", "đấy", "đó", "lắm", "ghê", "em", "anh", "chisa", "chía", "senpai", "bé", "bạn",
        "yêu", "thương", "nhớ", "quý", "ghét", "thích", "iu", "iêu", "xinh", "cute", "ngoan",
        "dễ thương", "đáng yêu", "tuyệt vời"
    }

    # Small talk regex patterns for greetings + pronouns + affection combinations
    _SMALL_TALK_PATTERNS = [
        r"^(haha|hihi|hehe|hí hí|kaka|kkk|lol|lmao|vui quá|buồn cười quá|hài quá|dạ|vâng|chuẩn|ừ|ừm|ok|okay)(\s+(vui|quá|đi|nhỉ|thật|vãi|luôn|nhé|nha|à|ơi|lắm|ghê|đấy|đó))*[!\.\?\s]*$",
        r"^(cảm ơn|thank you|thanks|tks)(\s+(em|chisa|senpai|nhiều|nhé|nha|ạ))*[!\.\?\s]*$",
        r"^(chào|hello|hi|hey|halo|alo|lô|g9|bye|tạm biệt)(\s+(em|chisa|senpai|chía|chía chía|bé|bạn|cậu|nhé|nha|à|ơi|nhỉ|nhở))*[!\.\?\s]*$",
        r"^(chào buổi sáng|chào buổi tối|chào buổi chiều)(\s+(em|chisa|senpai|chía|bé|bạn))*[!\.\?\s]*$",
        r"^.*(chúc em ngủ ngon|chúc ngủ ngon|ngủ ngon nhé|ngủ ngon nha|g9 nhé|g9 nha).*$",
        r"^(hôm nay|ngày mới).{0,15}(thế nào|sao rồi|vui không|khỏe không)[!\.\?\s]*$",
        r"^(em|chisa).{0,10}(ăn cơm chưa|dậy chưa|ngủ chưa|đang làm gì|khỏe không)[!\.\?\s]*$",
        r"^(anh|senpai|tớ|mình|em)\s+(yêu|thương|quý|nhớ|thích|ghét|iu|iêu)\s+(em|anh|chisa|bé chisa|chía)(\s+(lắm|nhiều|nè|nhé|nha|ạ|ghê|vãi))*[!\.\?\s]*$",
        r"^(yêu em|thương em|nhớ em|thích em|iu em|iêu em)(\s+(lắm|nhiều|quá|nhé|nha|ạ))*[!\.\?\s]*$",
        r"^(em|chisa|bé chisa)\s+(đáng yêu|dễ thương|cute|xinh|ngoan|tuyệt vời|dễ ghét)(\s+(quá|lắm|thế|ghê|nhỉ|nhở|nè|ạ))*[!\.\?\s]*$",
        r"^.*(yêu chisa|thương chisa|nhớ chisa|chisa ơi anh yêu em).*$"
    ]

    # Multi-Anchor Clusters cho L3 Semantic Vector Classification (SOTA Domain Disambiguation)
    # LƯU Ý: SMALL_TALK được xử lý 100% ở L1 Fast-path, KHÔNG đưa vào L3 để tránh ô nhiễm không gian vector.
    SEMANTIC_ANCHORS: Dict[ChatIntent, List[str]] = {
        ChatIntent.LORE: [
            "Vũ khí, trang bị, vật phẩm, cổ vật, kiếm Broadblade, súng Pistols, chuông, pháp khí, thánh tích trong game",
            "Hồ sơ nhân vật Wuthering Waves, Resonator Chisa, Chixia, Jiyan, Sanhua, Yinlin, Camellya, Shorekeeper",
            "Kỹ năng chiến đấu, chiêu thức resonance liberation, năng lực forte, tacet mark, thuộc tính nguyên tố Glacio, Fusion, Aero",
            "Cơ chế chiến đấu combat, phản đòn parry khi quái sáng mắt đỏ, né đòn né tránh dodge, luân chuyển nhân vật",
            "Khắc chế thuộc tính nguyên tố, sát thương bạo kích crit rate, nạp năng lượng energy regen, hiệu ứng vỡ giáp",
            "Quái vật Tacet Discord, quái dị biến, Dị Loại Thần Ma Threnodian, rồng Thanh Long Qingloong, linh thú Thánh Thú Jue",
            "Thế giới Solaris-3, thành phố Jinzhou, Thừa Tiêu Sơn Mt. Firmament, Biển Đen Black Shores, Huanglong, Norfall Barrens",
            "Cốt truyện game Wuthering Waves, hiện tượng Mưa ngược Retroact Rain, Thảm họa Lament, Sonoro Sphere, Tacet Field",
            "Tổ chức Dạ Hành Quân Midnight Rangers, Tàn Tinh Hội Fractsidus, Viện Huaxu, Tướng quân Geshu Lin",
            "Vật phẩm trong game, chuông báo tử, hộp lưu trữ, lõi năng lượng, thiết bị Chronosorter, quặng Lampylumen"
        ],
        ChatIntent.MEMORY: [
            "Thông tin cá nhân của người dùng Senpai, tên thật của anh, biệt danh, tuổi tác, quê quán, nơi ở",
            "Công việc, nghề nghiệp, nơi làm việc của anh, lịch trình phỏng vấn công việc, thi cử, kế hoạch tương lai",
            "Kỷ niệm riêng tư, lời hứa giữa hai người, chuyện cá nhân anh đã kể, hôm trước anh dặn em điều gì",
            "Sở thích cá nhân của Senpai, món ăn anh thích, món anh bị dị ứng, gu âm nhạc, thói quen sinh hoạt"
        ],
        ChatIntent.SYSTEM_ACTION: [
            "Tóm tắt cuộc trò chuyện, tổng hợp điểm chính của buổi chat, ghi lại nội dung từ nãy đến giờ",
            "Xem báo cáo cảm xúc, chỉ số tâm trạng hiện tại, biểu đồ cảm xúc của em, phân tích gắn kết",
            "Tìm kiếm thông tin trên internet, tra cứu web, search google thông tin mới trên mạng xã hội",
            "Tra cứu dữ liệu thời gian thực, tin tức mạng, sự kiện trực tuyến mới nhất hôm nay"
        ],
        ChatIntent.CONVERSATIONAL: [
            "Quan điểm của em về tình bạn, tình yêu, các mối quan hệ, nhân sinh quan và ý nghĩa cuộc sống",
            "Tâm sự cảm xúc cá nhân, chia sẻ nỗi buồn, áp lực công việc, mệt mỏi, niềm vui đời thường hôm nay",
            "Hỏi ý kiến, xin lời khuyên, thảo luận triết lý sống và chia sẻ tâm trạng cởi mở với nhau",
            "Trò chuyện phiếm diện tự do, bàn luận về cuộc đời, trao đổi quan điểm cá nhân"
        ]
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
        "resonance của em", "forte của chisa", "forte của em", "em sợ điều gì", "điểm yếu của em",
        "tiểu sử của em", "lý lịch của em", "năng lực của em", "em có năng lực gì",
        "năng lực của em là gì", "năng lực của chisa", "chisa có năng lực gì", "em có tuyệt chiêu gì",
        "em dùng vũ khí gì", "em hệ gì", "nguyên tố của em", "em chiến đấu thế nào",
        "thuộc tính nguyên tố của em", "dấu ấn tacet mark của em",
        "sonoro sphere", "tacet discord", "solaris-3", "solaris 3",
        "lahai-roi", "mutant resonator", "resonator là gì", "tacet field là gì",
        "echo là gì", "resonance liberation", "fracidust", "black shores", "huanglong",
        "jinzhou ở đâu", "thành phố jinzhou", "vòng lặp honami", "lễ hội startorch",
        "học viện startorch", "companion quest", "chapter 3", "cốt truyện chapter",
        "nhật ký của sumika", "startorch school festival"
    ]

    _SYSTEM_PATTERNS = ALL_SYSTEM_PATTERNS

    def __init__(
        self,
        llm: BaseLLMAdapter,
        embedder: Optional[IEmbeddingProvider] = None,
        entity_resolver: Optional[Any] = None,
        settings: Optional[Settings] = None
    ):
        self.llm = llm
        self.embedder = embedder
        self.entity_resolver = entity_resolver
        self.settings = settings or Settings()
        self.semantic_threshold = getattr(self.settings, "INTENT_SEMANTIC_THRESHOLD", 0.65)
        self.enable_l3 = getattr(self.settings, "INTENT_ENABLE_L3_SEMANTIC", True)

    @classmethod
    def is_small_talk(cls, message: str) -> bool:
        if not message:
            return True
        msg_lower = message.strip().lower()

        # Information-seeking guard: If message is asking for info, it is NEVER small talk
        info_words = {
            "là gì", "ở đâu", "khi nào", "tại sao", "như thế nào", "ai là", "vũ khí",
            "chiêu", "kỹ năng", "năng lực", "forte", "resonance", "tiểu sử", "thuộc tính",
            "nguyên tố", "bao nhiêu tuổi", "sinh ra", "sở thích", "món ăn", "sợ gì",
            "điểm yếu", "tìm kiếm", "tra cứu", "tuyệt chiêu"
        }
        if any(iw in msg_lower for iw in info_words):
            return False

        for pat in cls._SMALL_TALK_PATTERNS:
            if re.match(pat, msg_lower):
                return True

        words = re.findall(r'\w+', msg_lower)
        if len(words) <= 5 and all(w in cls.SMALL_TALK_WORDS for w in words):
            return True

        return False

    async def _ensure_anchor_vectors(self) -> None:
        if self._anchor_vectors or not self.embedder:
            return

        async with self._anchor_lock:
            if self._anchor_vectors:
                return

            log.info("Computing Multi-Anchor embeddings for Semantic Intent Router v2 (E5 passage prefix)...")
            computed: Dict[ChatIntent, List[List[float]]] = {}
            for intent, anchor_texts in self.SEMANTIC_ANCHORS.items():
                vectors = []
                for text in anchor_texts:
                    vec = await self.embedder.embed_text(text, prefix="passage: ")
                    vectors.append(vec)
                computed[intent] = vectors

            self._anchor_vectors.update(computed)
            log.info("Multi-Anchor embeddings initialized successfully", categories=list(computed.keys()))

    async def classify(
        self,
        user_message: str,
        query_vector: Optional[List[float]] = None,
        prior_intent: Optional[ChatIntent] = None
    ) -> IntentResult:
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

        if self.entity_resolver:
            try:
                extracted = self.entity_resolver.extract_entities(user_message)
                non_bot_entities = [e for e in extracted if e not in ("Kuchiba Chisa", "Chisa")]
                if non_bot_entities:
                    high_conf_intents.append(ChatIntent.LORE)
                elif extracted and any(kw in msg_lower for kw in ("vũ khí", "forte", "resonance", "tiểu sử", "sinh ra", "bao nhiêu tuổi", "món ăn", "bánh", "sợ", "điểm yếu")):
                    high_conf_intents.append(ChatIntent.LORE)
            except Exception:
                pass

        if _phrase_match(self._MEMORY_PHRASES, msg_lower) and ChatIntent.MEMORY not in high_conf_intents:
            high_conf_intents.append(ChatIntent.MEMORY)

        if _phrase_match(self._LORE_PHRASES, msg_lower) and ChatIntent.LORE not in high_conf_intents:
            high_conf_intents.append(ChatIntent.LORE)

        if _pattern_match(self._SYSTEM_PATTERNS, msg_lower) and ChatIntent.SYSTEM_ACTION not in high_conf_intents:
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

        if self.enable_l3 and self.embedder:
            try:
                if query_vector is None:
                    query_vector = await self.embedder.embed_text(user_message, prefix="query: ")

                await self._ensure_anchor_vectors()

                raw_scores: Dict[str, float] = {}
                for intent, anchor_vecs in self._anchor_vectors.items():
                    max_sim = max((_cosine_similarity(query_vector, avec) for avec in anchor_vecs), default=0.0)
                    raw_scores[intent.value] = max_sim

                # Contextual Intent Momentum: Boost prior intent if question is short or has coreference
                if prior_intent and prior_intent.value in raw_scores:
                    if has_coreference_markers(user_message) or len(user_message.split()) <= 5:
                        raw_scores[prior_intent.value] += 0.035
                        log.debug("Applied contextual momentum boost", intent=prior_intent.value, boost=0.035)

                # Softmax Temperature Scaling (T = 0.035) for calibrated sharp probability distribution
                max_raw = max(raw_scores.values()) if raw_scores else 0.0
                exp_scores = {k: math.exp((v - max_raw) / 0.035) for k, v in raw_scores.items()}
                sum_exp = sum(exp_scores.values()) or 1.0
                probs: Dict[str, float] = {k: round(v / sum_exp, 3) for k, v in exp_scores.items()}

                best_intent_value = max(probs, key=probs.get)
                confidence = probs[best_intent_value]
                best_intent = ChatIntent(best_intent_value)

                # Multi-label Intent Selection
                matched_intents: List[ChatIntent] = []
                if best_intent == ChatIntent.LORE or probs.get("LORE", 0.0) >= 0.35:
                    matched_intents = [ChatIntent.LORE]
                else:
                    # Support dual execution for MEMORY and CONVERSATIONAL if both have meaningful signal (prob >= 0.20)
                    for cat, p in probs.items():
                        if p >= 0.20:
                            matched_intents.append(ChatIntent(cat))

                if not matched_intents:
                    matched_intents = [best_intent]

                matched_intents.sort(key=lambda i: probs.get(i.value, 0.0), reverse=True)
                log.info(
                    "Intent L3 semantic router matched (Softmax T=0.035)",
                    best_intent=best_intent.value,
                    confidence=confidence,
                    matched=[i.value for i in matched_intents],
                    probs=probs,
                    raw_scores={k: round(v, 3) for k, v in raw_scores.items()}
                )
                return IntentResult(
                    intents=matched_intents,
                    confidence=confidence,
                    routing_method="L3_SEMANTIC",
                    query_vector=query_vector,
                    semantic_scores=probs,
                    routing_reason=f"L3 Semantic match: {best_intent.value} ({int(confidence*100)}%)"
                )
            except Exception as e:
                log.warning("L3 Semantic routing failed, falling back to OTHER", error=str(e))

        log.info("Intent fallback: returning OTHER")
        return IntentResult(
            intents=[ChatIntent.OTHER],
            confidence=0.0,
            routing_method="FALLBACK",
            query_vector=query_vector,
            semantic_scores={},
            routing_reason="Default fallback OTHER"
        )

    @classmethod
    def determine_routing_and_rewrite(
        cls,
        user_message: str,
        cleaned_query: str,
        intent_result: IntentResult,
        has_history: bool = False
    ) -> Dict[str, Any]:
        """
        Decision Matrix:
          - BYPASS: 0 tokens, 0ms (Skip RAG & Rewrite ONLY for pure Small-Talk)
          - LLM_REWRITE: DeepSeek V4 Flash (~40 tokens, ~100-200ms) for ALL non-small-talk queries
            (Guarantees SOTA query reformulation, persona disambiguation, relationship reasoning, and keyword expansion)
        """
        knowledge_intents = {ChatIntent.LORE, ChatIntent.MEMORY, ChatIntent.SYSTEM_ACTION}
        
        # 1. Pure Small Talk Gate -> BYPASS (0 tokens, 0ms)
        if ChatIntent.SMALL_TALK in intent_result.intents and not any(ki in intent_result.intents for ki in knowledge_intents):
            return {
                "decision": "BYPASS",
                "needs_llm_rewrite": False,
                "reason": "Small Talk detected (Bỏ qua RAG & Rewrite)"
            }

        # 2. Non-Small-Talk queries -> LLM_REWRITE (Mặc định dùng LLM Rewrite cho toàn bộ Lore, Memory, System & Conversational có hỏi đáp)
        reason_detail = "Multi-turn coreference resolution" if (has_history and has_coreference_markers(user_message)) else "Knowledge-grounded query expansion & persona disambiguation"
        return {
            "decision": "LLM_REWRITE",
            "needs_llm_rewrite": True,
            "reason": reason_detail
        }


