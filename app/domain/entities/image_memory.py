"""
Image Memory Entities & Payload for Kuchiba Chisa.
Location: app/domain/entities/image_memory.py
"""

from __future__ import annotations
import time
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field


class ImageMemoryPayload(BaseModel):
    """
    Strict typing for multimodal visual memory payload stored in Qdrant collection 'image_memories'.
    Enables Text-to-Image reverse search and retrieval for Chisa.
    """
    image_id: str
    user_id: str
    guild_id: Optional[str] = None
    channel_id: Optional[str] = None
    conversation_id: Optional[str] = None
    url: str                           # Web URL / Static path: e.g. "/static/uploads/2026/08/abc.webp"
    thumbnail_url: Optional[str] = None # 300px thumbnail URL for visualizer preview
    local_path: Optional[str] = None   # Server local path for Discord AttachmentBuilder
    visual_caption: str                # Detailed Vietnamese visual caption (60-120 words)
    tags: List[str] = Field(default_factory=list) # Visual tags: ["du lịch", "biển", "hoàng hôn", "kỷ niệm"]
    user_context_hint: Optional[str] = None       # What the user said when uploading the image
    chisa_comment_hint: Optional[str] = None      # Chisa's initial comment when receiving the image
    importance_score: float = Field(default=0.85, ge=0.0, le=1.0)
    created_at: int = Field(default_factory=lambda: int(time.time())) # Epoch seconds
    width: Optional[int] = None
    height: Optional[int] = None
    size_bytes: Optional[int] = None

    model_config = ConfigDict(extra="allow")


class RetrievedImageMemory(BaseModel):
    """
    Retrieved image memory returned by ImageMemoryRetriever.
    """
    image_id: str
    url: str
    thumbnail_url: Optional[str] = None
    local_path: Optional[str] = None
    visual_caption: str
    tags: List[str] = Field(default_factory=list)
    user_id: str
    guild_id: Optional[str] = None
    score: float
    created_at: int

    model_config = ConfigDict(extra="allow")
