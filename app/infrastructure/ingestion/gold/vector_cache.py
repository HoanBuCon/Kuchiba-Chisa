"""File vector cache: append-only numpy shards, so a crash loses at most the unsaved batch (L4)."""

from __future__ import annotations

import os
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from uuid import uuid4

import numpy as np


class FileVectorCache:
    def __init__(self, root: Path, model_id: str) -> None:
        slug = "".join(c if c.isalnum() else "_" for c in model_id)
        self._directory = root / "vectors" / slug

    def load(self, keys: Iterable[str]) -> dict[str, list[float]]:
        wanted = set(keys)
        found: dict[str, list[float]] = {}
        for shard in sorted(self._directory.glob("*.npz")):
            with np.load(shard) as data:
                for key, vector in zip(data["keys"].tolist(), data["vectors"], strict=True):
                    if key in wanted:
                        found[key] = vector.tolist()
        return found

    def save(self, vectors: Mapping[str, Sequence[float]]) -> None:
        self._directory.mkdir(parents=True, exist_ok=True)
        target = self._directory / f"{uuid4().hex}.npz"
        temporary = target.with_suffix(".tmp")
        with temporary.open("wb") as handle:
            np.savez(
                handle,
                keys=np.array(list(vectors)),
                vectors=np.array(list(vectors.values()), dtype=np.float32),
            )
        # Readers only glob finished shards, so a partial write is never visible.
        os.replace(temporary, target)
