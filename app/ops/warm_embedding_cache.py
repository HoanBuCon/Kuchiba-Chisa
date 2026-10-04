"""Download the embedding model into the shared cache volume, once, before startup.

Usage (deploy step, before `up -d app worker`):
    docker compose run --rm --no-deps app python -m app.ops.warm_embedding_cache

The API workers and the background worker share the ``model_cache`` volume. If
they all start on an empty cache they download the same files concurrently and
can leave a partial snapshot that fails to load. Running this single process
first makes later starts cache hits.

Like ``qdrant_snapshot`` it avoids the full application Settings (a one-off
``run`` command does not get the secrets the service command exports). The model
registration mirrors ``FastEmbedAdapter._get_model``; FASTEMBED_CACHE_PATH comes
from the compose environment.
"""

from __future__ import annotations

import os
import sys

from fastembed import TextEmbedding
from fastembed.common.model_description import ModelSource, PoolingType

_E5_SMALL = "intfloat/multilingual-e5-small"
_EXPECTED_DIMENSION = 384


def main() -> int:
    model_name = os.environ.get("EMBEDDING_MODEL", _E5_SMALL)
    if model_name == _E5_SMALL:
        TextEmbedding.add_custom_model(
            model=_E5_SMALL,
            pooling=PoolingType.MEAN,
            normalization=True,
            sources=ModelSource(hf=_E5_SMALL),
            dim=_EXPECTED_DIMENSION,
            model_file="onnx/model.onnx",
        )
    model = TextEmbedding(model_name=model_name)
    vector = next(iter(model.embed(["query: warm-up"])))
    if len(vector) != _EXPECTED_DIMENSION:
        print(f"unexpected embedding dimension {len(vector)}", file=sys.stderr)
        return 1
    print(f"embedding cache ready: {model_name} ({len(vector)} dims)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
