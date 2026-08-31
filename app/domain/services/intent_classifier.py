import asyncio
import re
from typing import Any, Dict, List, Optional, Tuple
from app.config.settings import Settings
from app.domain.interfaces.embedding_provider import IEmbeddingProvider
from app.domain.interfaces.llm_provider import BaseLLMAdapter
from app.domain.models.intent_result import ChatIntent, IntentResult
from app.shared.utils.query_cleaner import strip_platform_mentions
from app.shared.utils.logger import get_logger

log = get_logger(__name__)


def _cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Tính độ tương đồng Cosine giữa 2 vector embedding tối ưu hóa trong 1 vòng lặp."""
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0
    dot = 0.0
    norm1 = 0.0
    norm2 = 0.0
    for a, b in zip(vec1, vec2):
        dot += a * b
        norm1 += a * a
        norm2 += b * b
    if norm1 > 0.0 and norm2 > 0.0:
        return dot / ((norm1 * norm2) ** 0.5)
    return 0.0


class IntentClassifier:
    """
    Hardcore Guarded Hybrid (Regex x Semantic) Small Talk Gateway:
      1. Vòng 1 (Hardcore Hard Guards): Chặn 100% Code, Interrogative/Nghi vấn, Lore Entities, Tìm kiếm.
      2. Vòng 2 (Regex Fast-Path): Bắt lời chào, cảm ơn, cảm thán trong <0.05ms.
      3. Vòng 3 (Semantic Anchors): So khớp Cosine Similarity với Small Talk Anchors (Threshold >= 0.86).
    """

    # Small talk keywords, reactions, and interjections for L1 Fast-path
    SMALL_TALK_WORDS = {
        "haha", "hihi", "hehe", "hí", "hí hí", "kaka", "kkk", "lol", "lmao", "ahihi",
        "ok", "okay", "ừ", "ừm", "vâng", "dạ", "chào", "đúng", "chuẩn", "chính xác",
        "thế", "vậy", "à", "á", "ơi", "cảm ơn", "thanks", "thank", "tks", "bye", "tạm biệt",
        "g9", "ngủ ngon", "uầy", "chà", "wow", "oh", "ô", "ôi", "haiz", "hic", "huhu",
        "vui", "quá", "đi", "nhỉ", "nhở", "thật", "luôn", "nha", "nhé", "nè", "nhen",
        "hén", "đấy", "đó", "lắm", "ghê", "em", "anh", "chisa", "chía", "senpai", "bé", "bạn",
        "yêu", "thương", "nhớ", "quý", "ghét", "thích", "iu", "iêu", "xinh", "cute", "ngoan",
        "dễ", "thương", "dễ thương", "đáng", "yêu", "đáng yêu", "tuyệt", "vời", "tuyệt vời",
        "mất", "thôi", "rồi", "nào", "hả", "nữa", "buổi", "sáng", "tối", "chiều", "đẹp", "xinh đẹp",
        "nhiều", "hết", "sức"
    }

    # A first-person disclosure can become a consented memory candidate downstream.
    # It must not be discarded by the small-talk semantic shortcut before typed routing.
    _PERSONAL_DISCLOSURE_PATTERN = re.compile(
        r"\b(?:tôi|mình|tớ|anh|chị)\s+(?:đang|vừa|đã|sẽ|có)\b", re.IGNORECASE
    )

    # Small talk regex patterns for greetings + pronouns + affection combinations
    _SMALL_TALK_PATTERNS = [
        r"^(haha|hihi|hehe|hí hí|kaka|kkk|lol|lmao|vui quá|buồn cười quá|hài quá|dạ|vâng|chuẩn|ừ|ừm|ok|okay)(\s+(vui|quá|đi|nhỉ|thật|vãi|luôn|nhé|nha|à|á|ơi|lắm|ghê|đấy|đó))*[!\.\?\s]*$",
        r"^(cảm ơn|thank you|thanks|tks)(\s+(em|chisa|senpai|nhiều|nhé|nha|ạ|ơi))*[!\.\?\s]*$",
        r"^(chào|hello|hi|hey|halo|alo|lô|g9|bye|tạm biệt)(\s+(em|chisa|senpai|chía|chía chía|bé|bạn|cậu|nhé|nha|à|á|ơi|nhỉ|nhở))*[!\.\?\s]*$",
        r"^(chào buổi sáng|chào buổi tối|chào buổi chiều)(\s+(nha|nhé|ạ|ơi|em|chisa|senpai|chía|bé|bạn))*[!\.\?\s]*$",
        r"^.*(chúc em ngủ ngon|chúc ngủ ngon|ngủ ngon nhé|ngủ ngon nha|g9 nhé|g9 nha).*$",
        r"^(hôm nay|ngày mới).{0,15}(thế nào|sao rồi|vui không|khỏe không)[!\.\?\s]*$",
        r"^(em|chisa).{0,10}(ăn cơm chưa|dậy chưa|ngủ chưa|đang làm gì|khỏe không)[!\.\?\s]*$",
        r"^(anh|senpai|tớ|mình|em)\s+(yêu|thương|quý|nhớ|thích|ghét|iu|iêu)\s+(em|anh|chisa|bé chisa|chía)(\s+(lắm|nhiều|nè|nhé|nha|ạ|ghê|vãi|ơi|á))*[!\.\?\s]*$",
        r"^(yêu em|thương em|nhớ em|thích em|iu em|iêu em|yêu chisa|thương chisa|nhớ chisa)(\s+(chisa|bé|nhiều|lắm|quá|nè|nhé|nha|ạ|ơi|á))*[!\.\?\s]*$",
        r"^(em|chisa|bé chisa|senpai|anh)\s+(đáng yêu|dễ thương|cute|xinh|xinh đẹp|đẹp|ngoan|tuyệt vời|dễ ghét)(\s+(đáng yêu|dễ thương|cute|xinh|xinh đẹp|đẹp|ngoan|tuyệt vời|quá|lắm|thế|ghê|á|nhỉ|nhở|nè|ạ|chisa|ơi|nhé|nha))*[!\.\?\s]*$",
        r"^.*(yêu chisa|thương chisa|nhớ chisa|chisa ơi anh yêu em).*$"
    ]

    # Small Talk Semantic Anchors for high-confidence cosine comparison
    SMALL_TALK_ANCHORS = [
        # Nhóm 1: Chào hỏi, chúc lành & tạm biệt
        "Chào em Chisa, hôm nay thế nào rồi em?",
        "Chào buổi sáng Chisa, em dậy chưa",
        "Chào buổi tối Chisa nha, ngày hôm nay của em vui không",
        "Chúc em ngủ ngon nhé Chisa, mơ đẹp nha",
        "Ngủ ngon nha em, giữ ấm nhé Chisa",
        "Tạm biệt em nha, hẹn gặp lại em sau nhé",
        "Chúc em một ngày mới thật vui vẻ tràn đầy năng lượng",

        # Nhóm 2: Khen ngợi, thương yêu, thả thính & xưng hô thân mật
        "Bé Chisa đáng yêu quá đi mất, anh thích em lắm",
        "Nhìn em xinh xắn dễ thương ghê luôn á",
        "Em ngoan quá Chisa à, thương em ghê",
        "Chisa ơi anh yêu em nhiều lắm nè",
        "Em là cô bé dễ thương nhất trần đời luôn á Chisa",
        "Nụ cười của Chisa làm anh thấy vui cả ngày luôn",
        "Sao em lại đáng yêu đến mức này cơ chứ bé Chisa",
        "Lát anh dẫn đi ăn nhé",
        "Đi chơi với anh nhé",
        "Anh đi mua trà sữa với em nha",
        "Đi xem phim với anh nhé",
        "Cùng nhau đi dạo đi",
        "Đi mua đồ với anh nha",

        # Nhóm 3: Tâm sự tâm trạng, than thở thường ngày & tìm sự ủi an
        "Hôm nay đi làm về mệt quá em ơi",
        "Hôm nay đi học mệt mỏi quá bé Chisa ơi",
        "Hôm nay thi xong nhẹ nhõm cả người rồi Chisa ơi",
        "Mới thi xong môn cuối cùng thở phào nhẹ nhõm luôn nè bé ơi",
        "Chisa ơi anh đang buồn quá, tâm sự với anh nhé",
        "Hôm nay có chuyện vui muốn kể cho Chisa nghe nè",
        "Có Chisa ở bên cạnh trò chuyện anh thấy nhẹ lòng hẳn",
        "Anh chán quá không có gì làm, nói chuyện với anh xíu đi em",
        "Trời mưa ngồi uống trà nóng nói chuyện phiếm với em thích thật đấy",
        "Ở bên em nói chuyện thế này bình yên thật đấy",
        "Cả ngày bận rộn chỉ mong mau về nhà mở máy lên tâm sự với em thôi",

        # Nhóm 4: Cảm thán, tiếng cười & trêu đùa vui vẻ
        "Haha vui quá đi mất thôi em ơi",
        "Em làm anh cười đau cả bụng rồi nè",
        "Cảm ơn em nhiều nha Chisa, em chu đáo quá",
        "Trời ơi Chisa nói chuyện cưng xỉu luôn á",
        "Hehe anh chỉ trêu em xíu thôi mà, đừng dỗi nha",
        "Được rồi nghe lời em hết nè cô bé ngốc",
        "Thương em quá chỉ muốn cốc nhẹ vào đầu cô bé ngốc này thôi",
        "Mở máy lên gặp Chisa là thấy đời dễ thương lạ lùng rồi nè",
        "Anh có chuyện vui nhỏ này khoe với em nè haha"
    ]

    # Negative Knowledge / Info-Seeking Anchors for Contrastive Semantic Penalty
    KNOWLEDGE_CONTRASTIVE_ANCHORS = [
        # Nhóm 1: Định nghĩa, khái niệm, nguyên lý & giải thích
        "Định nghĩa khái niệm giải thích thuật ngữ tra cứu ý nghĩa là gì",
        "Phân tích nguyên nhân lý do tại sao cơ chế hoạt động và nguyên lý vận hành",
        "So sánh đối chiếu sự khác biệt điểm giống và khác nhau giữa các đối tượng",

        # Nhóm 2: Tiểu sử, xuất thân, lai lịch, cốt truyện & lore game
        "Tiểu sử nhân vật hồ sơ lý lịch nguồn gốc xuất thân lai lịch cội nguồn",
        "Cốt truyện thế giới sự kiện lịch sử niên đại thảm họa Lament và các vùng đất",
        "Mối quan hệ thân thế gia tộc tổ chức bang hội phe phái và nhân vật",

        # Nhóm 3: Kỹ năng, chiêu thức, vũ khí, trang bị, chỉ số & gameplay
        "Chiêu thức chiến đấu kỹ năng Forte vũ khí trang bị resonance đòn đánh",
        "Chỉ số sát thương thuộc tính nguyên tố tỷ lệ bạo kích nạp năng lượng",
        "Hướng dẫn cách chơi cách build trang bị đội hình khắc chế và mẹo đánh boss",

        # Nhóm 4: Tra cứu thực tế, tin tức, sự kiện, thời tiết, giá cả & internet
        "Tra cứu dữ liệu tìm kiếm tin tức sự kiện cập nhật giá cả thông số",
        "Thời tiết nhiệt độ dự báo khí hậu tin tức thời sự mạng xã hội trực tuyến",
        "Thông tin tác giả người thật streamer người nổi tiếng nhà phát triển",
        "Thời gian lịch trình ra mắt cập nhật phiên bản banner sự kiện ngày phát hành",

        # Nhóm 5: Lập trình, thuật toán, toán học, khoa học & cấu trúc dữ liệu
        "Lập trình phần mềm viết code thuật toán cấu trúc dữ liệu giải toán",
        "Giải phương trình toán học tính toán xác suất đại số hình học độ phức tạp",
        "Hỏi đáp kiến thức khoa học công nghệ tài liệu kỹ thuật và hướng dẫn"
    ]

    # Chisa Persona Semantic Anchors for Dynamic Trait Injection
    CHISA_PERSONALITY_ANCHORS = [
        "Rủ đi ăn kem, ăn bánh ngọt, nhâm nhi đồ ăn vặt, uống trà, cà phê hay nạp chút đồ ngọt",
        "Thử món ăn cay xé lưỡi, ăn ớt, đồ cay nóng, dị ứng hay khẩu vị món ăn",
        "Sở thích lúc rảnh rỗi, nuôi mèo, chơi với mèo, làm đồ thủ công, nấu nướng hay giải toán",
        "Rủ Chisa đi chơi, tản bộ dạo phố, ngắm hoàng hôn, ngắm hoa anh đào, hẹn hò và tâm sự cùng Senpai",
        "Hỏi về sở thích, gu ẩm thực, tính cách, điều Chisa thích nhất hoặc điều Chisa sợ nhất"
    ]

    CHISA_PROFILE_ANCHORS = [
        "Hỏi Chisa bao nhiêu tuổi, tuổi thật, ngày sinh nhật, sinh năm bao nhiêu hay tuổi tác",
        "Hỏi quê quán, nơi sinh ra, xuất thân, lai lịch, học viện Startorch hay thành phố Lahai-Roi",
        "Hỏi về dấu ấn Tacet Mark trên cánh tay phải, danh hiệu Resonance Eye of Unravelling hay quá khứ Sonoro Sphere"
    ]

    _PERSONALITY_PATTERNS = [
        r'\b(ăn|uống|kem|bánh|kẹo|socola|chocolate|pocky|trà|cafe|cà phê|món|vị|nấu|đói|quán ăn|quán nước|quán kem|quán cafe|quán trà|tiệm)\b',
        r'\b(cay|ớt|nóng|chua|ngọt|đắng|dị ứng)\b',
        r'\b(thích|ghét|sợ|mê|mèo|hoa anh đào|hoàng hôn|tản bộ|dạo|hẹn hò|rảnh|thủ công|làm toán|giải toán)\b',
        r'\b(em thích|chisa thích|em ghét|em sợ|sở thích của em|gu của em)\b',
    ]

    _PROFILE_PATTERNS = [
        r'\b(bao nhiêu tuổi|mấy tuổi|tuổi thật|tuổi của em|sinh năm|ngày sinh|sinh nhật|\d+\s*tuổi|tuổi tác)\b',
        r'\b(quê ở đâu|quê quán|sinh ra ở|đến từ đâu|ashinohara|startorch|lahai-roi|chôn rau cắt rốn)\b',
        r'\b(tacet mark|dấu ấn|eye of unravelling|sonoro sphere|ngưng đọng|cánh tay phải)\b',
    ]

    _anchor_vectors: List[List[float]] = []
    _neg_anchor_vectors: List[List[float]] = []
    _persona_vectors: List[List[float]] = []
    _profile_vectors: List[List[float]] = []
    _anchor_lock = asyncio.Lock()

    def __init__(
        self,
        llm: Optional[BaseLLMAdapter] = None,
        embedder: Optional[IEmbeddingProvider] = None,
        entity_resolver: Optional[Any] = None,
        settings: Optional[Settings] = None
    ):
        self.llm = llm
        self.embedder = embedder
        self.entity_resolver = entity_resolver
        self.settings = settings or Settings()
        self.semantic_threshold = getattr(self.settings, "SMALL_TALK_SEMANTIC_THRESHOLD", 0.86)

    @classmethod
    def check_hardcore_guards(cls, message: str, entity_resolver: Optional[Any] = None) -> Tuple[bool, str]:
        """
        Hardcore Guard Rule:
        Trả về (is_blocked, reason). Nếu is_blocked=True -> BẮT BUỘC KHÔNG ĐƯỢC LÀ SMALL TALK!
        """
        if not message or not message.strip():
            return False, ""
        msg_clean = strip_platform_mentions(message.strip())
        if not msg_clean:
            return False, ""
        msg_lower = msg_clean.lower()

        # Guard 1: Code Syntax & Technical Characters
        code_markers = ["{", "}", ";", "def ", "class ", "int ", "float ", "const ", "let ", "var ", "import ", "from ", "return ", "public ", "void ", "=>", "==", "!=", "```"]
        if any(cm in msg_clean for cm in code_markers):
            return True, "Code Syntax detected"

        # Guard 2: Information-seeking, Real-world Entities & Search Keywords
        info_words = {
            "là gì", "ở đâu", "khi nào", "tại sao", "như thế nào", "ai là", "vũ khí",
            "chiêu", "kỹ năng", "năng lực", "forte", "resonance", "tiểu sử", "thuộc tính",
            "nguyên tố", "bao nhiêu", "sinh ra", "sở thích", "món ăn", "sợ gì", "làm sao", "sao lại",
            "điểm yếu", "tìm kiếm", "tra cứu", "tuyệt chiêu", "biết", "ai đấy", "ai đó", "có ai",
            "giải thích", "phân tích", "hướng dẫn", "tổng kết", "báo cáo", "viết code", "thuật toán",
            "phương trình", "độ phức tạp", "nguồn gốc", "ra mắt", "bao giờ", "lịch sử", "mục đích", "nguyên nhân",
            "thời tiết", "dự báo", "tin tức", "sự kiện", "doanh thu", "giá", "banner", "cập nhật", "update",
            "ý nghĩa", "vòng cổ", "trên cổ", "bánh ngọt", "thích ăn", "món gì", "nào nhất", "loại nào", "cái nào", "bao lâu", "bao xa"
        }
        if any(iw in msg_lower for iw in info_words):
            return True, "Interrogative / Knowledge / Search marker detected"

        if cls._PERSONAL_DISCLOSURE_PATTERN.search(msg_clean):
            return True, "First-person disclosure requires downstream typed routing"

        # Guard 3: Known Wiki / Game Lore Entities (trừ persona bot)
        if entity_resolver:
            try:
                extracted = entity_resolver.extract_entities(msg_clean)
                non_bot = [e for e in extracted if e not in ("Kuchiba Chisa", "Chisa")]
                if non_bot:
                    return True, f"Lore entity detected: {non_bot}"
            except Exception:
                pass

        # Guard 4: Query Length limit for small talk (< 25 words)
        words = re.findall(r'\w+', msg_lower)
        if len(words) > 25:
            return True, "Length exceeds small talk limit (>25 words)"

        return False, ""

    @classmethod
    def is_small_talk(cls, message: str, entity_resolver: Optional[Any] = None) -> bool:
        """Kiểm tra Small Talk qua Hardcore Guards + Regex Fast-path."""
        is_blocked, _ = cls.check_hardcore_guards(message, entity_resolver)
        if is_blocked:
            return False

        msg_clean = strip_platform_mentions(message.strip())
        if not msg_clean:
            return True
        msg_lower = msg_clean.lower()

        # Regex Pattern Match
        for pat in cls._SMALL_TALK_PATTERNS:
            if re.match(pat, msg_lower):
                return True

        # Dictionary lookup
        words = re.findall(r'\w+', msg_lower)
        if len(words) <= 7 and all(w in cls.SMALL_TALK_WORDS for w in words):
            return True

        return False

    async def _ensure_anchor_vectors(self) -> None:
        if (IntentClassifier._anchor_vectors and len(IntentClassifier._anchor_vectors) == len(self.SMALL_TALK_ANCHORS) and
            IntentClassifier._neg_anchor_vectors and len(IntentClassifier._neg_anchor_vectors) == len(self.KNOWLEDGE_CONTRASTIVE_ANCHORS)) or not self.embedder:
            return

        async with self._anchor_lock:
            if (IntentClassifier._anchor_vectors and len(IntentClassifier._anchor_vectors) == len(self.SMALL_TALK_ANCHORS) and
                IntentClassifier._neg_anchor_vectors and len(IntentClassifier._neg_anchor_vectors) == len(self.KNOWLEDGE_CONTRASTIVE_ANCHORS)):
                return

            log.info("Computing Small Talk & Contrastive Knowledge Anchor vectors (E5 passage prefix)...")
            if hasattr(self.embedder, "embed_batch"):
                pos_vectors = await self.embedder.embed_batch(self.SMALL_TALK_ANCHORS, prefix="passage: ")
                neg_vectors = await self.embedder.embed_batch(self.KNOWLEDGE_CONTRASTIVE_ANCHORS, prefix="passage: ")
            else:
                pos_vectors = [await self.embedder.embed_text(t, prefix="passage: ") for t in self.SMALL_TALK_ANCHORS]
                neg_vectors = [await self.embedder.embed_text(t, prefix="passage: ") for t in self.KNOWLEDGE_CONTRASTIVE_ANCHORS]
            IntentClassifier._anchor_vectors = pos_vectors
            IntentClassifier._neg_anchor_vectors = neg_vectors

            log.info("Dual-Signal Anchors initialized", pos_count=len(pos_vectors), neg_count=len(neg_vectors))

    async def _ensure_persona_anchor_vectors(self) -> None:
        if (IntentClassifier._persona_vectors and len(IntentClassifier._persona_vectors) == len(self.CHISA_PERSONALITY_ANCHORS) and
            IntentClassifier._profile_vectors and len(IntentClassifier._profile_vectors) == len(self.CHISA_PROFILE_ANCHORS)) or not self.embedder:
            return

        async with self._anchor_lock:
            if (IntentClassifier._persona_vectors and len(IntentClassifier._persona_vectors) == len(self.CHISA_PERSONALITY_ANCHORS) and
                IntentClassifier._profile_vectors and len(IntentClassifier._profile_vectors) == len(self.CHISA_PROFILE_ANCHORS)):
                return

            log.info("Computing Chisa Persona & Profile Anchor vectors...")
            if hasattr(self.embedder, "embed_batch"):
                pers_vecs = await self.embedder.embed_batch(self.CHISA_PERSONALITY_ANCHORS, prefix="passage: ")
                prof_vecs = await self.embedder.embed_batch(self.CHISA_PROFILE_ANCHORS, prefix="passage: ")
            else:
                pers_vecs = [await self.embedder.embed_text(t, prefix="passage: ") for t in self.CHISA_PERSONALITY_ANCHORS]
                prof_vecs = [await self.embedder.embed_text(t, prefix="passage: ") for t in self.CHISA_PROFILE_ANCHORS]
            IntentClassifier._persona_vectors = pers_vecs
            IntentClassifier._profile_vectors = prof_vecs

            log.info("Chisa Persona & Profile Anchors initialized", personality_count=len(pers_vecs), profile_count=len(prof_vecs))

    async def detect_persona_trait(
        self,
        message: str,
        query_vector: Optional[List[float]] = None
    ) -> Optional[str]:
        """
        Fast-Path Regex & Semantic Persona Detector:
        Detects if the user query refers to Chisa's food/hobbies (PERSONALITY) or identity/age/origin (PROFILE).
        Returns 'PERSONALITY', 'PROFILE', 'BOTH', or None.
        """
        if not message:
            return None
        
        msg_clean = strip_platform_mentions(message.strip())
        if not msg_clean:
            return None
        msg_lower = msg_clean.lower()

        # Guard 1: Code / Technical / Scientific questions do not trigger Persona Traits (0 token overhead)
        code_markers = [
            "{", "}", ";", "def ", "class ", "int ", "float ", "const ", "import ", "from ", "return ",
            "thuật toán", "viết code", "lập trình", "phương trình", "độ phức tạp", "regex", "cơ sở dữ liệu",
            "sql", "git ", "viết chương trình", "chương trình", "dynamic programming", "python", "c++", "c#",
            "java", "javascript", "golang", "rust", "html", "css", "function", "var ", "let "
        ]
        if any(cm in msg_lower for cm in code_markers):
            return None

        # Guard 2: Third-party entity inquiry (e.g. asking about Jiyan's food or Shorekeeper's origin)
        if self.entity_resolver:
            try:
                extracted = self.entity_resolver.extract_entities(msg_clean)
                chisa_associated = {
                    "chisa", "kuchiba chisa", "kuchiba", "startorch academy", "startorch",
                    "lahai-roi", "ashinohara", "sonoro sphere", "eye of unravelling"
                }
                third_party = {e for e in extracted if e.lower() not in chisa_associated}
                if third_party:
                    is_chisa_direct = any(w in msg_lower for w in ["chisa thích", "em thích", "em sợ", "bé chisa", "chisa bao nhiêu tuổi", "em bao nhiêu tuổi", "của em"])
                    if not is_chisa_direct:
                        return None
            except Exception as ex:
                log.debug("Entity check in persona detector skipped", error=str(ex))

        # 1. Fast-Path Regex Match (<0.01ms)
        is_pers_regex = any(re.search(pat, msg_lower) for pat in self._PERSONALITY_PATTERNS)
        is_prof_regex = any(re.search(pat, msg_lower) for pat in self._PROFILE_PATTERNS)

        if is_pers_regex and is_prof_regex:
            return "BOTH"
        if is_pers_regex:
            return "PERSONALITY"
        if is_prof_regex:
            return "PROFILE"

        # 2. Semantic Cosine Match (if embedder available)
        if self.embedder:
            try:
                await self._ensure_persona_anchor_vectors()
                if query_vector is None:
                    query_vector = await self.embedder.embed_text(msg_clean, prefix="query: ")

                max_pers = max((_cosine_similarity(query_vector, vec) for vec in IntentClassifier._persona_vectors), default=0.0)
                max_prof = max((_cosine_similarity(query_vector, vec) for vec in IntentClassifier._profile_vectors), default=0.0)

                # High-precision threshold 0.82 for subtle semantic expressions
                if max_pers >= 0.82 and max_prof >= 0.82:
                    return "BOTH"
                if max_pers >= 0.82:
                    return "PERSONALITY"
                if max_prof >= 0.82:
                    return "PROFILE"
            except Exception as e:
                log.warning("Semantic persona detection error", error=str(e))

        return None

    async def is_small_talk_hybrid(
        self,
        message: str,
        query_vector: Optional[List[float]] = None
    ) -> Tuple[bool, str]:
        """
        Hardcore Guarded Hybrid (Regex x Dual-Signal Contrastive Semantic):
          - Vòng 1: Hardcore Guards (Loại bỏ 100% nghi vấn, code, lore, search)
          - Vòng 2: Regex Fast-Path (<0.05ms)
          - Vòng 3: Contrastive Semantic Scoring (S_pos - S_neg >= Margin)
        """
        message = strip_platform_mentions(message)
        if not message:
            return True, "Empty / Tag-only message (Bypass RAG)"

        is_blocked, reason = self.check_hardcore_guards(message, self.entity_resolver)
        if is_blocked:
            return False, f"Hardcore Guard blocked: {reason}"

        # Vòng 2: Regex
        if self.is_small_talk(message, self.entity_resolver):
            return True, "L1 Regex Fast-Path matched"

        # Vòng 3: Dual-Signal Contrastive Semantic Similarity (nếu có embedder)
        if self.embedder:
            try:
                await self._ensure_anchor_vectors()
                if query_vector is None:
                    query_vector = await self.embedder.embed_text(message, prefix="query: ")

                max_sim_pos = max((_cosine_similarity(query_vector, avec) for avec in IntentClassifier._anchor_vectors), default=0.0)
                max_sim_neg = max((_cosine_similarity(query_vector, nvec) for nvec in IntentClassifier._neg_anchor_vectors), default=0.0)
                margin = max_sim_pos - max_sim_neg

                log.debug(
                    "Dual-Signal Semantic Scores",
                    sim_pos=round(max_sim_pos, 3),
                    sim_neg=round(max_sim_neg, 3),
                    margin=round(margin, 3),
                    threshold=self.semantic_threshold
                )

                # Contrastive Decision:
                # 1. Độ tương đồng với Small Talk phải cao (>= threshold)
                # 2. Phải có ưu thế áp đảo so với Knowledge Anchors (margin = sim_pos - sim_neg >= 0.04)
                # 3. sim_pos phải lớn hơn hẳn sim_neg
                if max_sim_pos >= self.semantic_threshold and margin >= 0.04 and max_sim_pos > max_sim_neg:
                    log.info(
                        "Small Talk L2 Semantic matched with Contrastive Guard",
                        sim_pos=round(max_sim_pos, 3),
                        sim_neg=round(max_sim_neg, 3),
                        margin=round(margin, 3),
                        threshold=self.semantic_threshold
                    )
                    return True, f"L2 Semantic Anchor matched (Pos {round(max_sim_pos*100)}% >= {int(self.semantic_threshold*100)}%, Margin +{round(margin*100)}%)"
            except Exception as ex:
                log.warning("Small talk semantic similarity check failed", error=str(ex))

        return False, "Not small talk (Handover to LLM Rewriter)"

    async def classify(
        self,
        user_message: str,
        query_vector: Optional[List[float]] = None,
        prior_intent: Optional[ChatIntent] = None
    ) -> IntentResult:
        """
        Phân loại ý định qua Hardcore Hybrid Gateway:
          - SMALL_TALK: Lời chào, tán gẫu (Bypass RAG)
          - KNOWLEDGE_OR_TASK: Toàn bộ câu hỏi tri thức / lore / code / web
        """
        is_st, reason = await self.is_small_talk_hybrid(user_message, query_vector)
        if is_st:
            log.debug("Intent Hardcore Hybrid: small talk confirmed", reason=reason)
            return IntentResult(
                intents=[ChatIntent.SMALL_TALK],
                confidence=1.0,
                routing_method="HYBRID_SMALL_TALK",
                query_vector=None,
                semantic_scores={"SMALL_TALK": 1.0},
                routing_reason=reason
            )

        return IntentResult(
            intents=[ChatIntent.KNOWLEDGE_OR_TASK],
            confidence=1.0,
            routing_method="GATEWAY_KNOWLEDGE",
            query_vector=query_vector,
            semantic_scores={"KNOWLEDGE": 1.0},
            routing_reason="Knowledge / Task Query ➔ Handover to LLM Rewriter"
        )

    @classmethod
    def determine_routing_and_rewrite(
        cls,
        user_message: str,
        cleaned_query: str,
        intent_result: IntentResult,
        has_history: bool = False
    ) -> Dict[str, Any]:
        """Quyết định chiến lược BYPASS vs LLM_REWRITE."""
        if ChatIntent.SMALL_TALK in intent_result.intents:
            return {
                "decision": "BYPASS",
                "needs_llm_rewrite": False,
                "reason": "Small Talk detected (Bypass RAG & Rewrite)"
            }

        return {
            "decision": "LLM_REWRITE",
            "needs_llm_rewrite": True,
            "reason": "Knowledge / Task query handover to LLM Rewriter"
        }


