"""Hash chain over admin audit rows so tampering is detectable (SEC-ADM-007)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

GENESIS_HASH = "0" * 64


@dataclass(frozen=True, slots=True)
class AuditRecord:
    """One stored audit row; `detail` holds only non-personal state (SEC-ADM-008)."""

    seq: int
    actor: str
    action: str
    target: str
    reason: str
    request_id: str | None
    created_at: datetime
    detail: dict[str, Any]
    prev_hash: str
    hash: str


@dataclass(frozen=True, slots=True)
class ChainVerification:
    checked: int
    first_broken_seq: int | None

    @property
    def intact(self) -> bool:
        return self.first_broken_seq is None


def canonical_payload(
    *,
    actor: str,
    action: str,
    target: str,
    reason: str,
    request_id: str | None,
    created_at: datetime,
    detail: dict[str, Any],
) -> str:
    """Stable JSON so the same fields always hash to the same digest."""
    return json.dumps(
        {
            "actor": actor,
            "action": action,
            "target": target,
            "reason": reason,
            "request_id": request_id,
            "created_at": created_at.astimezone(UTC).isoformat(),
            "detail": detail,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def compute_hash(prev_hash: str, payload: str) -> str:
    return hashlib.sha256(f"{prev_hash}|{payload}".encode()).hexdigest()


def record_hash(record: AuditRecord) -> str:
    payload = canonical_payload(
        actor=record.actor,
        action=record.action,
        target=record.target,
        reason=record.reason,
        request_id=record.request_id,
        created_at=record.created_at,
        detail=record.detail,
    )
    return compute_hash(record.prev_hash, payload)


def verify_chain(records: Iterable[AuditRecord]) -> ChainVerification:
    """Walk rows in sequence order and report the first row whose link or hash is wrong."""
    expected_prev = GENESIS_HASH
    checked = 0
    for record in records:
        checked += 1
        if record.prev_hash != expected_prev or record.hash != record_hash(record):
            return ChainVerification(checked, record.seq)
        expected_prev = record.hash
    return ChainVerification(checked, None)
