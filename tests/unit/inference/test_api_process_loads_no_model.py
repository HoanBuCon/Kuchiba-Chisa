"""KNW-007 acceptance: the API and worker composition never imports a model-loading module.

The fastembed package itself may be imported (qdrant-client probes for it); what must never
happen is constructing a model, which only these engine modules do.
"""

import subprocess
import sys

MODEL_LOADERS = (
    "app.infrastructure.embeddings.fastembed_adapter",
    "app.infrastructure.rag.fastembed_cross_encoder_reranker",
    "app.infrastructure.inference.models",
)
PROBE = f"""
import sys
import app.main  # noqa: F401
import app.worker  # noqa: F401
from app.application.dependencies import container
container.embedder
container.cross_encoder_reranker
print("LOADED=" + ",".join(m for m in {MODEL_LOADERS!r} if m in sys.modules))
"""


def test_api_and_worker_composition_never_import_model_loaders() -> None:
    result = subprocess.run(
        [sys.executable, "-c", PROBE], capture_output=True, text=True, timeout=120, check=True
    )
    loaded = [line for line in result.stdout.splitlines() if line.startswith("LOADED=")]
    assert loaded == ["LOADED="]
