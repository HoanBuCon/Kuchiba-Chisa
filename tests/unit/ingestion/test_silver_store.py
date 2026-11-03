"""Silver store: lossless round trip, idempotent writes, path safety."""

import pytest

from app.domain.ingestion.documents import (
    Block,
    BlockKind,
    CanonicalDocument,
    DialogueTurn,
    GlossaryEntry,
    TurnKind,
)
from app.infrastructure.ingestion.silver.silver_store import FileSilverStore

DOC = CanonicalDocument(
    page_id=7,
    title="Chisa",
    revid=3,
    family="resonator",
    cleaner_version="silver-1+abc",
    url="https://w/Chisa",
    license="CC-BY-SA",
    blocks=(
        Block(BlockKind.STORY, ("Voicelines",), "Line.", title="Thoughts: I", variant="Male"),
        Block(
            BlockKind.DIALOGUE,
            ("Dialogue",),
            "A: hi",
            turns=(
                DialogueTurn(TurnKind.LINE, "hi", "A"),
                DialogueTurn(TurnKind.CHOICE, "Go", depth=1),
            ),
        ),
    ),
    infoboxes=({"name": "Chisa"},),
    glossary=(GlossaryEntry("Ashinohara", "A nation."),),
    links=("Ashinohara",),
    removed={"ui": 10},
)


def test_round_trip_is_lossless(tmp_path) -> None:
    store = FileSilverStore(tmp_path)

    path = store.save("k1", DOC)

    assert path == store.path_for(7, "k1") == "silver/7/k1.json.gz"
    assert store.load(path) == DOC


def test_existing_key_is_not_rewritten(tmp_path) -> None:
    store = FileSilverStore(tmp_path)
    path = store.save("k1", DOC)
    modified = (tmp_path / path).stat().st_mtime_ns

    store.save("k1", DOC)

    assert (tmp_path / path).stat().st_mtime_ns == modified


def test_load_refuses_paths_outside_the_root(tmp_path) -> None:
    with pytest.raises(ValueError, match="escapes"):
        FileSilverStore(tmp_path / "s").load("../x.json.gz")
