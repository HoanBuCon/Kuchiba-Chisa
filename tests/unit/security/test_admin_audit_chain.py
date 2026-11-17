"""Hash-chained, append-only admin audit (SEC-ADM-007, SEC-ADM-008)."""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.rbac import Role, RoleAuditAction, RoleAuditEvent
from app.domain.services.audit_chain import (
    GENESIS_HASH,
    AuditRecord,
    canonical_payload,
    compute_hash,
    record_hash,
    verify_chain,
)
from app.infrastructure.database.models.admin_audit_event import AdminAuditEventModel
from app.infrastructure.security.postgres_role_audit import PostgresRoleAuditSink

MIGRATION = (
    Path(__file__).resolve().parents[3]
    / "alembic_migrations"
    / "versions"
    / "d5e2b8f4a173_add_admin_audit_events.py"
)
NOW = datetime(2026, 11, 17, 12, 0, tzinfo=UTC)


def _chain(count: int) -> list[AuditRecord]:
    records: list[AuditRecord] = []
    prev = GENESIS_HASH
    for seq in range(1, count + 1):
        fields: dict[str, Any] = {
            "actor": "admin-1",
            "action": "role.grant",
            "target": f"account:{seq}",
            "reason": "beta tester",
            "request_id": None,
            "created_at": NOW + timedelta(seconds=seq),
            "detail": {"role": "chia_con", "expires_at": None, "authz_ver_after": seq},
        }
        digest = compute_hash(prev, canonical_payload(**fields))
        records.append(AuditRecord(seq=seq, prev_hash=prev, hash=digest, **fields))
        prev = digest
    return records


def test_hash_covers_previous_hash_and_fields() -> None:
    first, second = _chain(2)

    assert first.prev_hash == GENESIS_HASH
    assert second.prev_hash == first.hash
    assert len(first.hash) == 64
    assert first.hash != second.hash


def test_intact_chain_verifies() -> None:
    result = verify_chain(_chain(4))

    assert result.intact
    assert result.checked == 4


def test_empty_chain_is_intact() -> None:
    assert verify_chain([]).intact


def test_edited_row_is_reported_as_first_broken_link() -> None:
    records = _chain(4)
    records[1] = replace(records[1], reason="edited after the fact")

    result = verify_chain(records)

    assert result.first_broken_seq == 2
    assert not result.intact


def test_deleted_row_breaks_the_following_link() -> None:
    records = _chain(4)
    del records[1]

    assert verify_chain(records).first_broken_seq == 3


def test_recomputed_hash_on_edited_row_still_breaks_next_link() -> None:
    records = _chain(3)
    forged = replace(records[0], reason="forged")

    records[0] = replace(forged, hash=record_hash(forged))

    assert verify_chain(records).first_broken_seq == 2


class _FakeSession(AsyncSession):
    """Minimal session double that records what the sink adds."""

    def __init__(self, last_hash: str | None) -> None:
        self.last_hash = last_hash
        self.added: list[AdminAuditEventModel] = []
        self.executed: list[str] = []

    async def execute(self, statement: Any, params: Any = None, **_: Any) -> None:  # type: ignore[override]
        self.executed.append(str(statement))

    async def scalar(self, *_: Any, **__: Any) -> str | None:  # type: ignore[override]
        return self.last_hash

    def add(self, instance: Any, *_: Any, **__: Any) -> None:  # type: ignore[override]
        self.added.append(instance)

    async def flush(self, *_: Any, **__: Any) -> None:  # type: ignore[override]
        return None


def _event() -> RoleAuditEvent:
    return RoleAuditEvent(
        RoleAuditAction.GRANT,
        "11111111-1111-1111-1111-111111111111",
        uuid.UUID("22222222-2222-2222-2222-222222222222"),
        Role.CHIA_CON,
        "beta tester",
        NOW,
        authz_ver_after=3,
        request_id="req-1",
    )


@pytest.mark.asyncio
async def test_sink_appends_linked_row_without_personal_data() -> None:
    session = _FakeSession(last_hash="a" * 64)

    await PostgresRoleAuditSink().record(session, _event())

    (row,) = session.added
    assert row.prev_hash == "a" * 64
    assert row.actor == "11111111-1111-1111-1111-111111111111"
    assert row.action == "role.grant"
    assert row.target == "account:22222222-2222-2222-2222-222222222222"
    assert row.reason == "beta tester"
    assert row.request_id == "req-1"
    assert row.detail == {"role": "chia_con", "expires_at": None, "authz_ver_after": 3}
    assert "@" not in repr(row.detail) + row.target + row.actor
    assert "pg_advisory_xact_lock" in session.executed[0]
    expected = compute_hash(
        "a" * 64,
        canonical_payload(
            actor=row.actor,
            action=row.action,
            target=row.target,
            reason=row.reason,
            request_id=row.request_id,
            created_at=NOW,
            detail=row.detail,
        ),
    )
    assert row.hash == expected


@pytest.mark.asyncio
async def test_first_sink_row_links_to_genesis() -> None:
    session = _FakeSession(last_hash=None)

    await PostgresRoleAuditSink().record(session, _event())

    assert session.added[0].prev_hash == GENESIS_HASH


@pytest.mark.asyncio
async def test_sink_rejects_non_sqlalchemy_session() -> None:
    with pytest.raises(TypeError):
        await PostgresRoleAuditSink().record(object(), _event())


def test_migration_installs_append_only_triggers() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")

    assert "BEFORE UPDATE OR DELETE ON admin_audit_events" in sql
    assert "BEFORE TRUNCATE ON admin_audit_events" in sql
    assert "RAISE EXCEPTION" in sql
    assert 'down_revision = "c4d7a1e92b58"' in sql
