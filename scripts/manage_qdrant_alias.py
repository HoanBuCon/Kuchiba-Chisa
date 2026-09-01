"""Explicit, auditable Qdrant version/alias lifecycle operations.

This tool never deletes a collection. A candidate must be built and validated
before ``promote`` atomically switches the runtime alias. The old physical
collection remains available for an explicit ``rollback``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config.settings import settings
from app.infrastructure.vector.qdrant.qdrant_service import (
    ALL_COLLECTIONS,
    active_collection_alias,
    qdrant_service,
    versioned_collection_name,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "promote", "rollback"))
    parser.add_argument("--collection", choices=ALL_COLLECTIONS, required=True)
    parser.add_argument("--actor", required=True, help="Authorized operator identity for audit output")
    parser.add_argument("--execute", action="store_true", help="Perform the requested state change")
    parser.add_argument("--version", help="Version component for prepare, e.g. corpus_20260901")
    parser.add_argument("--target", help="Verified physical target for promote or rollback")
    parser.add_argument(
        "--expected-point-count",
        type=int,
        help="Exact candidate point count required before alias promotion",
    )
    parser.add_argument(
        "--expected-dimension",
        type=int,
        default=settings.QDRANT_EMBEDDING_DIM,
        help="Expected vector dimension for the candidate collection",
    )
    return parser


def _plan(args: argparse.Namespace) -> dict[str, Any]:
    event: dict[str, Any] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "actor": args.actor,
        "action": args.action,
        "logical_collection": args.collection,
        "active_alias": active_collection_alias(args.collection),
        "expected_dimension": args.expected_dimension,
        "execute": args.execute,
    }
    if args.action == "prepare":
        if not args.version:
            raise ValueError("--version is required for prepare")
        event["target_collection"] = versioned_collection_name(args.collection, args.version)
    else:
        if not args.target:
            raise ValueError("--target is required for promote or rollback")
        if args.expected_point_count is None:
            raise ValueError("--expected-point-count is required for promote or rollback")
        event["target_collection"] = args.target
        event["expected_point_count"] = args.expected_point_count
    return event


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    event = _plan(args)
    if not args.execute:
        event["status"] = "dry_run"
        return event

    if args.action == "prepare":
        target = await qdrant_service.prepare_versioned_collection(
            logical_collection=args.collection,
            version=args.version,
            vector_size=args.expected_dimension,
        )
        event.update(status="prepared", target_collection=target)
        return event

    promotion = await qdrant_service.promote_active_alias(
        logical_collection=args.collection,
        target_collection=args.target,
        expected_point_count=args.expected_point_count,
        expected_dimension=args.expected_dimension,
    )
    event.update(
        status="promoted" if args.action == "promote" else "rolled_back",
        previous_collection=promotion.previous_collection,
        actual_point_count=promotion.actual_point_count,
    )
    return event


def main() -> None:
    args = _build_parser().parse_args()
    try:
        event = asyncio.run(_run(args))
    except (ValueError, RuntimeError) as exc:
        raise SystemExit(f"Qdrant lifecycle operation rejected: {exc}") from exc
    print(json.dumps(event, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
