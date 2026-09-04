"""
Visual Memory Ingestion Worker for Kuchiba Chisa.
Location: app/domain/services/visual_memory_ingestion.py
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from qdrant_client.http.models import PointStruct

from app.domain.entities.image_memory import ImageMemoryPayload
from app.domain.interfaces.embedding_provider import IEmbeddingProvider
from app.domain.interfaces.vector_store import IVectorStore
from app.domain.services.guardrails import ContentSource, GuardAction, InjectionGuard
from app.domain.services.guardrails.pii_redaction import PiiRedactor
from app.infrastructure.logging.logger import get_logger
from app.infrastructure.vector.qdrant.qdrant_service import COLLECTION_IMAGE_MEMORIES

log = get_logger(__name__)

# Common tag extractor dictionary
_TAG_PATTERNS = {
    "du lịch": [
        "du lịch",
        "đi chơi",
        "bãi biển",
        "biển",
        "phượt",
        "resort",
        "khách sạn",
        "núi",
        "cảnh đẹp",
        "hoàng hôn",
        "bình minh",
    ],
    "thú cưng": [
        "mèo",
        "chó",
        "thú cưng",
        "pet",
        "meo",
        "dog",
        "cat",
        "cún",
        "miu",
        "hoàng thượng",
    ],
    "game": [
        "wuthering waves",
        "genshin",
        "echo",
        "vũ khí",
        "weapon",
        "crit",
        "chỉ số",
        "stats",
        "build",
        "nhân vật",
        "dòng phụ",
        "tinh luyện",
    ],
    "ẩm thực": ["món ăn", "ăn uống", "trà", "cà phê", "bánh", "nấu ăn", "quán ăn", "socola", "kem"],
    "học tập/code": [
        "code",
        "lập trình",
        "python",
        "lỗi",
        "error",
        "terminal",
        "ocr",
        "tài liệu",
        "sách",
        "bài tập",
    ],
    "kỷ niệm": [
        "kỷ niệm",
        "chúng ta",
        "senpai",
        "chisa",
        "chụp chung",
        "lần đầu",
        "hôm nọ",
        "hồi trước",
    ],
    "meme": ["meme", "hài", "bựa", "vui", "ảnh chế", "troll"],
}


class VisualMemoryIngestionWorker:
    """
    Background worker that extracts visual captions & tags from multimodal interactions
    and vector-indexes them into Qdrant collection 'image_memories'.
    """

    def __init__(
        self,
        vector_store: IVectorStore,
        embedder: IEmbeddingProvider,
        injection_guard: InjectionGuard | None = None,
        pii_redactor: PiiRedactor | None = None,
    ) -> None:
        self.vector_store = vector_store
        self.embedder = embedder
        self.injection_guard = injection_guard or InjectionGuard()
        self.pii_redactor = pii_redactor or PiiRedactor()

    async def ingest_image_memories(
        self,
        user_id: str,
        user_message: str,
        chisa_reply: str,
        processed_images: list[dict[str, Any]],
        conversation_id: str | None = None,
        guild_id: str | None = None,
        channel_id: str | None = None,
        is_ephemeral: bool = False,
        llm_image_tags: list[str] | None = None,
        llm_visual_caption: str | None = None,
        retention_expires_at: int | None = None,
    ) -> int:
        """
        Indexes all permanent processed images into Qdrant 'image_memories'.
        Prioritizes tags and visual captions generated directly by the Vision LLM (0ms latency).
        Returns number of successfully ingested image memories.
        """
        if is_ephemeral or not processed_images:
            return 0

        ingested_count = 0
        cleaned_user_msg = self.pii_redactor.redact((user_message or "").strip()).value
        cleaned_chisa_reply = self.pii_redactor.redact((chisa_reply or "").strip()).value

        # Extract semantic tags: prioritize LLM tags and combine with heuristic fallback
        combined_text = f"{cleaned_user_msg} {cleaned_chisa_reply}".lower()
        fallback_tags: list[str] = []
        for tag_name, keywords in _TAG_PATTERNS.items():
            if any(kw in combined_text for kw in keywords):
                fallback_tags.append(tag_name)

        final_tags: list[str] = []
        if llm_image_tags:
            for t in llm_image_tags:
                clean_t = str(t).strip().lower()
                if clean_t and clean_t not in final_tags:
                    final_tags.append(clean_t)
        for t in fallback_tags:
            if t not in final_tags:
                final_tags.append(t)

        for img in processed_images:
            image_id = img.get("image_id")
            if not image_id or img.get("is_ephemeral"):
                continue

            # Build descriptive visual caption: prioritize LLM caption
            if llm_visual_caption and llm_visual_caption.strip():
                visual_caption = self.pii_redactor.redact(llm_visual_caption.strip()).value
            else:
                caption_parts = []
                if cleaned_user_msg:
                    caption_parts.append(f"Bối cảnh người dùng: {cleaned_user_msg}")
                if cleaned_chisa_reply:
                    # Take first 250 characters of Chisa's analytical response
                    summary_reply = cleaned_chisa_reply[:250].replace("\n", " ")
                    caption_parts.append(f"Mô tả và nhận xét của Chisa: {summary_reply}")
                visual_caption = (
                    " | ".join(caption_parts)
                    if caption_parts
                    else "Hình ảnh được lưu trữ trong kho ký ức."
                )

            # Vision captions and tags originate from image-derived, untrusted content.
            # Do not embed or persist a visual prompt-injection payload for future retrieval.
            image_derived_text = "\n".join([visual_caption, *final_tags])
            assessment = self.injection_guard.assess(
                image_derived_text, ContentSource.IMAGE_DERIVED
            )
            if assessment.action is GuardAction.QUARANTINE:
                log.warning(
                    "Image-derived metadata quarantined before visual-memory indexing",
                    image_id=str(image_id),
                    rule_id=assessment.rule_id,
                    fingerprint=assessment.fingerprint,
                )
                continue

            # Text to embed
            tags_str = ", ".join(final_tags) if final_tags else "hình ảnh, ký ức"
            text_to_embed = f"{visual_caption} | Tags: {tags_str} | Bối cảnh: {cleaned_user_msg}"

            try:
                # Vectorize text using multilingual-e5-small with 'passage: ' prefix
                vector = await self.embedder.embed_text(text_to_embed, prefix="passage: ")
                if not vector:
                    continue

                # Prepare payload
                payload = ImageMemoryPayload(
                    image_id=str(image_id),
                    user_id=str(user_id),
                    guild_id=str(guild_id) if guild_id else None,
                    channel_id=str(channel_id) if channel_id else None,
                    conversation_id=str(conversation_id) if conversation_id else None,
                    url=img.get("url") or "",
                    thumbnail_url=img.get("thumbnail_url"),
                    local_path=img.get("local_path"),
                    visual_caption=visual_caption,
                    tags=final_tags,
                    user_context_hint=cleaned_user_msg[:200] if cleaned_user_msg else None,
                    chisa_comment_hint=cleaned_chisa_reply[:200] if cleaned_chisa_reply else None,
                    created_at=int(time.time()),
                    expires_at=retention_expires_at,
                    width=img.get("width"),
                    height=img.get("height"),
                    size_bytes=img.get("size_bytes"),
                )

                # Deterministic UUID for Qdrant point
                point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"chisa_img_{image_id}"))

                # Upsert into Qdrant
                qdrant_client = getattr(self.vector_store, "_client", None)
                if qdrant_client:
                    await qdrant_client.upsert(
                        collection_name=COLLECTION_IMAGE_MEMORIES,
                        points=[
                            PointStruct(
                                id=point_id,
                                vector=vector,
                                payload=payload.model_dump(),
                            )
                        ],
                        wait=False,
                    )
                    ingested_count += 1
                    log.info(
                        "Ingested image memory into Qdrant",
                        image_id=image_id,
                        user_id=user_id,
                        tags=final_tags,
                    )

            except Exception as ex:
                log.error(
                    "Failed to ingest image memory into Qdrant", image_id=image_id, error=str(ex)
                )

        return ingested_count
