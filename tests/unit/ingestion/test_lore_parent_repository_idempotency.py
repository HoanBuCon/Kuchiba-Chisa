"""FR-ING-005 persistence regression for deterministic parent identities."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from app.domain.entities.lore import LoreParent
from app.infrastructure.database.repositories.lore_parent import LoreParentRepository


@pytest.mark.asyncio
async def test_save_parent_merges_a_deterministic_parent_id_for_safe_retry() -> None:
    session = AsyncMock()
    repository = LoreParentRepository(session)
    parent = LoreParent(
        id=uuid.uuid5(uuid.NAMESPACE_URL, "wiki:19:revision:97:section:19-H2-01"),
        page_id=19,
        page_title="Chisa",
        heading="Lore",
        markdown="Chisa studies at Startorch Academy.",
        source_file="raw://19/" + "a" * 64 + ".wikitext",
        revision_id=97,
        corpus_version="v20260905",
    )

    await repository.save_parent(parent)

    session.merge.assert_awaited_once()
    session.flush.assert_awaited_once()
