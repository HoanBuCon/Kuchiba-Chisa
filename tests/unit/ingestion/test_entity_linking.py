"""Entity linking for questions: bilingual aliases, no diacritics, longest name, whole words."""

from app.domain.ingestion.entity_linking import EntityLinker, fold_for_matching
from app.domain.ingestion.knowledge import Alias, AliasKind, Entity, KnowledgeBase


def _entity(page_id: int, title: str) -> Entity:
    return Entity(page_id, title, "lore", {}, None, None, None, None)


KB = KnowledgeBase(
    entities=(
        _entity(1, "Chisa"),
        _entity(2, "Chisa/Backstory"),
        _entity(3, "Chisa/Voicelines"),
        _entity(4, "Black Shores"),
        _entity(5, "Black Shores Archipelago"),
        _entity(6, "Port"),
    ),
    aliases=(
        Alias("Kuchiba Chisa", "Chisa", AliasKind.REDIRECT, "high"),
        Alias("\u5343\u54b2 Chisa", "Chisa", AliasKind.OTHER_LANGUAGE, "high"),
        Alias("Honami", "Black Shores", AliasKind.INFERRED, "inferred"),
        Alias("Nowhere Land", "Missing Page", AliasKind.REDIRECT, "high"),
    ),
    glossary=(),
    quests=(),
    locations=(),
)
LINKER = EntityLinker.from_knowledge(KB)


def test_folding_removes_case_and_vietnamese_diacritics() -> None:
    assert fold_for_matching("Đà Nẵng CHISA") == "da nang chisa"


def test_names_are_found_without_diacritics_or_case() -> None:
    assert LINKER.link("chisa hoc o dau vay") == ("Chisa",)
    assert LINKER.link("Kuchiba Chisa là ai?") == ("Chisa",)


def test_longest_name_wins_and_several_entities_keep_their_order() -> None:
    assert LINKER.link("From the Black Shores Archipelago to Chisa") == (
        "Black Shores Archipelago",
        "Chisa",
    )


def test_only_whole_words_match() -> None:
    assert LINKER.link("Chisas and Porter") == ()


def test_inferred_and_unknown_aliases_do_not_link() -> None:
    assert LINKER.link("Honami or Nowhere Land") == ()


def test_own_pages_include_subpages() -> None:
    assert LINKER.own_pages(("Chisa",)) == ("Chisa", "Chisa/Backstory", "Chisa/Voicelines")


def test_curated_aliases_can_bridge_vietnamese_names() -> None:
    curated = (Alias("Hoc vien Bo Den", "Black Shores", "curated", "high"),)

    linker = EntityLinker.from_knowledge(KB, curated)

    assert linker.link("Học viện Bờ Đen ở đâu") == ("Black Shores",)


def test_empty_knowledge_links_nothing() -> None:
    assert EntityLinker.from_knowledge(KnowledgeBase((), (), (), (), ())).link("Chisa") == ()
