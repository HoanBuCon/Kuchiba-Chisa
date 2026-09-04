"""Pure, versioned manifest contracts for a staged lore corpus."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from dataclasses import dataclass

from app.domain.models.evidence import EvidenceAccess

_SHA256 = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class LoreManifestRow:
    """One immutable vector-record identity included in a corpus checksum."""

    point_id: str
    chunk_hash: str
    parent_id: str
    source_id: str
    corpus_version: str
    access: EvidenceAccess

    def __post_init__(self) -> None:
        if not all(
            (
                self.point_id,
                self.parent_id,
                self.source_id,
                self.corpus_version,
            )
        ):
            raise ValueError("lore manifest rows require point, parent, source, and corpus version")
        if _SHA256.fullmatch(self.chunk_hash.lower()) is None:
            raise ValueError("lore manifest rows require a SHA-256 child checksum")

    def canonical(self) -> str:
        """Stable serialization safe to hash and independent of Qdrant ordering."""
        return "|".join(
            (
                self.point_id,
                self.chunk_hash.lower(),
                self.parent_id,
                self.source_id,
                self.corpus_version,
                self.access.scope,
                self.access.subject_id or "",
                self.access.tenant_id or "",
                self.access.channel_id or "",
            )
        )


def lore_manifest_checksum(rows: Iterable[LoreManifestRow]) -> str:
    """Calculate the order-independent SHA-256 checksum of staged lore records."""
    return hashlib.sha256(
        "\n".join(sorted(row.canonical() for row in rows)).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class ParentManifestRow:
    """One immutable parent-document identity included in a corpus checksum."""

    parent_id: str
    content_hash: str
    source_id: str
    corpus_version: str
    access: EvidenceAccess

    def __post_init__(self) -> None:
        if not all((self.parent_id, self.source_id, self.corpus_version)):
            raise ValueError("parent manifest rows require parent, source, and corpus version")
        if _SHA256.fullmatch(self.content_hash.lower()) is None:
            raise ValueError("parent manifest rows require a SHA-256 content checksum")

    def canonical(self) -> str:
        return "|".join(
            (
                self.parent_id,
                self.content_hash.lower(),
                self.source_id,
                self.corpus_version,
                self.access.scope,
                self.access.subject_id or "",
                self.access.tenant_id or "",
                self.access.channel_id or "",
            )
        )


def parent_manifest_checksum(rows: Iterable[ParentManifestRow]) -> str:
    """Calculate the order-independent SHA-256 checksum of staged parent documents."""
    return hashlib.sha256(
        "\n".join(sorted(row.canonical() for row in rows)).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class ParentCorpusManifest:
    """Non-content verification receipt read from the parent store."""

    parent_count: int
    checksum: str

    def __post_init__(self) -> None:
        if self.parent_count < 0:
            raise ValueError("parent manifest count must not be negative")
        if _SHA256.fullmatch(self.checksum.lower()) is None:
            raise ValueError("parent manifest checksum must be SHA-256")
