import asyncio
import json
import sys
import uuid
from pathlib import Path
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert

from app.infrastructure.database.engine import AsyncSessionFactory
from app.infrastructure.database.models.lore_parent import LoreParentModel

async def sync_parents():
    canonical_path = Path("data/canonical/canonical.jsonl")
    if not canonical_path.exists():
        print(f"[ERROR] {canonical_path} not found.")
        sys.exit(1)

    print(f"[+] Reading canonical pages from: {canonical_path}")
    pages = []
    with open(canonical_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                pages.append(json.loads(line))

    records = []
    for p in pages:
        identity = p.get("identity", {})
        page_id = identity.get("page_id")
        page_title = identity.get("title", "")
        slug = identity.get("canonical_slug", "")
        source_file = f"data/canonical/{slug}.json"
        meta = p.get("_meta", {})
        revision_id = meta.get("revision_id", 1)

        for s in p.get("sections", []):
            sec_id = s.get("section_id")
            heading = s.get("title", "Lead")
            content = s.get("content", "").strip()
            level = s.get("level", 1)

            if not sec_id or not content:
                continue

            parent_uuid = uuid.uuid5(uuid.NAMESPACE_URL, f"parent:{sec_id}")
            heading_path = f"{page_title} > {heading}" if heading != "Lead" else page_title

            records.append({
                "id": parent_uuid,
                "page_id": page_id,
                "page_title": page_title,
                "heading": heading,
                "markdown": content,
                "source_file": source_file,
                "revision_id": revision_id,
                "section_id": sec_id,
                "heading_path": heading_path,
                "section_depth": level,
            })

    print(f"[+] Total parent section records to sync to PostgreSQL: {len(records)}")

    async with AsyncSessionFactory() as session:
        print("[*] Truncating old legacy records in PostgreSQL lore_parents table...")
        await session.execute(delete(LoreParentModel))
        await session.commit()

        print("[*] Inserting new LoreParent records in batches...")
        batch_size = 200
        for i in range(0, len(records), batch_size):
            batch = records[i : i + batch_size]
            stmt = insert(LoreParentModel).values(batch)
            stmt = stmt.on_conflict_do_update(
                index_elements=["id"],
                set_={
                    "page_id": stmt.excluded.page_id,
                    "page_title": stmt.excluded.page_title,
                    "heading": stmt.excluded.heading,
                    "markdown": stmt.excluded.markdown,
                    "heading_path": stmt.excluded.heading_path,
                    "section_depth": stmt.excluded.section_depth,
                }
            )
            await session.execute(stmt)
            await session.commit()

    print(f"[SUCCESS] Successfully synced {len(records)} LoreParent sections to PostgreSQL database.")

if __name__ == "__main__":
    asyncio.run(sync_parents())
