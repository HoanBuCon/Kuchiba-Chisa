import asyncio
import numpy as np
from typing import List, Dict, Optional, Set
from app.domain.services.production_pipeline.intent_classifier import ChatIntent
from app.domain.interfaces.embedding_provider import IEmbeddingProvider
from app.infrastructure.logging.logger import get_logger

log = get_logger(__name__)

# Anchors definition for semantic routing.
# Each entry is a list of (anchor_text, is_explicit) tuples.
# is_explicit=True → câu mẫu ra lệnh tường minh → nhận score bonus khi match.
ROUTER_ANCHORS: Dict[ChatIntent, List[tuple]] = {
    ChatIntent.CHARACTER_LORE: [
        # --- Ngoại hình & trang bị ---
        ("vũ khí của em là gì", False),
        ("vòng ở cổ em để làm gì", False),
        ("kéo của em để làm gì", False),
        ("em trông như thế nào", False),
        ("tóc của em màu gì vậy", False),
        # --- Sở thích & thói quen ---
        ("chisa thích ăn món gì", False),
        ("sở thích của em là gì", False),
        ("món tủ của chisa", False),
        ("chisa thích ăn vặt gì", False),
        ("em thích làm gì nhất lúc rảnh", False),
        ("em có thói quen gì đặc biệt không", False),
        # --- Thân thế & xuất xứ ---
        ("em bao nhiêu tuổi thế", False),
        ("em học trường nào", False),
        ("em sinh ra ở đâu vậy", False),
        ("gia đình của em thế nào", False),
        ("em có anh chị em ruột không", False),
        # --- Tính cách & tâm lý ---
        ("tính cách của em thế nào", False),
        ("em có điểm yếu gì không", False),
        ("em sợ điều gì nhất", False),
        ("em thích điều gì nhất trong cuộc sống", False),
        ("điều gì khiến em vui nhất", False),
        ("em có bạn bè thân thiết không", False),
        # --- Năng lực & chiến đấu ---
        ("resonance của em là gì", False),
        ("forte của chisa là gì", False),
        ("em mạnh nhất ở điểm nào", False),
        ("em có kỹ năng gì ngoài chiến đấu", False),
        ("kỹ năng đặc biệt của chisa là gì", False),
    ],
    ChatIntent.WORLD_LORE: [
        # --- Khái niệm cốt lõi ---
        ("sonoro sphere là gì", False),
        ("tacet discord xuất hiện từ đâu", False),
        ("resonator là gì giải thích giúp anh", False),
        ("tacet field là gì", False),
        ("mutant resonator là gì", False),
        ("echo là gì trong wuthering waves", False),
        ("resonance liberation hoạt động thế nào", False),
        # --- Địa danh & tổ chức ---
        ("thành phố Jinzhou ở đâu", False),
        ("Lahai-roi ở đâu", False),
        ("Huanglong nằm ở đâu trong thế giới game", False),
        ("Aether Union là tổ chức gì", False),
        ("Montcalm là gì vậy", False),
        ("Black Shores là nơi nào", False),
        ("thế giới trong game có bao nhiêu vùng", False),
        # --- Cơ chế & lịch sử thế giới ---
        ("năng lượng tacet field hoạt động thế nào", False),
        ("concerto mechanic trong game là gì", False),
        ("nguyên nhân nào dẫn đến thảm họa tacet discord", False),
        ("forgery challenge trong game là gì", False),
        ("overworld trong wuthering waves có gì đặc biệt", False),
    ],
    ChatIntent.STORY_LORE: [
        # --- Cốt truyện chính ---
        ("cốt truyện chapter 3", False),
        ("ending của chapter 1 là gì", False),
        ("nội dung chính của act 2 là gì", False),
        ("rover là ai trong cốt truyện", False),
        ("crownless đến từ đâu", False),
        # --- Arc Honami & vòng lặp ---
        ("vòng lặp của honami là gì", False),
        ("làm sao em sống sót qua vòng lặp", False),
        ("chisa đã trải qua những gì trong vòng lặp", False),
        ("vòng lặp thời gian xảy ra như thế nào", False),
        # --- Arc Startorch & Sumika ---
        ("lễ hội startorch", False),
        ("sự kiện startorch school festival", False),
        ("câu chuyện của sumika", False),
        ("nhật ký của sumika nói gì", False),
        ("sự kiện đêm trước startorch xảy ra gì", False),
        # --- Mối quan hệ nhân vật ---
        ("mối quan hệ của chisa với jiyan là gì", False),
        ("chisa và phrolova có quen nhau không", False),
        ("senpai trong truyện là ai", False),
        ("honami và chisa có mối liên hệ gì", False),
    ],
    ChatIntent.MEMORY: [
        # --- Danh tính người dùng ---
        ("anh tên là gì em nhớ không", False),
        ("biệt danh của anh là gì", False),
        ("tên của anh là gì", False),
        ("anh đang làm nghề gì thế", False),
        ("anh bao nhiêu tuổi nhỉ", False),
        # --- Ký ức & hứa hẹn ---
        ("hôm qua anh đã hứa gì với em", False),
        ("ngày mai anh có bài phỏng vấn ở đâu", False),
        ("hôm trước anh nói gì với em nhớ không", False),
        ("lần trước chúng ta đã đồng ý điều gì", False),
        ("anh đã từng kể về gia đình chưa", False),
        # --- Sở thích & cá nhân ---
        ("ngày trước anh kể cho em nghe về sở thích của anh chưa", False),
        ("sở thích của anh là gì", False),
        ("anh thích thể loại nhạc nào", False),
        ("anh có nhắc đến ước mơ của anh không", False),
        ("anh thích đọc sách gì", False),
        ("anh chơi game nào ngoài wuthering waves", False),
        # --- Mối quan hệ ---
        ("chúng ta gặp nhau thế nào", False),
        ("anh và em quen nhau bao lâu rồi", False),
        ("kỷ niệm đầu tiên của chúng ta là gì", False),
    ],
    ChatIntent.SYSTEM_ACTION: [
        # === SUMMARIZE CONVERSATION ===
        ("tóm tắt lại nội dung cuộc trò chuyện nãy giờ giúp anh", True),
        ("hãy tổng hợp lại câu chuyện của chúng ta đi em", True),
        ("tóm tắt cuộc hội thoại này lại cho anh nghe", True),
        ("nãy giờ chúng ta đã nói về những gì rồi nhỉ", True),
        ("em tóm tắt ngắn gọn cuộc trò chuyện của chúng ta đi", True),
        ("tổng kết lại những gì nãy giờ anh và em nói đi", True),
        ("em ghi lại những điểm chính cuộc trò chuyện này giúp anh", True),
        ("cho anh xem tóm tắt cuộc hội thoại hôm nay", True),
        # === EMOTION REPORT ===
        ("hiển thị bảng đo cảm xúc của em đi", True),
        ("cho anh xem chỉ số cảm xúc hiện tại của em", True),
        ("em đang cảm thấy thế nào bây giờ theo số liệu", False),
        ("xuất báo cáo cảm xúc của em ra đi", True),
        ("em cho anh xem tâm trạng hiện tại theo số liệu", True),
        # === EXPLICIT WEB SEARCH ===
        ("tra mạng giúp anh tin tức này", True),
        ("em lên mạng tìm hiểu xem sao nhé", True),
        ("search google giúp anh với", True),
        ("em tra cứu trên internet giúp anh được không", True),
        ("lên mạng kiểm tra tin tức mới nhất giúp anh", True),
        ("em tìm kiếm trên internet thông tin này cho anh", True),
        ("tra cứu giúp anh xem có cập nhật mới chưa", True),
        ("em search giúp anh xem phiên bản wuthering waves mới nhất", True),
        ("lên google xem banner wuthering waves tháng này là gì", True),
        ("tra mạng xem wuthering waves có sự kiện gì mới không", True),
        ("em tìm giúp anh thông tin này trên internet", True),
        ("lên web kiểm tra xem có tin tức gì chưa", True),
        ("tra xem sự kiện game này diễn ra thế nào", True),
    ]
}

# Score bonus cộng thêm vào cosine similarity khi câu query khớp với explicit anchor.
# Cosine similarity không thể scale bằng nhân scalar nên dùng additive offset.
EXPLICIT_ANCHOR_BONUS = 0.04

# Ngưỡng khoảng cách tối thiểu (Top1 − Top2) để coi routing là "tự tin".
# Nếu nhỏ hơn ngưỡng này → model đang phân vân → áp dụng keyword guard chặt hơn.
CONFIDENCE_MARGIN_MIN = 0.05


class SemanticRouter:
    """
    Tầng 1 - Định tuyến ngữ nghĩa dựa trên Cosine Similarity sử dụng NumPy.
    Tái sử dụng vector embedding của câu hỏi người dùng để tối ưu tài nguyên.

    Cải tiến:
    - Confidence Margin: so sánh gap giữa Top1 và Top2, phát hiện trường hợp
      model phân vân để tăng cường keyword guard.
    - Explicit Anchor Bonus: cộng offset nhỏ vào score khi best-matching anchor
      là câu mẫu tường minh (is_explicit=True), thay thế cho scalar multiplication
      vốn vô hiệu lực với cosine similarity.
    """
    def __init__(self, embedder: IEmbeddingProvider, threshold: float = 0.65):
        self.embedder = embedder
        self.threshold = threshold
        # Lưu ma trận embeddings: (N x D)
        self.route_embeddings: Dict[ChatIntent, np.ndarray] = {}
        # Lưu set index của các anchor "explicit" theo từng intent
        self.explicit_indices: Dict[ChatIntent, Set[int]] = {}
        self._lock = asyncio.Lock()
        self._initialized = False

    async def initialize(self) -> None:
        """Sinh và cache các vector embedding của các Anchors vào bộ nhớ RAM"""
        async with self._lock:
            if self._initialized:
                return

            log.info("Initializing Semantic Router anchors...")
            for intent, anchor_tuples in ROUTER_ANCHORS.items():
                vectors = []
                explicit_idx: Set[int] = set()
                for i, (text, is_explicit) in enumerate(anchor_tuples):
                    try:
                        vec = await self.embedder.embed_text(text)
                        vectors.append(vec)
                        if is_explicit:
                            explicit_idx.add(i)
                    except Exception as e:
                        log.error("Failed to embed anchor text", text=text, error=str(e))
                if vectors:
                    self.route_embeddings[intent] = np.array(vectors)
                    self.explicit_indices[intent] = explicit_idx

            self._initialized = True
            log.info("Semantic Router anchors initialized successfully ✓")

    def _cosine_similarity(self, q_vec: np.ndarray, anchor_matrix: np.ndarray) -> np.ndarray:
        """Tính cosine similarity giữa vector truy vấn và ma trận anchors"""
        dot_product = np.dot(anchor_matrix, q_vec)
        norm_q = np.linalg.norm(q_vec)
        norm_anchors = np.linalg.norm(anchor_matrix, axis=1)
        # Tránh chia cho 0
        return dot_product / (norm_q * norm_anchors + 1e-9)

    def _score_with_explicit_bonus(
        self,
        similarities: np.ndarray,
        explicit_indices: Set[int],
    ) -> float:
        """
        Trả về max similarity có áp dụng explicit anchor bonus.

        Vì cosine similarity bất biến với scalar multiplication (1.1·v không đổi score),
        ta dùng additive offset: nếu best-matching anchor nằm trong explicit_indices,
        cộng thêm EXPLICIT_ANCHOR_BONUS vào score.

        Không cap ở 1.0 vì giá trị sau bonus chỉ dùng để so sánh tương đối giữa intents.
        """
        best_idx = int(np.argmax(similarities))
        base_score = float(similarities[best_idx])
        if best_idx in explicit_indices:
            return base_score + EXPLICIT_ANCHOR_BONUS
        return base_score

    async def classify(self, user_message: str, query_vector: Optional[List[float]] = None) -> List[ChatIntent]:
        """Phân loại tin nhắn dựa trên khoảng cách vector ngữ nghĩa"""
        if not self._initialized:
            await self.initialize()

        if query_vector is None:
            # Fallback nếu vector chưa được sinh ở ngoài
            log.debug("No pre-computed query vector provided to SemanticRouter, generating one now")
            query_vector = await self.embedder.embed_text(user_message)

        q_vec = np.array(query_vector)
        intent_scores: Dict[ChatIntent, float] = {}

        for intent, anchor_matrix in self.route_embeddings.items():
            similarities = self._cosine_similarity(q_vec, anchor_matrix)
            # Áp dụng explicit bonus sau khi tính cosine (additive, không phải scalar multiply)
            score = self._score_with_explicit_bonus(similarities, self.explicit_indices.get(intent, set()))
            intent_scores[intent] = score
            log.debug("Semantic router score check", intent=intent.value, score=round(score, 4))

        if not intent_scores:
            return []

        # --- Confidence Margin: so sánh Top1 và Top2 ---
        sorted_intents = sorted(intent_scores.items(), key=lambda x: x[1], reverse=True)
        best_intent, best_score = sorted_intents[0]
        second_score = sorted_intents[1][1] if len(sorted_intents) > 1 else 0.0
        confidence_margin = best_score - second_score
        is_uncertain = confidence_margin < CONFIDENCE_MARGIN_MIN

        log.debug(
            "Semantic router top scores",
            top1=f"{best_intent.value}={best_score:.4f}",
            top2=f"{sorted_intents[1][0].value}={second_score:.4f}" if len(sorted_intents) > 1 else "N/A",
            margin=round(confidence_margin, 4),
            uncertain=is_uncertain,
        )

        margin_threshold = max(self.threshold, best_score - 0.08)

        matched_intents = []
        msg_lower = user_message.lower()
        for intent, score in intent_scores.items():
            if score >= margin_threshold:
                # Extra strict validation for SYSTEM_ACTION to avoid false positives on general talk
                if intent == ChatIntent.SYSTEM_ACTION:
                    # Guard: require explicit action-intent markers to avoid false positives
                    # on general lore/factual questions that happen to have similar embeddings.
                    has_summarize_kw = any(kw in msg_lower for kw in [
                        "tóm tắt", "tổng hợp", "tổng kết", "summarize",
                        "nãy giờ", "những gì", "cuộc trò chuyện", "hội thoại",
                        "ghi lại", "liệt kê lại", "nhắc lại", "điểm chính",
                        "buổi chat", "session", "ký ức chung"
                    ])
                    has_emotion_kw = any(kw in msg_lower for kw in [
                        "cảm xúc", "báo cáo", "chỉ số", "bảng đo",
                        "tâm trạng", "nội tâm", "cảm giác", "trái tim",
                        "tình cảm", "xúc cảm", "tâm lý", "tâm tư"
                    ])
                    has_search_kw = any(kw in msg_lower for kw in [
                        "tra mạng", "lên mạng", "tra cứu", "search", "google",
                        "internet", "tìm kiếm trên", "tìm giúp", "tra giúp",
                        "tra xem", "tìm xem", "lên web", "check", "xem thử",
                        "kiểm tra xem", "tìm hiểu xem", "tìm thông tin",
                        "tìm kiếm", "tìm hiểu", "tìm kiếm thông tin", "tra thông tin",
                        "tìm về", "tìm kiếm về"
                    ])
                    has_keyword = has_summarize_kw or has_emotion_kw or has_search_kw

                    # Khi model đang phân vân (margin hẹp), keyword guard là bắt buộc.
                    # Khi model tự tin (margin rộng), chấp nhận nếu score đủ cao.
                    if is_uncertain:
                        if not has_keyword:
                            log.debug("SYSTEM_ACTION rejected: uncertain margin + no keyword", score=score, margin=confidence_margin)
                            continue
                    else:
                        if not (has_keyword or score >= 0.94):
                            log.debug("SYSTEM_ACTION rejected: no keyword and score below hard threshold", score=score)
                            continue

                matched_intents.append(intent)

        return matched_intents
