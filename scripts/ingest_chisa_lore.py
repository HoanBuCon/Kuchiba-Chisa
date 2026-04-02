"""
Chisa Lore Ingestion Script
============================
Reads assets/chisa_lore.txt, chunks it by section (===== delimiter),
embeds each chunk with FastEmbed, and upserts into Qdrant `chisa_lore` collection.

Run once (or re-run to refresh lore):
    cd <project_root>
    .\venv\Scripts\activate
    python scripts/ingest_chisa_lore.py
"""

import asyncio
import sys
import os
import uuid
import re

sys.path.append(os.getcwd())

from app.infrastructure.vector.qdrant.qdrant_service import qdrant_service, get_qdrant_client
from app.infrastructure.embeddings.fastembed_adapter import FastEmbedAdapter
from qdrant_client.http import models as qdrant_models


LORE_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "lore", "chisa_lore.md")
COLLECTION = "chisa_lore"
VECTOR_SIZE = 384  # all-MiniLM-L6-v2


async def ensure_collection():
    """Create chisa_lore collection, dropping the old one if it exists to ensure clean state."""
    client = get_qdrant_client()
    collections = await client.get_collections()
    names = [c.name for c in collections.collections]
    
    if COLLECTION in names:
        await client.delete_collection(collection_name=COLLECTION)
        print(f"[*] Deleted existing collection to refresh lore: {COLLECTION}")

    await client.create_collection(
        collection_name=COLLECTION,
        vectors_config=qdrant_models.VectorParams(
            size=VECTOR_SIZE,
            distance=qdrant_models.Distance.COSINE,
        ),
    )
    print(f"[+] Created collection: {COLLECTION}")


def parse_lore_chunks(filepath: str) -> list[tuple[str, str]]:
    with open(filepath, "r", encoding="utf-8") as f:
        raw = f.read()

    # Find all sections starting with ##
    # Regex splits by "## " but keeps the content.
    import re
    sections = re.split(r'\n## ', '\n' + raw)
    
    chunks = []
    for section in sections:
        section = section.strip()
        if not section or section.startswith("# Chisa"):
            continue
            
        lines = section.split("\n", 1)
        if len(lines) < 2:
            continue
            
        section_name = lines[0].strip()
        section_body = lines[1].strip()
        
        # Split body by lists (-) or empty paragraphs
        paragraphs = [p.strip() for p in section_body.split("\n") if p.strip()]
        
        current_chunk = []
        current_len = 0
        
        for para in paragraphs:
            if current_len + len(para) > 1000 and current_chunk:
                combined_text = " ".join(current_chunk)
                chunks.append((section_name, f"[{section_name}] {combined_text}"))
                current_chunk = [para]
                current_len = len(para)
            else:
                current_chunk.append(para)
                current_len += len(para)
                
        if current_chunk:
            combined_text = " ".join(current_chunk)
            chunks.append((section_name, f"[{section_name}] {combined_text}"))

    return chunks


async def main():
    print("=" * 50)
    print(" CHISA LORE INGESTION")
    print("=" * 50)

    # 1. Ensure collection
    await ensure_collection()

    # 2. Parse lore file
    chunks = parse_lore_chunks(LORE_FILE)
    print(f"[i] Parsed {len(chunks)} lore chunks from {LORE_FILE}")

    # 3. Embed and upsert
    embedder = FastEmbedAdapter()
    success = 0
    for section, text in chunks:
        try:
            vector = await embedder.embed_text(text)
            point_id = str(uuid.uuid4())
            await qdrant_service.upsert_lore(
                collection=COLLECTION,
                point_id=point_id,
                vector=vector,
                text_content=text,
                section=section,
            )
            print(f"  [+] [{section}] {text[:60]}...")
            success += 1
        except Exception as e:
            print(f"  [!] Failed chunk [{section}]: {e}")

    print(f"\n[DONE] {success}/{len(chunks)} lore chunks ingested into `{COLLECTION}`.")
    print("Chisa is now self-aware. Handle with care.\n")


if __name__ == "__main__":
    asyncio.run(main())
