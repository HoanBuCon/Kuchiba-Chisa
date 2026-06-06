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

import os
os.environ["HF_HUB_DISABLE_SYMLINKS"] = "1"
import asyncio
import sys
import uuid

import re

# Reconfigure stdout to use UTF-8 on Windows
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

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

    # Sections to ignore in RAG (since they are static guidelines already in the system prompt rules)
    EXCLUDED_SECTIONS = {
        "Tính Cách Lý Trí (Canon)",
        "Nội Tâm và Quan Điểm Về Con Người",
        "Con Người Chisa (Persona đối với Senpai)",
        "Phong Cách Nói Chuyện",
        "Câu Thường Nói (Quotes)"
    }

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
        if section_name in EXCLUDED_SECTIONS:
            print(f"[*] Skipping persona/style section for RAG ingestion: '{section_name}'")
            continue
            
        section_body = lines[1].strip()
        
        # Split body by list items (-)
        raw_lines = [l.strip() for l in section_body.split("\n") if l.strip()]
        
        for line in raw_lines:
            if line.startswith("-"):
                content = line[1:].strip() # Remove the dash
                if content:
                    chunks.append((section_name, f"[{section_name}] {content}"))
            else:
                chunks.append((section_name, f"[{section_name}] {line}"))

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
