import asyncio
import os
import sys
import uuid
import re

PROJECT_ROOT = r"d:\Hoc_Tap\Code\Du_An_Ca_Nhan\Chisa_bot\kuchiba_chisa"
sys.path.append(PROJECT_ROOT)

# Ensure UTF-8 output encoding for print
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from app.infrastructure.vector.qdrant.qdrant_service import qdrant_service, get_qdrant_client
from app.infrastructure.embeddings.fastembed_adapter import FastEmbedAdapter
from qdrant_client.http import models as qdrant_models

LORE_FILE = os.path.join(PROJECT_ROOT, "data", "lore", "chisa_lore.md")
TEMP_COLLECTION = "chisa_lore_bullet_test"

def parse_bullet_chunks(filepath: str) -> list[tuple[str, str]]:
    with open(filepath, "r", encoding="utf-8") as f:
        raw = f.read()

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
        
        # Split body by lines and handle bullet points
        raw_lines = [l.strip() for l in section_body.split("\n") if l.strip()]
        
        for line in raw_lines:
            # Match lines starting with -
            if line.startswith("-"):
                content = line[1:].strip() # Remove the dash
                if content:
                    chunks.append((section_name, f"[{section_name}] {content}"))
            else:
                chunks.append((section_name, f"[{section_name}] {line}"))
                
    return chunks

async def test_search(query: str, embedder: FastEmbedAdapter):
    from app.shared.utils.query_cleaner import clean_query_for_rag
    cleaned = clean_query_for_rag(query)
    print(f"\nQuery: '{query}'")
    print(f"Cleaned: '{cleaned}'")
    vector = await embedder.embed_text(cleaned)
    
    results = await qdrant_service.search_lore(
        collection=TEMP_COLLECTION,
        query_vector=vector,
        limit=6,
        score_threshold=0.0
    )
    for idx, r in enumerate(results):
        payload = r["payload"]
        print(f"  Rank {idx+1}. Score: {r['score']:.4f} | Section: {payload.get('section')}")
        print(f"    Text: {payload.get('text_content')}")

async def main():
    print("Parsing bullet chunks...")
    chunks = parse_bullet_chunks(LORE_FILE)
    print(f"Total chunks created: {len(chunks)}")
    
    # 2. Setup Temp Collection
    client = get_qdrant_client()
    collections = await client.get_collections()
    if TEMP_COLLECTION in [c.name for c in collections.collections]:
        await client.delete_collection(TEMP_COLLECTION)
    
    await client.create_collection(
        collection_name=TEMP_COLLECTION,
        vectors_config=qdrant_models.VectorParams(
            size=384,
            distance=qdrant_models.Distance.COSINE,
        ),
    )
    
    # 3. Embed & Upsert
    embedder = FastEmbedAdapter()
    for section, text in chunks:
        vector = await embedder.embed_text(text)
        await qdrant_service.upsert_lore(
            collection=TEMP_COLLECTION,
            point_id=str(uuid.uuid4()),
            vector=vector,
            text_content=text,
            section=section
        )
    print("Ingested successfully.")
    
    # 4. Search
    await test_search("Chào em Chisa, kể anh nghe về trường em đang học đi", embedder)
    await test_search("Em hãy kể về khoảng thời gian tại Honami đi Chisa", embedder)
    
    # Cleanup temp collection
    await client.delete_collection(TEMP_COLLECTION)

if __name__ == "__main__":
    asyncio.run(main())
