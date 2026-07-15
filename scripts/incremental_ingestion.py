import os
import sys
import hashlib
import sqlite3
import asyncio
import uuid
import re
from datetime import datetime
from typing import List, Dict, Set

# Ensure correct path resolution
sys.path.append(os.getcwd())

from app.config.settings import settings
from app.infrastructure.database.engine import AsyncSessionFactory
from app.infrastructure.database.repositories.lore_parent import LoreParentRepository
from app.domain.entities.lore import LoreParent, LorePayload
from app.infrastructure.vector.qdrant.qdrant_service import qdrant_service, get_qdrant_client
from app.infrastructure.embeddings.fastembed_adapter import FastEmbedAdapter
from app.domain.services.rag.entity_resolver import EntityResolver
from qdrant_client.http import models as qdrant_models

VECTOR_SIZE = settings.QDRANT_EMBEDDING_DIM
DB_PATH = "data/ingestion.sqlite"

COLLECTION_DIRS = {
    "lore": [
        "data/lore/character_lore", 
        "data/lore/relationship_lore",
        "data/lore/world_lore",
        "data/lore/story_lore"
    ]
}

def init_sqlite():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS file_hashes (
            filepath TEXT PRIMARY KEY,
            md5_hash TEXT,
            last_updated TIMESTAMP
        )
    """)
    conn.commit()
    return conn

def compute_md5(filepath: str) -> str:
    hash_md5 = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

def extract_infobox(text: str) -> (Dict[str, str], str):
    """
    Dummy extraction of infoboxes or frontmatter for now.
    Returns (metadata_dict, remaining_text)
    """
    # Just returning raw text for now, could be upgraded with Regex for YAML or wiki infoboxes
    return {}, text

def parse_markdown_to_parent_sections(filepath: str) -> List[Dict]:
    """
    Splits document by H2 headers (##)
    """
    with open(filepath, "r", encoding="utf-8") as f:
        raw_content = f.read().strip()

    basename = os.path.splitext(os.path.basename(filepath))[0]
    default_title = " ".join([w.capitalize() for w in basename.split("_")])

    _, clean_content = extract_infobox(raw_content)

    if "\n## " in ("\n" + clean_content):
        raw_sections = re.split(r'\n## ', '\n' + clean_content)
        sections = []
        for sec in raw_sections:
            sec = sec.strip()
            if not sec or sec.startswith("#"):  
                continue
            parts = sec.split("\n", 1)
            title = parts[0].strip()
            body = parts[1].strip() if len(parts) > 1 else ""
            sections.append({
                "title": title,
                "parent_full_text": f"## {title}\n\n{body}",
                "body_content": body
            })
        return sections
    else:
        body = re.sub(r'^#[^\n]*\n', '', clean_content).strip()
        return [{
            "title": default_title,
            "parent_full_text": clean_content,
            "body_content": body
        }]

def extract_child_chunks(body_text: str) -> List[str]:
    child_chunks = []
    lines = body_text.split("\n")
    for line in lines:
        line = line.strip()
        if not line or line.startswith("##"):
            continue
        if line.startswith("-"):
            line = line[1:].strip()
            
        if len(line) > 250:
            sentences = re.split(r'(?<=[.!?]) +', line)
            for sentence in sentences:
                sentence = sentence.strip()
                if sentence:
                    child_chunks.append(sentence)
        else:
            if line:
                child_chunks.append(line)
    return child_chunks

async def process_file(
    filepath: str, 
    col_name: str, 
    embedder: FastEmbedAdapter, 
    entity_resolver: EntityResolver,
    db_session
):
    parent_sections = parse_markdown_to_parent_sections(filepath)
    parent_repo = LoreParentRepository(db_session)
    
    success_count = 0
    for parent_sec in parent_sections:
        parent_id = uuid.uuid4()
        parent_full_text = parent_sec["parent_full_text"]
        
        # Save Parent Document
        parent_doc = LoreParent(id=parent_id, full_text=parent_full_text)
        await parent_repo.save_parent(parent_doc)
        
        child_texts = extract_child_chunks(parent_sec["body_content"])
        
        for idx, child_text in enumerate(child_texts):
            try:
                vector = await embedder.embed_text(child_text)
                point_id = str(uuid.uuid4())
                
                entities_found = list(entity_resolver.extract_entities(child_text))
                
                payload = LorePayload(
                    parent_id=str(parent_id),
                    source_file=filepath.replace("\\", "/"),
                    chunk_index=idx,
                    text_content=child_text,
                    entities=entities_found,
                    schema_version=2
                )
                
                await qdrant_service.upsert_lore(
                    collection=col_name,
                    point_id=point_id,
                    vector=vector,
                    payload=payload
                )
                success_count += 1
            except Exception as e:
                print(f"  [!] Failed child point in {filepath}: {e}")
                
    return success_count

async def main():
    print("=" * 60)
    print(" INCREMENTAL LORE INGESTION PIPELINE (PHASE 4)")
    print("=" * 60)
    
    sqlite_conn = init_sqlite()
    cursor = sqlite_conn.cursor()
    
    embedder = FastEmbedAdapter()
    entity_resolver = EntityResolver()
    entity_resolver.load()

    # Pre-create Qdrant collections if they don't exist
    client = get_qdrant_client()
    collections = await client.get_collections()
    names = [c.name for c in collections.collections]
    
    for col_name in COLLECTION_DIRS.keys():
        if col_name not in names:
            await client.create_collection(
                collection_name=col_name,
                vectors_config=qdrant_models.VectorParams(
                    size=VECTOR_SIZE,
                    distance=qdrant_models.Distance.COSINE,
                ),
            )
            print(f"[+] Created Qdrant collection: {col_name}")

    total_ingested = 0
    total_skipped = 0
    
    async with AsyncSessionFactory() as db_session:
        for col_name, dirpaths in COLLECTION_DIRS.items():
            print(f"\nProcessing collection `{col_name}`...")
            
            for dirpath in dirpaths:
                if not os.path.exists(dirpath):
                    continue
                    
                for root, _, files in os.walk(dirpath):
                    for file in files:
                        if file.endswith(".md"):
                            filepath = os.path.join(root, file)
                            
                            current_hash = compute_md5(filepath)
                            
                            cursor.execute("SELECT md5_hash FROM file_hashes WHERE filepath=?", (filepath,))
                            row = cursor.fetchone()
                            
                            if row and row[0] == current_hash:
                                total_skipped += 1
                                continue
                                
                            print(f"  [*] Ingesting: {filepath}")
                            
                            count = await process_file(filepath, col_name, embedder, entity_resolver, db_session)
                            total_ingested += count
                            
                            cursor.execute(
                                "INSERT OR REPLACE INTO file_hashes (filepath, md5_hash, last_updated) VALUES (?, ?, ?)",
                                (filepath, current_hash, datetime.now())
                            )
                            sqlite_conn.commit()

        await db_session.commit()
                            
    print(f"\n[COMPLETE] Skipped {total_skipped} unchanged files.")
    print(f"[COMPLETE] Ingested {total_ingested} new child chunks.")

if __name__ == "__main__":
    asyncio.run(main())
