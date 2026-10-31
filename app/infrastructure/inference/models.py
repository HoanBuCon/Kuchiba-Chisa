"""FastEmbed registrations for models it does not ship; no application Settings (ops tools)."""

from __future__ import annotations

from fastembed import TextEmbedding
from fastembed.common.model_description import ModelSource, PoolingType

E5_SMALL = "intfloat/multilingual-e5-small"
E5_SMALL_DIMENSION = 384


def register_known_models() -> None:
    """Register multilingual-e5-small with mean pooling; repeated calls are harmless."""
    if any(description.model == E5_SMALL for description in TextEmbedding._list_supported_models()):
        return
    TextEmbedding.add_custom_model(
        model=E5_SMALL,
        pooling=PoolingType.MEAN,
        normalization=True,
        sources=ModelSource(hf=E5_SMALL),
        dim=E5_SMALL_DIMENSION,
        model_file="onnx/model.onnx",
    )
