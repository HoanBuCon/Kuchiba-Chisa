import os
import sys
import hashlib
import sqlite3
import asyncio
import uuid
import re
from datetime import datetime
from typing import List, Dict, Set, Optional

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
    "character_lore": [
        "data/lore/character_lore",
        "data/lore/relationship_lore"
    ],
    "world_lore": [
        "data/lore/world_lore"
    ],
    "story_lore": [
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

def parse_markdown_to_parent_sections(filepath: str, page_id: int) -> List[Dict]:
    """
    Splits document by H2 (##) and H3 (###) headers to build precise parent sections.
    Generates section_id and full hierarchical heading_path.
    """
    with open(filepath, "r", encoding="utf-8") as f:
        raw_content = f.read().strip()

    basename = os.path.splitext(os.path.basename(filepath))[0]
    default_title = " ".join([w.capitalize() for w in basename.split("_")])

    _, clean_content = extract_infobox(raw_content)
    lines = clean_content.split("\n")

    sections = []
    current_h2_title = None
    current_h3_title = None
    current_heading = "Lead"
    current_depth = 1
    current_lines = []
    
    h2_idx = 0
    h3_idx = 0

    def flush_section():
        nonlocal current_lines, current_heading, current_depth
        if current_lines:
            body = "\n".join(current_lines).strip()
            parts = [default_title]
            if current_h2_title and current_h2_title != "Lead":
                parts.append(current_h2_title)
            if current_h3_title:
                parts.append(current_h3_title)
                
            heading_path = " > ".join(parts)
            sec_id = f"{page_id}-H2-{h2_idx:02d}"
            if h3_idx > 0:
                sec_id += f"-H3-{h3_idx:02d}"

            sections.append({
                "title": current_heading or default_title,
                "parent_full_text": body,
                "body_content": body,
                "section_id": sec_id,
                "heading_path": heading_path,
                "section_depth": current_depth
            })
            current_lines = []

    for line in lines:
        if line.startswith("## "):
            flush_section()
            h2_idx += 1
            h3_idx = 0
            current_h2_title = line[3:].strip()
            current_h3_title = None
            current_heading = current_h2_title
            current_depth = 2
            current_lines.append(line)
        elif line.startswith("### "):
            flush_section()
            h3_idx += 1
            current_h3_title = line[4:].strip()
            current_heading = current_h3_title
            current_depth = 3
            current_lines.append(line)
        else:
            current_lines.append(line)

    flush_section()
    return sections

def extract_child_chunks(
    body_text: str,
    min_chunk_chars: int = 100,
    max_chunk_chars: int = 800,
    overlap_chars: int = 100,
) -> List[str]:
    """
    Semantic-aware chunking for lore documents:
    1. Splits body text by paragraphs (double newlines).
    2. Merges consecutive small paragraphs up to max_chunk_chars.
    3. Splits oversized paragraphs by sentence boundaries if they exceed max_chunk_chars.
    4. Adds overlap between adjacent chunks to maintain context across boundaries.
    """
    if not body_text or not body_text.strip():
        return []

    # Step 1: Split by paragraph (double newline)
    raw_paragraphs = re.split(r'\n\s*\n', body_text)
    paragraphs = []
    for p in raw_paragraphs:
        cleaned_p = p.strip()
        if cleaned_p and not cleaned_p.startswith("##"):
            paragraphs.append(cleaned_p)

    if not paragraphs:
        return []

    # Step 2: Merge small paragraphs until reaching max_chunk_chars
    merged_blocks = []
    current_block = ""

    for para in paragraphs:
        para_text = re.sub(r'^\s*[-*]\s+', '', para, flags=re.MULTILINE)
        if len(current_block) + len(para_text) + 1 <= max_chunk_chars:
            current_block = f"{current_block}\n{para_text}".strip() if current_block else para_text
        else:
            if current_block:
                merged_blocks.append(current_block)
            current_block = para_text

    if current_block:
        merged_blocks.append(current_block)

    # Step 3: Split oversized blocks by sentence boundaries
    final_chunks = []
    for block in merged_blocks:
        if len(block) <= max_chunk_chars:
            if len(block) >= min_chunk_chars or not final_chunks:
                final_chunks.append(block)
            else:
                if len(final_chunks[-1]) + len(block) + 1 <= max_chunk_chars + 200:
                    final_chunks[-1] = f"{final_chunks[-1]}\n{block}"
                else:
                    final_chunks.append(block)
        else:
            sentences = re.split(r'(?<=[.!?。])\s+', block)
            current_sent_chunk = ""
            for sent in sentences:
                sent = sent.strip()
                if not sent:
                    continue
                if len(current_sent_chunk) + len(sent) + 1 <= max_chunk_chars:
                    current_sent_chunk = f"{current_sent_chunk} {sent}".strip()
                else:
                    if current_sent_chunk:
                        final_chunks.append(current_sent_chunk)
                    current_sent_chunk = sent
            if current_sent_chunk:
                final_chunks.append(current_sent_chunk)

    # Step 4: Apply overlap between adjacent chunks
    if overlap_chars > 0 and len(final_chunks) > 1:
        overlapped_chunks = [final_chunks[0]]
        for i in range(1, len(final_chunks)):
            prev_tail = final_chunks[i - 1][-overlap_chars:]
            overlapped_chunks.append(f"{prev_tail}\n{final_chunks[i]}")
        final_chunks = overlapped_chunks

    return [c for c in final_chunks if len(c) >= 20]

def derive_metadata_from_path(filepath: str) -> Dict[str, Optional[str]]:
    """
    Derive metadata attributes (page_type, source_type) from directory structure and filename.
    """
    normalized = filepath.replace("\\", "/").lower()
    page_type = None
    if "character_lore" in normalized:
        page_type = "Character"
    elif "world_lore" in normalized:
        page_type = "World"
    elif "story_lore" in normalized:
        page_type = "Story"
    elif "relationship_lore" in normalized:
        page_type = "Relationship"
    
    return {
        "page_type": page_type,
        "source_type": "Lore Document",
    }

async def process_file(
    filepath: str, 
    col_name: str, 
    embedder: FastEmbedAdapter, 
    entity_resolver: EntityResolver,
    db_session
):
    page_id = int(hashlib.md5(filepath.encode("utf-8")).hexdigest()[:7], 16)
    parent_sections = parse_markdown_to_parent_sections(filepath, page_id)
    parent_repo = LoreParentRepository(db_session)
    
    meta = derive_metadata_from_path(filepath)
    page_type = meta.get("page_type")
    source_type = meta.get("source_type")

    source_file_clean = filepath.replace("\\", "/")
    
    success_count = 0
    for parent_sec in parent_sections:
        parent_id = uuid.uuid4()
        parent_full_text = parent_sec["parent_full_text"]
        
        # Save Parent Document
        parent_doc = LoreParent(
            id=parent_id,
            page_id=page_id,
            page_title=parent_sec["title"],
            heading=parent_sec["title"],
            markdown=parent_full_text,
            source_file=source_file_clean,
            revision_id=1,
            section_id=parent_sec.get("section_id"),
            heading_path=parent_sec.get("heading_path"),
            section_depth=parent_sec.get("section_depth")
        )
        await parent_repo.save_parent(parent_doc)
        
        child_texts = extract_child_chunks(parent_sec["body_content"])
        
        for idx, child_text in enumerate(child_texts):
            try:
                vector = await embedder.embed_text(child_text, prefix="passage: ")
                point_id = str(uuid.uuid4())
                
                entities_found = list(entity_resolver.extract_entities(child_text))
                
                # Derive region and faction from entity resolver if available
                region = None
                faction = None
                canonical_name = None
                entity_id = None
                entity_type = page_type.upper() if page_type else "LORE"
                
                for ent in entities_found:
                    node = entity_resolver.get_node(ent) if hasattr(entity_resolver, "get_node") else None
                    if node:
                        if not canonical_name:
                            canonical_name = getattr(node, "canonical_name", ent)
                            entity_id = getattr(node, "id", None)
                        if getattr(node, "region", None) and not region:
                            region = node.region
                        if getattr(node, "faction", None) and not faction:
                            faction = node.faction
                
                payload = LorePayload(
                    parent_id=str(parent_id),
                    section_id=parent_sec.get("section_id"),
                    page_id=page_id,
                    source_file=source_file_clean,
                    chunk_index=idx,
                    text_content=child_text,
                    heading_path=parent_sec.get("heading_path"),
                    section_depth=parent_sec.get("section_depth"),
                    canonical_name=canonical_name,
                    entity_id=entity_id,
                    entity_type=entity_type,
                    entities=entities_found,
                    region=region,
                    faction=faction,
                    source_type=source_type,
                    page_type=page_type,
                    schema_version=3
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
