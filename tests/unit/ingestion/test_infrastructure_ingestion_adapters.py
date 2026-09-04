from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest
from click.testing import CliRunner
from sqlalchemy.dialects import postgresql

from app.infrastructure.database.repositories.postgres_wiki_sync_state import (
    PostgresWikiSyncStateRepository,
)
from app.infrastructure.ingestion.mediawiki_source import MediaWikiSource, MediaWikiSourceError
from app.infrastructure.ingestion.raw_storage import FileRawStorage, RawStoragePathError


async def _allow_public_test_destination(_: str, __: int) -> tuple[str, ...]:
    return ("93.184.216.34",)


@pytest.mark.asyncio
async def test_raw_storage_uses_opaque_content_addressed_uris_and_rejects_paths(
    tmp_path: Path,
) -> None:
    storage = FileRawStorage(tmp_path / "raw")

    uri = await storage.save_raw_page("../../untrusted-title", 27, "{{lore|safe}}")

    assert uri.startswith("raw://27/")
    assert await storage.read_raw_page(uri) == "{{lore|safe}}"
    assert list((tmp_path / "raw").rglob("*.wikitext"))
    with pytest.raises(RawStoragePathError):
        await storage.read_raw_page("../../secrets.txt")


@pytest.mark.asyncio
async def test_mediawiki_source_enumerates_versioned_category_pages_and_downloads_content() -> None:
    calls: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        calls.append(params)
        if params.get("list") == "categorymembers":
            return httpx.Response(
                200,
                json={"query": {"categorymembers": [{"pageid": 19}]}},
            )
        if params.get("prop") == "revisions" and params.get("pageids") == "19":
            if "content" in params.get("rvprop", ""):
                return httpx.Response(
                    200,
                    json={
                        "query": {
                            "pages": [
                                {
                                    "pageid": 19,
                                    "title": "Chisa",
                                    "revisions": [
                                        {
                                            "revid": 97,
                                            "timestamp": "2026-01-02T03:04:05Z",
                                            "slots": {"main": {"*": "{{Character|Chisa}}"}},
                                        }
                                    ],
                                }
                            ]
                        }
                    },
                )
            return httpx.Response(
                200,
                json={
                    "query": {
                        "pages": [
                            {
                                "pageid": 19,
                                "title": "Chisa",
                                "revisions": [{"revid": 97, "timestamp": "2026-01-02T03:04:05Z"}],
                            }
                        ]
                    }
                },
            )
        raise AssertionError(f"unexpected source request: {params}")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        source = MediaWikiSource(
            http_client=client,
            api_url="https://wiki.example.test/api.php",
            categories=("Lore",),
            allowed_hosts=("wiki.example.test",),
            destination_validator=_allow_public_test_destination,
        )
        pages = [page async for page in source.get_all_pages()]
        revision = await source.download_page(19)

    assert pages[0].page_id == 19
    assert pages[0].latest_revision_id == 97
    assert pages[0].last_updated == datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    assert revision.content == "{{Character|Chisa}}"
    assert revision.revision_id == 97
    assert all(call.get("formatversion") == "2" for call in calls)


@pytest.mark.asyncio
async def test_mediawiki_source_rejects_mismatched_or_malformed_source_content() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "query": {
                    "pages": [
                        {
                            "pageid": 99,
                            "title": "Wrong page",
                            "revisions": [
                                {
                                    "revid": 1,
                                    "timestamp": "2026-01-02T03:04:05Z",
                                    "slots": {"main": {"*": "content"}},
                                }
                            ],
                        }
                    ]
                }
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        source = MediaWikiSource(
            http_client=client,
            api_url="https://wiki.example.test/api.php",
            categories=("Lore",),
            allowed_hosts=("wiki.example.test",),
            max_retries=0,
            destination_validator=_allow_public_test_destination,
        )
        with pytest.raises(MediaWikiSourceError, match="identifier mismatch"):
            await source.download_page(19)


@pytest.mark.parametrize(
    "api_url",
    (
        "http://wiki.example.test/api.php",
        "https://wiki.example.test:8443/api.php",
        "https://wiki.example.test/api.php?untrusted=1",
        "https://user:password@wiki.example.test/api.php",
        "https://169.254.169.254/latest/meta-data",
    ),
)
def test_mediawiki_source_rejects_unapproved_egress_endpoints(api_url: str) -> None:
    with pytest.raises(ValueError, match="allowlisted HTTPS"):
        MediaWikiSource(
            http_client=AsyncMock(spec=httpx.AsyncClient),
            api_url=api_url,
            categories=("Lore",),
            allowed_hosts=("wiki.example.test",),
        )


@pytest.mark.asyncio
async def test_mediawiki_source_rejects_private_destination_before_request() -> None:
    async def reject_private_destination(_: str, __: int) -> tuple[str, ...]:
        from app.shared.security.network_destinations import NetworkDestinationError

        raise NetworkDestinationError("private address")

    client = AsyncMock(spec=httpx.AsyncClient)

    source = MediaWikiSource(
        http_client=client,
        api_url="https://wiki.example.test/api.php",
        categories=("Lore",),
        allowed_hosts=("wiki.example.test",),
        max_retries=0,
        destination_validator=reject_private_destination,
    )

    with pytest.raises(MediaWikiSourceError, match="request failed"):
        _ = [page async for page in source.get_all_pages()]

    client.get.assert_not_awaited()


@pytest.mark.asyncio
async def test_mediawiki_source_disables_redirect_following() -> None:
    client = AsyncMock(spec=httpx.AsyncClient)
    client.get.return_value = httpx.Response(
        302,
        json={},
        request=httpx.Request("GET", "https://wiki.example.test/api.php"),
    )

    source = MediaWikiSource(
        http_client=client,
        api_url="https://wiki.example.test/api.php",
        categories=("Lore",),
        allowed_hosts=("wiki.example.test",),
        max_retries=0,
        destination_validator=_allow_public_test_destination,
    )

    with pytest.raises(MediaWikiSourceError, match="request failed"):
        _ = [page async for page in source.get_all_pages()]

    assert client.get.await_args.kwargs["follow_redirects"] is False


@pytest.mark.asyncio
async def test_wiki_sync_state_never_moves_a_revision_cursor_backwards() -> None:
    session = AsyncMock()
    repository = PostgresWikiSyncStateRepository(session)

    await repository.update_sync_state(19, "Chisa", 97, "downloaded")

    statement = session.execute.await_args.args[0]
    compiled = str(statement.compile(dialect=postgresql.dialect()))
    assert "ON CONFLICT" in compiled
    assert "excluded.revision_id >= wiki_sync_state.revision_id" in compiled
    session.commit.assert_awaited_once()


def test_canonical_cli_rejects_an_active_alias_before_any_side_effect() -> None:
    from app.infrastructure.ingestion.cli import cli

    result = CliRunner().invoke(
        cli,
        [
            "run-dag",
            "--source-id",
            "c7ad47e2-41a1-5a88-8a88-bc3c0b9c0638",
            "--staging-collection",
            "character_lore__active",
        ],
    )

    assert result.exit_code != 0
    assert "ValidationError" in result.output
