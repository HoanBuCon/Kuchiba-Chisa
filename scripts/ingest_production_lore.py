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

COLLECTION_DIRS = {
    "character_lore": ["data/lore/character_lore", "data/lore/relationship_lore"],
    "world_lore": ["data/lore/world_lore"],
    "story_lore": ["data/lore/story_lore"],
}

def parse_markdown_to_parent_sections(filepath: str) -> list[dict]:
    if not os.path.exists(filepath):
        print(f"[!] File not found: {filepath}")
        return []

    with open(filepath, "r", encoding="utf-8") as f:
        raw_content = f.read().strip()

    basename = os.path.splitext(os.path.basename(filepath))[0]
    default_title = " ".join([w.capitalize() for w in basename.split("_")])

    # Case 1: File has H2 headings
    if "\n## " in ("\n" + raw_content):
        raw_sections = re.split(r'\n## ', '\n' + raw_content)
        sections_list = []
        for sec in raw_sections:
            sec = sec.strip()
            if not sec or sec.startswith("#"):  # Skip the H1 header section
                continue
            
            parts = sec.split("\n", 1)
            title = parts[0].strip()
            body = parts[1].strip() if len(parts) > 1 else ""
            
            sections_list.append({
                "title": title,
                "parent_full_text": f"## {title}\n\n{body}",
                "body_content": body
            })
        return sections_list
    
    # Case 2: Flat file without H2
    else:
        body_without_h1 = re.sub(r'^#[^\n]*\n', '', raw_content).strip()
        return [{
            "title": default_title,
            "parent_full_text": raw_content,
            "body_content": body_without_h1
        }]

def extract_child_chunks(body_text: str) -> list[str]:
    child_chunks = []
    lines = body_text.split("\n")
    for line in lines:
        line = line.strip()
        if not line or line.startswith("##"):
            continue
        
        # Strip bullet points
        if line.startswith("-"):
            line = line[1:].strip()
            
        if len(line) > 250:
            # Segment long paragraphs by sentences
            sentences = re.split(r'(?<=[.!?]) +', line)
            for sentence in sentences:
                sentence = sentence.strip()
                if sentence:
                    child_chunks.append(sentence)
        else:
            if line:
                child_chunks.append(line)
                
    return child_chunks

async def ensure_collections():
    client = get_qdrant_client()
    collections = await client.get_collections()
    names = [c.name for c in collections.collections]
    
    for col_name in COLLECTION_DIRS.keys():
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
    print(" INGESTING PRODUCTION PIPELINE LORE (PARENT-CHILD SCHEMA)")
    print("=" * 60)
    
    # 1. Recreate collections
    await ensure_collections()
    
    embedder = FastEmbedAdapter()
    
    # 2. Embed and upsert for each collection
    for col_name, dirpaths in COLLECTION_DIRS.items():
        print(f"\nProcessing collection `{col_name}`...")
        
        success = 0
        for dirpath in dirpaths:
            if not os.path.exists(dirpath):
                print(f"[!] Directory not found: {dirpath}")
                continue
                
            for root, _, files in os.walk(dirpath):
                for file in files:
                    if file.endswith(".md"):
                        filepath = os.path.join(root, file)
                        sub_category = os.path.splitext(file)[0]
                        
                        parent_sections = parse_markdown_to_parent_sections(filepath)
                        
                        for parent_sec in parent_sections:
                            parent_id = str(uuid.uuid4())
                            parent_title = parent_sec["title"]
                            parent_full_text = parent_sec["parent_full_text"]
                            
                            child_texts = extract_child_chunks(parent_sec["body_content"])
                            
                            for child_text in child_texts:
                                try:
                                    vector = await embedder.embed_text(child_text)
                                    point_id = str(uuid.uuid4())
                                    
                                    # Create the metadata payload
                                    payload = {
                                        "parent_id": parent_id,
                                        "parent_full_text": parent_full_text,
                                        "category": col_name,
                                        "sub_category": sub_category,
                                        "character": "chisa",
                                        "importance": 0.8,
                                        "source_file": filepath.replace("\\", "/")
                                    }
                                    
                                    await qdrant_service.upsert_lore(
                                        collection=col_name,
                                        point_id=point_id,
                                        vector=vector,
                                        text_content=child_text,
                                        section=parent_title,
                                        payload=payload
                                    )
                                    success += 1
                                except Exception as e:
                                    print(f"  [!] Failed child point in section [{parent_title}]: {e}")
                                    
        print(f"[DONE] Ingested {success} child points into `{col_name}`")
        
    print("\n[COMPLETE] Ingestion finished successfully.\n")

if __name__ == "__main__":
    asyncio.run(main())
