"""
Visual Memory Ingestion Worker for Kuchiba Chisa.
Location: app/domain/services/visual_memory_ingestion.py
"""

from __future__ import annotations
import re
import uuid
import time
from typing import List, Dict, Any, Optional
from qdrant_client.http.models import PointStruct

from app.domain.entities.image_memory import ImageMemoryPayload
from app.domain.interfaces.vector_store import IVectorStore
from app.domain.interfaces.embedding_provider import IEmbeddingProvider
from app.infrastructure.logging.logger import get_logger
from app.infrastructure.vector.qdrant.qdrant_service import COLLECTION_IMAGE_MEMORIES

log = get_logger(__name__)

# Common tag extractor dictionary
_TAG_PATTERNS = {
    "du lịch": ["du lịch", "đi chơi", "bãi biển", "biển", "phượt", "resort", "khách sạn", "núi", "cảnh đẹp", "hoàng hôn", "bình minh"],
    "thú cưng": ["mèo", "chó", "thú cưng", "pet", "meo", "dog", "cat", "cún", "miu", "hoàng thượng"],
    "game": ["wuthering waves", "genshin", "echo", "vũ khí", "weapon", "crit", "chỉ số", "stats", "build", "nhân vật", "dòng phụ", "tinh luyện"],
    "ẩm thực": ["món ăn", "ăn uống", "trà", "cà phê", "bánh", "nấu ăn", "quán ăn", "socola", "kem"],
    "học tập/code": ["code", "lập trình", "python", "lỗi", "error", "terminal", "ocr", "tài liệu", "sách", "bài tập"],
    "kỷ niệm": ["kỷ niệm", "chúng ta", "senpai", "chisa", "chụp chung", "lần đầu", "hôm nọ", "hồi trước"],
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
    ) -> None:
        self.vector_store = vector_store
        self.embedder = embedder

    async def ingest_image_memories(
        self,
        user_id: str,
        user_message: str,
        chisa_reply: str,
        processed_images: List[Dict[str, Any]],
        conversation_id: Optional[str] = None,
        guild_id: Optional[str] = None,
        channel_id: Optional[str] = None,
        is_ephemeral: bool = False,
    ) -> int:
        """
        Indexes all permanent processed images into Qdrant 'image_memories'.
        Returns number of successfully ingested image memories.
        """
        if is_ephemeral or not processed_images:
            return 0

        ingested_count = 0
        cleaned_user_msg = (user_message or "").strip()
        cleaned_chisa_reply = (chisa_reply or "").strip()

        # Extract semantic tags
        combined_text = f"{cleaned_user_msg} {cleaned_chisa_reply}".lower()
        extracted_tags: List[str] = []
        for tag_name, keywords in _TAG_PATTERNS.items():
            if any(kw in combined_text for kw in keywords):
                extracted_tags.append(tag_name)

        for img in processed_images:
            image_id = img.get("image_id")
            if not image_id or img.get("is_ephemeral"):
                continue

            # Build descriptive visual caption
            caption_parts = []
            if cleaned_user_msg:
                caption_parts.append(f"Bối cảnh người dùng: {cleaned_user_msg}")
            if cleaned_chisa_reply:
                # Take first 250 characters of Chisa's analytical response
                summary_reply = cleaned_chisa_reply[:250].replace("\n", " ")
                caption_parts.append(f"Mô tả và nhận xét của Chisa: {summary_reply}")

            visual_caption = " | ".join(caption_parts) if caption_parts else "Hình ảnh được lưu trữ trong kho ký ức."

            # Text to embed
            tags_str = ", ".join(extracted_tags) if extracted_tags else "hình ảnh, ký ức"
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
                    tags=extracted_tags,
                    user_context_hint=cleaned_user_msg[:200] if cleaned_user_msg else None,
                    chisa_comment_hint=cleaned_chisa_reply[:200] if cleaned_chisa_reply else None,
                    created_at=int(time.time()),
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
                        tags=extracted_tags,
                    )

            except Exception as ex:
                log.error("Failed to ingest image memory into Qdrant", image_id=image_id, error=str(ex))

        return ingested_count
