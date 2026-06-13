import os
os.environ["HF_HUB_DISABLE_SYMLINKS"] = "1"
import asyncio
import sys
import uuid
import re

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

sys.path.append(os.getcwd())

from app.infrastructure.vector.qdrant.qdrant_service import qdrant_service, get_qdrant_client
from app.infrastructure.embeddings.fastembed_adapter import FastEmbedAdapter
from qdrant_client.http import models as qdrant_models

VECTOR_SIZE = 384

COLLECTIONS = {
    "character_lore": "data/lore/character_lore.md",
    "world_lore": "data/lore/world_lore.md",
    "story_lore": "data/lore/story_lore.md",
}

def _parse_bullets(section_body: str) -> list[str]:
    bullets: list[str] = []
    for line in section_body.split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("##"):
            continue
        if stripped.startswith("-"):
            content = stripped[1:].strip()
            if content:
                bullets.append(content)
        else:
            bullets.append(stripped)
    return bullets

def parse_lore_chunks(filepath: str) -> list[tuple[str, str]]:
    if not os.path.exists(filepath):
        print(f"[!] File not found: {filepath}")
        return []
        
    with open(filepath, "r", encoding="utf-8") as f:
        raw = f.read()

    sections = re.split(r'\n## ', '\n' + raw)
    chunks = []
    
    for section in sections:
        section = section.strip()
        if not section or section.startswith("#"):
            continue
            
        lines = section.split("\n", 1)
        if len(lines) < 2:
            continue
            
        section_name = lines[0].strip()
        section_body = lines[1].strip()
        bullets = _parse_bullets(section_body)
        
        # We can chunk by bullet points
        for bullet in bullets:
            if bullet.strip():
                chunks.append((section_name, f"[{section_name}] {bullet.strip()}"))
                
    return chunks

async def ensure_collections():
    client = get_qdrant_client()
    collections = await client.get_collections()
    names = [c.name for c in collections.collections]
    
    for col_name in COLLECTIONS.keys():
        if col_name in names:
            await client.delete_collection(collection_name=col_name)
            print(f"[*] Deleted existing collection: {col_name}")
            
        await client.create_collection(
            collection_name=col_name,
            vectors_config=qdrant_models.VectorParams(
                size=VECTOR_SIZE,
                distance=qdrant_models.Distance.COSINE,
            ),
        )
        print(f"[+] Created collection: {col_name}")

async def main():
    print("=" * 60)
    print(" INGESTING PRODUCTION PIPELINE LORE")
    print("=" * 60)
    
    # 1. Recreate collections
    await ensure_collections()
    
    embedder = FastEmbedAdapter()
    
    # 2. Embed and upsert for each collection
    for col_name, filepath in COLLECTIONS.items():
        print(f"\nProcessing {filepath}...")
        chunks = parse_lore_chunks(filepath)
        print(f"[i] Parsed {len(chunks)} chunks for `{col_name}`")
        
        success = 0
        for section, text in chunks:
            try:
                vector = await embedder.embed_text(text)
                point_id = str(uuid.uuid4())
                await qdrant_service.upsert_lore(
                    collection=col_name,
                    point_id=point_id,
                    vector=vector,
                    text_content=text,
                    section=section,
                )
                print(f"  [+] [{section}] {text[:50]}...")
                success += 1
            except Exception as e:
                print(f"  [!] Failed chunk [{section}]: {e}")
                
        print(f"[DONE] Ingested {success}/{len(chunks)} chunks into `{col_name}`")
        
    print("\n[COMPLETE] Ingestion finished successfully.\n")

if __name__ == "__main__":
    asyncio.run(main())
