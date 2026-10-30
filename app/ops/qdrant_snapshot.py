"""Create a full Qdrant storage snapshot and stream it to stdout (backup helper).

Usage (from the VPS host):
    docker compose exec -T app python -m app.ops.qdrant_snapshot > qdrant.snapshot

The snapshot covers every collection and alias, including the active corpus
release and private memory collections. The server-side copy is deleted after a
successful download so snapshots do not accumulate on the VPS disk.

It reads only QDRANT_URL/QDRANT_API_KEY from the environment instead of the full
application Settings: `docker compose exec` does not inherit the secrets that the
service command exports (REDIS_PASSWORD, DATABASE_URL), so production Settings
validation would refuse to load.
"""

from __future__ import annotations

import os
import sys

import httpx

_CHUNK = 1024 * 1024


def main() -> int:
    api_key = os.environ.get("QDRANT_API_KEY", "")
    headers = {"api-key": api_key} if api_key else {}
    base = os.environ.get("QDRANT_URL", "http://qdrant:6333").rstrip("/")
    with httpx.Client(base_url=base, headers=headers, timeout=600.0) as client:
        created = client.post("/snapshots", params={"wait": "true"})
        created.raise_for_status()
        name = created.json()["result"]["name"]
        written = 0
        try:
            with client.stream("GET", f"/snapshots/{name}") as response:
                response.raise_for_status()
                for chunk in response.iter_bytes(_CHUNK):
                    sys.stdout.buffer.write(chunk)
                    written += len(chunk)
            sys.stdout.buffer.flush()
        finally:
            client.delete(f"/snapshots/{name}")
    print(f"qdrant snapshot {name}: {written} bytes", file=sys.stderr)
    return 0 if written > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
