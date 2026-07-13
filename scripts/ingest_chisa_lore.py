"""
Chisa Lore Ingestion Script
============================
Reads `data/lore/chisa_lore.md`, chunks it by semantic blocks, embeds each chunk with FastEmbed,
and upserts into Qdrant `chisa_lore` collection.

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
from app.config.settings import settings

LORE_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "lore", "chisa_lore.md")
LORE_DIR = os.path.dirname(LORE_FILE)
COLLECTION = "chisa_lore"
VECTOR_SIZE = settings.QDRANT_EMBEDDING_DIM


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


def _flush_block(chunks: list[tuple[str, str]], section_name: str, block_lines: list[str]) -> None:
    if not block_lines:
        return

    block_text = " ".join(line.strip() for line in block_lines if line.strip())
    if block_text:
        chunks.append((section_name, f"[{section_name}] {block_text}"))


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


def _chunk_section_by_rules(section_name: str, bullets: list[str]) -> list[str]:
    if not bullets:
        return []

    # The goal is to keep semantically related facts together while avoiding huge vectors.
    if section_name == "Thông Tin Cơ Bản":
        return [" ".join(bullets)]

    if section_name == "Cốt truyện cốt lõi: Chisa & Vòng lặp Honami":
        groups: list[list[str]] = [
            bullets[:4],
            bullets[4:8],
            bullets[8:],
        ]
        return [" ".join(group) for group in groups if group]

    if section_name in {
        "Hành trình phá vỡ vòng lặp: Rover & Chisa",
        "Sức Mạnh và Khả Năng (Resonance Forte)",
        "Rủi Ro Năng Lực (Overclocking)",
        "Tính Cách Lý Trí (Canon)",
        "Nội Tâm và Quan Điểm Về Con Người",
        "Con Người Chisa (Persona đối với Senpai)",
        "Sở Thích Cá Nhân",
        "Điểm Yếu",
    }:
        return [" ".join(bullets)]

    # Fallback: preserve the current section as a single semantic block.
    return [" ".join(bullets)]


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
        bullets = _parse_bullets(section_body)
        semantic_chunks = _chunk_section_by_rules(section_name, bullets)

        for chunk_text in semantic_chunks:
            if chunk_text.strip():
                chunks.append((section_name, f"[{section_name}] {chunk_text.strip()}"))

    return chunks


def discover_lore_files(lore_dir: str) -> list[str]:
    files: list[str] = []
    for entry in sorted(os.listdir(lore_dir)):
        full_path = os.path.join(lore_dir, entry)
        if os.path.isfile(full_path) and entry.lower().endswith(".md"):
            files.append(full_path)
    return files


def choose_lore_file(lore_files: list[str]) -> str:
    print("\nAvailable lore files:")
    for index, file_path in enumerate(lore_files, start=1):
        print(f"  [{index}] {os.path.basename(file_path)}")

    while True:
        selection = input("Select lore file to ingest (number): ").strip()
        if not selection.isdigit():
            print("  Invalid input. Enter a number from the list above.")
            continue

        chosen_index = int(selection)
        if 1 <= chosen_index <= len(lore_files):
            return lore_files[chosen_index - 1]

        print("  Selection out of range. Try again.")


async def main():
    print("=" * 50)
    print(" CHISA LORE INGESTION")
    print("=" * 50)

    lore_files = discover_lore_files(LORE_DIR)
    if not lore_files:
        print(f"[!] No lore files found in {LORE_DIR}")
        return

    selected_lore_file = choose_lore_file(lore_files)
    print(f"\n[i] Selected lore file: {selected_lore_file}")

    # 1. Ensure collection
    await ensure_collection()

    # 2. Parse lore file
    chunks = parse_lore_chunks(selected_lore_file)
    print(f"[i] Parsed {len(chunks)} lore chunks from {selected_lore_file}")

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
