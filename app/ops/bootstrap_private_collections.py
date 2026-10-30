"""Create the private memory collections and their ``__active`` aliases on a fresh VPS.

Usage (fresh install only, after Qdrant is up):
    scripts/ops/app_python.sh -m app.ops.bootstrap_private_collections

Production startup requires every runtime alias. The three lore aliases must come
from an approved corpus release (snapshot restore or the governed ingestion DAG)
and are never created here. The private memory collections start empty, so this
creates ``<name>__v1`` with the standard collection config and points the alias at
it. It is idempotent: an existing alias is left untouched.
"""

from __future__ import annotations

import asyncio
import sys

from qdrant_client.http.models import CreateAlias, CreateAliasOperation

from app.config.settings import settings
from app.infrastructure.vector.qdrant.qdrant_service import (
    COLLECTION_GUILD_MEMORIES,
    COLLECTION_IMAGE_MEMORIES,
    COLLECTION_MEMORIES,
    active_collection_alias,
    qdrant_service,
)

PRIVATE_COLLECTIONS = (COLLECTION_MEMORIES, COLLECTION_GUILD_MEMORIES, COLLECTION_IMAGE_MEMORIES)
_INITIAL_VERSION = "v1"


async def bootstrap() -> int:
    operations = []
    for logical in PRIVATE_COLLECTIONS:
        if await qdrant_service.active_alias_target(logical) is not None:
            print(f"{active_collection_alias(logical)} already exists; skipped", file=sys.stderr)
            continue
        target = await qdrant_service.prepare_versioned_collection(
            logical, _INITIAL_VERSION, settings.QDRANT_EMBEDDING_DIM
        )
        operations.append(
            CreateAliasOperation(
                create_alias=CreateAlias(
                    collection_name=target, alias_name=active_collection_alias(logical)
                )
            )
        )
    if operations:
        await qdrant_service._client.update_collection_aliases(
            change_aliases_operations=operations
        )
    readiness = await qdrant_service.validate_active_collections()
    for result in readiness.values():
        state = "ready" if result.ready else f"NOT READY ({result.reason})"
        print(f"{result.active_name}: {state}", file=sys.stderr)
    return 0 if all(readiness[name].ready for name in PRIVATE_COLLECTIONS) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(bootstrap()))
