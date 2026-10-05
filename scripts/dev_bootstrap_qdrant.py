"""Development-only: make a local Qdrant satisfy the runtime ``*__active`` alias contract.

Production-style startup (API readiness and the worker) requires an alias
``<collection>__active`` for each of the six logical collections. Older local
development stacks hold the data in plain collections such as ``world_lore``.
This tool, run by ``chisa dev start``:

* leaves an existing alias untouched;
* points a missing alias at the *existing* plain collection of that name (no data
  is copied, moved, modified or deleted);
* creates an empty collection ``<name>__dev1`` plus alias only when no collection
  exists at all.

It refuses to run unless ``APP_ENV=development``. It never promotes, rolls back,
or deletes anything; governed corpus releases keep using ``manage_qdrant_alias.py``.
Because a plain collection is not a versioned corpus release, the lore answer cache
is bypassed (fail-safe) until a governed release is promoted; retrieval is unchanged.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from qdrant_client.http.models import CreateAlias, CreateAliasOperation  # noqa: E402

from app.config.settings import settings  # noqa: E402
from app.infrastructure.vector.qdrant.qdrant_service import (  # noqa: E402
    ALL_COLLECTIONS,
    active_collection_alias,
    qdrant_service,
)

_DEV_VERSION = "dev1"


async def bootstrap() -> int:
    if not settings.is_dev:
        print(f"refusing to run: APP_ENV={settings.APP_ENV} (development only)", file=sys.stderr)
        return 2
    client = qdrant_service._client
    existing = {c.name for c in (await client.get_collections()).collections}
    operations = []
    for logical in ALL_COLLECTIONS:
        if await qdrant_service.active_alias_target(logical) is not None:
            print(f"{active_collection_alias(logical)}: already present")
            continue
        if logical in existing:
            target = logical
            origin = "existing collection"
        else:
            target = await qdrant_service.prepare_versioned_collection(
                logical, _DEV_VERSION, settings.QDRANT_EMBEDDING_DIM
            )
            origin = "new empty collection"
        operations.append(
            CreateAliasOperation(
                create_alias=CreateAlias(
                    collection_name=target, alias_name=active_collection_alias(logical)
                )
            )
        )
        print(f"{active_collection_alias(logical)}: -> {target} ({origin})")
    if operations:
        await client.update_collection_aliases(change_aliases_operations=operations)
    readiness = await qdrant_service.validate_active_collections()
    failed = [r for r in readiness.values() if not r.ready]
    for result in failed:
        print(f"NOT READY {result.active_name}: {result.reason}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(bootstrap()))
