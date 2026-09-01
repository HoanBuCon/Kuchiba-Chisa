"""Typed failures for ingestion work that has not been durably acknowledged."""

from __future__ import annotations


class QdrantIngestionAcknowledgementError(RuntimeError):
    """A Qdrant write was not acknowledged, so the ingestion job must fail.

    Earlier point IDs may have been acknowledged before this error. Chunk IDs
    are deterministic, therefore retrying the same staging target is idempotent
    and must be preferred over promoting a partially written corpus.
    """

    def __init__(
        self,
        *,
        target_collection: str,
        failed_point_id: str,
        acknowledged_count: int,
    ) -> None:
        self.target_collection = target_collection
        self.failed_point_id = failed_point_id
        self.acknowledged_count = acknowledged_count
        super().__init__(
            "Qdrant did not acknowledge ingestion point "
            f"{failed_point_id!r} in {target_collection!r}; "
            f"{acknowledged_count} point(s) were acknowledged before the failure."
        )
