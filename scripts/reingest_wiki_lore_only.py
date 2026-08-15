"""
================================================================================
RE-INGEST WIKI LORE ONLY (PURGE ALL LEGACY & MANUAL LORE FROM VECTOR DB)
================================================================================
1. Deletes old manual/legacy lore collections in Qdrant (without touching `memories`).
2. Creates fresh collections: character_lore, world_lore, story_lore.
3. Ingests all 2,010 clean Wiki chunks from data/chunks/chunks.jsonl using FastEmbed.
4. Syncs parent sections from data/canonical/canonical.jsonl to PostgreSQL lore_parents.
5. Syncs entity dictionary from chunks to data/entity_dict.json.
================================================================================
"""

import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import asyncio
import json
import time
import uuid
from pathlib import Path
from typing import List, Dict, Any

from qdrant_client.http import models as qdrant_models
from qdrant_client.http.models import PayloadSchemaType

from app.config.settings import settings
from app.infrastructure.vector.qdrant.qdrant_service import (
    qdrant_service,
    get_qdrant_client,
    COLLECTION_CHARACTER_LORE,
    COLLECTION_WORLD_LORE,
    COLLECTION_STORY_LORE,
)
from app.infrastructure.embeddings.fastembed_adapter import FastEmbedAdapter
from app.infrastructure.ingestion.models.chunk_model import Chunk
from app.infrastructure.ingestion.storage.qdrant_sync import map_page_type_to_collection
from app.domain.services.rag.entity_sync import sync_entities_dictionary
from scripts.sync_parents_to_db import sync_parents


async def purge_and_recreate_lore_collections():
    print("\n" + "=" * 80)
    print("🧹 BƯỚC 1: XÓA SẠCH LORE CŨ & TẠO LẠI COLLECTIONS MỚI TRONG QDRANT")
    print("=" * 80)

    client = get_qdrant_client()
    collections_to_wipe = [
        COLLECTION_CHARACTER_LORE,
        COLLECTION_WORLD_LORE,
        COLLECTION_STORY_LORE,
        "lore",
        "chisa_lore",
        "user_facts",
        "persona_embeddings",
        "conversation_summaries",
        "emotional_memories",
    ]

    for col in collections_to_wipe:
        try:
            if await qdrant_service.collection_exists(col):
                await client.delete_collection(col)
                print(f"  ✓ Đã xóa collection cũ: {col}")
        except Exception as e:
            print(f"  ⚠️ Không thể xóa {col}: {e}")

    # Preserving `memories` collection (Do not touch user memories!)
    print("  🔒 Collection 'memories' (User Long-Term Memory) ĐƯỢC BẢO TOÀN NGUYÊN VẸN.")

    dim = settings.QDRANT_EMBEDDING_DIM  # 384 for multilingual-e5-small
    target_lore_cols = [COLLECTION_CHARACTER_LORE, COLLECTION_WORLD_LORE, COLLECTION_STORY_LORE]

    for col in target_lore_cols:
        await qdrant_service.create_collection(col, vector_size=dim)
        print(f"  ✓ Đã tạo mới collection: {col} (Vector dim: {dim})")

    # Create keyword indexes
    for col in target_lore_cols:
        for field in ["entities", "region", "faction", "canonical_name", "page_id", "section_id"]:
            try:
                await client.create_payload_index(
                    collection_name=col,
                    field_name=field,
                    field_schema=PayloadSchemaType.KEYWORD,
                    wait=True
                )
            except Exception:
                pass
        print(f"  ✓ Đã tạo index tìm kiếm entity/metadata cho: {col}")


async def ingest_wiki_chunks():
    print("\n" + "=" * 80)
    print("📥 BƯỚC 2: EMBEDDING & UPSERT TOÀN BỘ 2,010 CHUNKS TỪ WIKI VÀO QDRANT")
    print("=" * 80)

    chunks_file = Path("data/chunks/chunks.jsonl")
    if not chunks_file.exists():
        print(f"[!] Không tìm thấy file: {chunks_file}", file=sys.stderr)
        sys.exit(1)

    chunks: List[Chunk] = []
    with open(chunks_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                chunks.append(Chunk.model_validate_json(line.strip()))

    print(f"[*] Đã đọc thành công {len(chunks)} chunks từ {chunks_file}")

    embedder = FastEmbedAdapter()
    print("  [OK] Initialized FastEmbed Adapter (intfloat/multilingual-e5-small)")

    # Prepare texts with context_prefix
    texts = [f"{c.context_prefix}\n{c.text_content}" for c in chunks]

    cache_path = Path("data/chunks/embeddings_cache_384.json")
    if cache_path.exists():
        print(f"[*] Đang nạp vectors từ cache: {cache_path}...")
        with open(cache_path, "r", encoding="utf-8") as cf:
            vectors = json.load(cf)
        print(f"  ✓ Đã nạp {len(vectors)} vectors từ cache tức thì (0.1s)")
    else:
        print(f"[*] Đang thực hiện Embedding cho {len(texts)} chunks...")
        t0 = time.time()
        vectors = await embedder.embed_batch(texts, prefix="passage: ")
        embed_duration = time.time() - t0
        print(f"  ✓ Hoàn thành Embedding trong {embed_duration:.2f}s (Tốc độ: {len(texts)/embed_duration:.1f} chunks/s)")
        try:
            with open(cache_path, "w", encoding="utf-8") as cf:
                json.dump(vectors, cf)
            print(f"  ✓ Đã lưu cache vectors vào: {cache_path}")
        except Exception:
            pass

    # Group points by target collection
    collection_points: Dict[str, List[qdrant_models.PointStruct]] = {
        COLLECTION_CHARACTER_LORE: [],
        COLLECTION_WORLD_LORE: [],
        COLLECTION_STORY_LORE: [],
    }

    for chunk, vector in zip(chunks, vectors):
        pt_val = chunk.page_type.value if hasattr(chunk.page_type, "value") else str(chunk.page_type)
        strat_val = chunk.chunk_strategy.value if hasattr(chunk.chunk_strategy, "value") else str(getattr(chunk, "chunk_strategy", "GENERIC"))
        target_col = map_page_type_to_collection(pt_val)
        point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"chunk:{chunk.chunk_id}"))

        payload = {
            "chunk_id": str(chunk.chunk_id),
            "page_id": chunk.page_id,
            "page_title": chunk.page_title,
            "canonical_slug": chunk.page_title.lower().replace(" ", "_"),
            "canonical_name": chunk.page_title,
            "page_type": pt_val,
            "section_id": chunk.section_id,
            "section_title": chunk.section_title,
            "heading_path": chunk.heading_path,
            "strategy": strat_val,
            "text_content": chunk.text_content,
            "context_prefix": getattr(chunk, "context_prefix", ""),
            "entities": getattr(chunk, "entities", []),
            "token_count": getattr(chunk, "token_count_approx", 0),
            "source_type": "wiki",
            "parent_id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"parent:{chunk.section_id}")),
        }

        struct = qdrant_models.PointStruct(
            id=point_id,
            vector=vector,
            payload=payload
        )
        collection_points[target_col].append(struct)

    client = get_qdrant_client()
    for col_name, points in collection_points.items():
        print(f"[*] Đang nạp {len(points)} points vào {col_name}...")
        batch_size = 150
        for i in range(0, len(points), batch_size):
            batch = points[i : i + batch_size]
            await client.upsert(collection_name=col_name, points=batch, wait=True)
        print(f"  ✓ Hoàn tất nạp {len(points)} points vào {col_name}")


async def sync_postgres_parents():
    print("\n" + "=" * 80)
    print("📚 BƯỚC 3: ĐỒNG BỘ PARENT SECTIONS TỪ WIKI VÀO POSTGRESQL (lore_parents)")
    print("=" * 80)
    await sync_parents()


def sync_wiki_entities():
    print("\n" + "=" * 80)
    print("🏷️ BƯỚC 4: ĐỒNG BỘ TỪ ĐIỂN THỰC THỂ & ALIASES TỪ WIKI CHUNKS")
    print("=" * 80)
    entities = sync_entities_dictionary(chunks_path="data/chunks/chunks.jsonl", output_file="data/lore/entities.json")
    print(f"  ✓ Đã cập nhật file data/lore/entities.json với {len(entities)} thực thể từ 2,010 chunks Wiki")


async def verify_qdrant_status():
    print("\n" + "=" * 80)
    print("🔍 BƯỚC 5: KIỂM TRA TỔNG KẾT DỮ LIỆU TRONG VECTOR DB (QDRANT)")
    print("=" * 80)

    client = get_qdrant_client()
    cols = await client.get_collections()
    for c in cols.collections:
        count = await client.count(c.name)
        print(f"  📦 Collection: {c.name:22} | Số lượng Points: {count.count}")


async def main():
    print("🚀 BẮT ĐẦU QUY TRÌNH RE-INGEST LORE CHỈ TỪ WUTHERING WAVES WIKI...")
    t_start = time.time()

    await purge_and_recreate_lore_collections()
    await ingest_wiki_chunks()
    await sync_postgres_parents()
    sync_wiki_entities()
    await verify_qdrant_status()

    total_time = time.time() - t_start
    print("\n" + "=" * 80)
    print(f"🎉 RE-INGEST WIKI LORE HOÀN TẤT 100% TRONG {total_time:.2f} GIÂY!")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
