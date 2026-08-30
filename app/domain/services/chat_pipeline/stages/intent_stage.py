from typing import Callable, Optional
from app.domain.services.chat_pipeline.stage import PipelineStage
from app.domain.services.chat_pipeline.context import ChatContext
from app.domain.models.intent_result import IntentResult, ChatIntent
from app.domain.services.intent_classifier import IntentClassifier
from app.domain.services.rag.query_rewriter import QueryRewriter
from app.domain.interfaces.embedding_provider import IEmbeddingProvider
from app.domain.interfaces.session import IDbSession
from app.domain.interfaces.repositories import IConversationRepository
from app.shared.utils.query_cleaner import clean_query_for_rag, is_meaningful_query
from app.shared.utils.logger import get_logger
from app.domain.interfaces.tracker import IPipelineTracker

log = get_logger(__name__)

VISION_GAMEPLAY_ANCHORS = {
    # Echo, trang bị, vũ khí & chỉ số
    "echo", "stats", "stat", "crit", "crit rate", "crit dmg", "chỉ số", "vũ khí", "weapon", "build",
    "nâng cấp", "trang bị", "dòng phụ", "dòng chính", "dòng ẩn", "dòng crit", "dòng stat", "dòng bạo", "substat", "mainstat", "tỷ lệ bạo",
    "sát thương bạo", "sát thương", "bạo kích", "tấn công", "phòng ngự", "kháng", "atk", "def", "hp",
    "nạp", "hiệu quả nạp", "energy recharge", "er", "tốc độ nạp", "chấn", "vũ khí trấn", "sonata",
    "set đồ", "set echo", "cost 1", "cost 3", "cost 4", "relic", "thánh di vật", "tuning", "tune",
    # Nhân vật, kỹ năng & gacha
    "cung mệnh", "chuỗi cộng hưởng", "resonance chain", "rc", "forte", "kỹ năng", "skill", "talent",
    "c0", "c1", "c2", "c3", "c4", "c5", "c6", "s1", "s2", "s3", "s4", "s5", "s6", "gacha", "roll",
    "lệch rate", "trúng rate", "bảo hiểm", "quay tướng", "pull", "khoe đồ", "khoe luck", "luck",
    # Thẩm định & Đánh giá
    "ngon không", "ngon ko", "ổn không", "ổn ko", "dùng được không", "dùng đc ko", "chọn cái nào",
    "so sánh", "chấm điểm", "tạ không", "phế không", "đạt chuẩn chưa", "chuẩn chưa", "la hoàn",
    "tháp", "tower", "toa độ", "toa", "hologram", "boss", "dps", "support", "healer", "sub dps"
}

VISION_MEME_ANCHORS = {
    # Hài hước, ảnh chế, troll & internet slang
    "meme", "hài", "ảnh chế", "buồn cười", "vui", "troll", "bựa", "dìm", "chúa hề", "tấu hề",
    "tấu hài", "cười", "cười ỉa", "cười vcl", "cười vãi", "lmao", "kekw", "bruh", "dảk", "dark meme",
    "shitpost", "cà khịa", "khịa", "gắt", "ảo thật", "độc lạ", "bất ổn", "wibu", "hội chứng", "ảo ma",
    "vô tri", "ngáo", "ngố", "chế ảnh", "mặn", "hài hước", "cười đau bụng", "hề hước", "cười bò", "tấu"
}

VISION_CODE_ANCHORS = {
    # Lập trình & Debug lỗi
    "code", "lỗi", "error", "bug", "log", "traceback", "exception", "terminal", "console", "cmd",
    "powershell", "đoạn mã", "hàm", "function", "class", "script", "debug", "sửa lỗi", "chạy không được",
    "không chạy", "syntax", "runtime", "compile", "build fail", "ide", "vscode", "stack trace", "output"
}

VISION_DOCUMENT_OCR_ANCHORS = {
    # Đọc văn bản, hóa đơn, dịch thuật & OCR
    "dịch", "translate", "chữ gì", "đọc hộ", "đọc giúp", "tài liệu", "hóa đơn", "bill", "văn bản",
    "chữ này", "nghĩa là gì", "đoạn văn", "bài tập", "đề bài", "chữ viết tay", "tiếng nhật", "tiếng trung",
    "tiếng anh", "kanji", "chữ hán", "hán tự", "biển báo", "bảng hiệu", "biên lai", "chứng từ"
}

VISION_ARTWORK_ANCHORS = {
    # Tranh vẽ, Fanart, Cosplay & Phong cách
    "art", "fanart", "cosplay", "ảnh vẽ", "tranh", "avatar", "avt", "vẽ", "sketch", "minh họa",
    "illustration", "waifu", "husbando", "tạo hình", "trang phục", "outfit", "nét vẽ", "style",
    "phối màu", "đẹp không", "xinh không", "dễ thương không", "kawaii", "bức tranh", "tranh vẽ"
}


class IntentStage(PipelineStage):
    """
    Stage 2: Classify intent, perform Tiered Query Rewrite (Fast-Path / Micro LLM Rewrite),
    and embed the final aligned query vector for RAG.
    """
    def __init__(
        self,
        intent_classifier: IntentClassifier,
        embedder: IEmbeddingProvider,
        query_rewriter: Optional[QueryRewriter] = None,
        conv_repo_factory: Optional[Callable[[IDbSession], IConversationRepository]] = None,
        pipeline_tracker: Optional[IPipelineTracker] = None,
    ):
        self.intent_classifier = intent_classifier
        self.embedder = embedder
        self.query_rewriter = query_rewriter
        self.conv_repo_factory = conv_repo_factory
        self.pipeline_tracker = pipeline_tracker

    async def process(self, context: ChatContext) -> ChatContext:
        if context.has_images:
            is_st = False
            st_reason = "Multimodal Vision Input Active (Bypass Small Talk Fast Path)"
        else:
            is_st, st_reason = await self.intent_classifier.is_small_talk_hybrid(context.user_message)
        
        query_vector = None
        cleaned_query = ""
        rewritten_query = context.user_message
        rewrite_method = "BYPASS"
        needs_vector_search = False
        needs_web_search = False
        intent_result: Optional[IntentResult] = None

        if not is_st and not context.has_images:
            cleaned_query = clean_query_for_rag(context.user_message)
            if not is_meaningful_query(cleaned_query):
                log.info("Intent post-clean guard: query cleaned down to non-meaningful content -> Small Talk", original=context.user_message, cleaned=cleaned_query)
                is_st = True
                st_reason = "Non-meaningful query guard (Bypass RAG)"
                cleaned_query = ""

        # ── BRANCH 1: Small Talk (0ms Latency, 0 Token LLM Rewrite Bypass) ──
        if is_st:
            intent_result = IntentResult(
                intents=[ChatIntent.SMALL_TALK],
                confidence=1.0,
                routing_method="HYBRID_SMALL_TALK",
                query_vector=None,
                semantic_scores={"SMALL_TALK": 1.0},
                routing_reason=f"Hardcore Hybrid Small Talk: {st_reason}"
            )
            context.is_small_talk = True
            rewritten_query = context.user_message
            rewrite_method = "BYPASS"
            needs_vector_search = False
            needs_web_search = False

            # Optionally embed text for long-term memory retrieval
            try:
                query_vector = await self.embedder.embed_text(context.user_message, prefix="query: ")
                intent_result.query_vector = query_vector
            except Exception as ex:
                log.debug("Small talk memory embedding skipped", error=str(ex))

            # Detect Chisa Persona Trait (Personality vs Profile vs None)
            persona_trait = await self.intent_classifier.detect_persona_trait(context.user_message, query_vector=query_vector)
            context.persona_trait_type = persona_trait

            if self.pipeline_tracker:
                self.pipeline_tracker.add_step("intent_classification", {
                    "user_message": context.user_message,
                    "is_small_talk": True,
                    "intents": ["SMALL_TALK"],
                    "rewritten_query": context.user_message,
                    "rewrite_method": "BYPASS",
                    "needs_vector_search": False,
                    "needs_web_search": False,
                    "confidence": 1.0,
                    "routing_method": "HYBRID_SMALL_TALK",
                    "semantic_scores": {"SMALL_TALK": 1.0},
                    "persona_trait_type": persona_trait,
                    "rag_triggered": False,
                    "routing_reason": f"Hardcore Hybrid Small Talk: {st_reason}"
                })

        # ── BRANCH 2: Knowledge / Task / Out-of-Lore / Code (LLM Rewriter & Tri-State Router) ──
        else:
            context.is_small_talk = False

            # Register Stage 2 root step FIRST so sub-action LLM rewrite appears hierarchically as its child node
            stage_tracker_data = {
                "user_message": context.user_message,
                "is_small_talk": False,
                "intents": ["KNOWLEDGE_OR_TASK"],
                "rewritten_query": context.user_message,
                "rewrite_method": "LLM_FLASH",
                "needs_vector_search": False,
                "needs_web_search": False,
                "rag_triggered": False,
                "confidence": 1.0,
                "routing_method": "LLM_ROUTER",
                "routing_reason": "Knowledge / Task Query ➔ Handover to Micro LLM Rewriter"
            }
            if self.pipeline_tracker:
                self.pipeline_tracker.add_step("intent_classification", stage_tracker_data)

            # 1. Retrieve previous user rewritten query from SQL (1-Turn Context Chaining)
            prev_rewritten_query = None
            if self.conv_repo_factory and context.session and context.conv_id and context.user_uuid:
                try:
                    conv_repo = self.conv_repo_factory(context.session)
                    prev_rewritten_query = await conv_repo.get_last_user_rewritten_query(
                        user_id=context.user_uuid,
                        conversation_id=context.conv_id
                    )
                except Exception as e:
                    log.warning("Failed to fetch last rewritten query from SQL", error=str(e))

            # Fallback to history if SQL didn't have it
            if not prev_rewritten_query and context.history:
                user_hist = [h["content"] for h in context.history if h.get("role") == "user"]
                if user_hist:
                    prev_rewritten_query = user_hist[-1]

            # 2. Execute Micro LLM Rewrite & Tri-State Routing (Sub-step LLM is recorded after root step)
            if self.query_rewriter:
                rewritten_query, rewrite_method, needs_vector_search, needs_web_search = await self.query_rewriter.rewrite(
                    user_message=context.user_message,
                    cleaned_query=cleaned_query,
                    prev_rewritten_query=prev_rewritten_query,
                    needs_llm_rewrite=True,
                    intent_hint=None,
                )
            else:
                rewritten_query = cleaned_query or context.user_message
                rewrite_method = "FAST_PATH"
                needs_vector_search = True
                needs_web_search = False

            # 3. Determine intents based on LLM Router decisions & Multimodal Vision Anchors
            matched_intents: List[ChatIntent] = []
            if context.has_images:
                msg_lower = (context.user_message or "").lower()

                if any(kw in msg_lower for kw in VISION_GAMEPLAY_ANCHORS):
                    matched_intents.append(ChatIntent.GAMEPLAY_STATS_EVALUATION)
                    matched_intents.append(ChatIntent.LORE)
                    needs_vector_search = True
                elif any(kw in msg_lower for kw in VISION_MEME_ANCHORS):
                    matched_intents.append(ChatIntent.MEME_REACTION)
                elif any(kw in msg_lower for kw in VISION_CODE_ANCHORS):
                    matched_intents.append(ChatIntent.CODE_ANALYSIS)
                    matched_intents.append(ChatIntent.KNOWLEDGE_OR_TASK)
                elif any(kw in msg_lower for kw in VISION_DOCUMENT_OCR_ANCHORS):
                    matched_intents.append(ChatIntent.DOCUMENT_OCR)
                    matched_intents.append(ChatIntent.KNOWLEDGE_OR_TASK)
                elif any(kw in msg_lower for kw in VISION_ARTWORK_ANCHORS):
                    matched_intents.append(ChatIntent.ARTWORK_EVALUATION)
                    matched_intents.append(ChatIntent.CONVERSATIONAL)
                else:
                    matched_intents.append(ChatIntent.IMAGE_ANALYSIS)
                    matched_intents.append(ChatIntent.CONVERSATIONAL)
                
                routing_reason = f"Multimodal Vision Router: {[i.value for i in matched_intents]}"
            else:
                if needs_vector_search:
                    matched_intents.append(ChatIntent.LORE)
                    matched_intents.append(ChatIntent.KNOWLEDGE_OR_TASK)
                elif needs_web_search:
                    matched_intents.append(ChatIntent.KNOWLEDGE_OR_TASK)
                else:
                    matched_intents.append(ChatIntent.CONVERSATIONAL)

                if needs_vector_search and needs_web_search:
                    routing_reason = "LLM Tri-State: Hybrid Search (Vector Lore + Direct Web Search)"
                elif needs_vector_search:
                    routing_reason = "LLM Tri-State: Qdrant Vector Search (Game Lore)"
                elif needs_web_search:
                    routing_reason = "LLM Tri-State: Direct Web Search (External / Internet)"
                else:
                    routing_reason = "LLM Tri-State: Code / Small Talk (0ms RAG Bypass)"

            intent_result = IntentResult(
                intents=matched_intents,
                confidence=1.0,
                routing_method="LLM_ROUTER",
                query_vector=query_vector,
                semantic_scores={"LORE": 1.0 if needs_vector_search else 0.0, "WEB": 1.0 if needs_web_search else 0.0},
                routing_reason=routing_reason
            )

            intent_values = [i.value for i in intent_result.intents]
            rag_triggered = bool(needs_vector_search or needs_web_search)

            # Detect Chisa Persona Trait (Personality vs Profile vs None)
            persona_trait = await self.intent_classifier.detect_persona_trait(context.user_message, query_vector=query_vector)
            context.persona_trait_type = persona_trait

            # 5. Update Stage 2 tracker step data with finalized rewrite & routing outcomes
            stage_tracker_data.update({
                "intents": intent_values,
                "rewritten_query": rewritten_query,
                "rewrite_method": rewrite_method,
                "needs_vector_search": needs_vector_search,
                "needs_web_search": needs_web_search,
                "rag_triggered": rag_triggered,
                "persona_trait_type": persona_trait,
                "routing_reason": routing_reason
            })

        log.info(
            "Production query classified and routed",
            intents=[i.value for i in intent_result.intents],
            confidence=intent_result.confidence,
            method=intent_result.routing_method,
            rewrite_method=rewrite_method,
            rewritten_query=rewritten_query,
            needs_vector_search=needs_vector_search,
            needs_web_search=needs_web_search,
            user_id=context.user_id
        )

        context.intent_result = intent_result
        context.cleaned_query = cleaned_query
        context.rewritten_query = rewritten_query
        context.rewrite_method = rewrite_method
        context.needs_vector_search = needs_vector_search
        context.needs_web_search = needs_web_search
        context.query_vector = query_vector
        context.intents = intent_result.intents

        return context
