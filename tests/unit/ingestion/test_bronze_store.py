"""Bronze store: content-addressed keys, idempotent writes, round trip and path safety."""

from datetime import UTC, datetime

import pytest

from app.domain.interfaces.wiki_ingestion import ParsedPage
from app.infrastructure.ingestion.bronze_store import FileBronzeStore, render_hash


def _page(html: str = "<p>Chisa</p>") -> ParsedPage:
    return ParsedPage(
        page_id=7,
        title="Chisa",
        revid=99,
        html=html,
        categories=("Resonators",),
        templates=("Template:Infobox Resonator",),
        sections=({"line": "Profile"},),
        properties={"infoboxes": "[]"},
        url="https://wiki.test/wiki/Chisa",
        license="CC BY-SA",
        fetched_at=datetime(2026, 11, 1, tzinfo=UTC),
    )


def test_key_is_relative_and_content_addressed(tmp_path) -> None:
    key = FileBronzeStore(tmp_path).save(_page())

    assert key == f"bronze/7/99-{render_hash('<p>Chisa</p>')[:16]}.json.gz"
    assert (tmp_path / key).is_file()


def test_same_render_is_written_once_and_new_render_gets_new_key(tmp_path) -> None:
    store = FileBronzeStore(tmp_path)
    first = store.save(_page())
    modified = (tmp_path / first).stat().st_mtime_ns

    assert store.save(_page()) == first
    assert (tmp_path / first).stat().st_mtime_ns == modified
    assert store.save(_page("<p>Chisa v2</p>")) != first


def test_round_trip_keeps_fields(tmp_path) -> None:
    store = FileBronzeStore(tmp_path)

    record = store.load(store.save(_page()))

    assert record["schema_version"] == 1
    assert record["title"] == "Chisa"
    assert record["fetched_at"] == "2026-11-01T00:00:00+00:00"
    assert not list(tmp_path.rglob("*.tmp"))


def test_load_refuses_keys_outside_the_root(tmp_path) -> None:
    with pytest.raises(ValueError, match="escapes"):
        FileBronzeStore(tmp_path / "store").load("../secret.json.gz")
