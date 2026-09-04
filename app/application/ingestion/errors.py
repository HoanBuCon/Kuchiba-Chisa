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


class CorpusSafetyGateError(RuntimeError):
    """A staging corpus contains prompt-poisoned content and cannot be published."""

    def __init__(self, *, quarantined_count: int, report_path: str) -> None:
        self.quarantined_count = quarantined_count
        self.report_path = report_path
        super().__init__(
            "Corpus safety gate quarantined "
            f"{quarantined_count} chunk(s); staging was not started. "
            f"Review {report_path!r} with curator access."
        )


class IngestionStageError(RuntimeError):
    """A stage reported unacknowledged work, so the staging run cannot succeed."""

    def __init__(self, *, stage: str, failed_items: int) -> None:
        self.stage = stage
        self.failed_items = failed_items
        super().__init__(
            f"Ingestion stage {stage!r} reported {failed_items} failed item(s); "
            "the staging run was not promoted."
        )
