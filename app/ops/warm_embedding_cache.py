"""Download the embedding model into the shared cache volume once, before inference starts.

Usage (deploy step, before `up -d inference`):
    docker compose --profile ops run --rm model-warmup

The inference service has no egress (chisa_data is internal), so it can only load a
model this step already cached. Running a single download also avoids two processes
writing the same snapshot. Like ``qdrant_snapshot`` it avoids the full application
Settings; FASTEMBED_CACHE_PATH comes from the compose environment.
"""

from __future__ import annotations

import os
import sys

from fastembed import TextEmbedding

from app.infrastructure.inference.models import E5_SMALL, E5_SMALL_DIMENSION, register_known_models


def main() -> int:
    model_name = os.environ.get("EMBEDDING_MODEL", E5_SMALL)
    register_known_models()
    model = TextEmbedding(model_name=model_name)
    vector = next(iter(model.embed(["query: warm-up"])))
    if model_name == E5_SMALL and len(vector) != E5_SMALL_DIMENSION:
        print(f"unexpected embedding dimension {len(vector)}", file=sys.stderr)
        return 1
    print(f"embedding cache ready: {model_name} ({len(vector)} dims)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
