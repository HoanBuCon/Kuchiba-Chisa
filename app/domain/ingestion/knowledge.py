"""Structured knowledge built deterministically from pages and silver (KNW-004, ING-005, E6-E10)."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, replace

from app.domain.ingestion.chunking import Chunk
from app.domain.ingestion.documents import BlockKind, CanonicalDocument, TurnKind
from app.domain.ingestion.pages import PageState, PageStatus

LOCATION_CATEGORY = re.compile(r"^(?:Category:)?(.+) Locations$")
LOWERCASE_WORD = re.compile(r"(?<![\w'-])[a-z]{4,}(?![\w'-])")
VERSION_CATEGORY = re.compile(r"^(?:Category:)?Released in Version (\d+\.\d+)$")
# Catch-all location categories that say nothing about where a page is.
GENERIC_LOCATION_PARENTS = frozenset({"Event", "Domain", "Upcoming"})
NATION_FIELDS = ("nation",)
LOCATION_FIELDS = ("region", "area", "location", "startLocation", "base")
ALIAS_FIELDS = ("alias", "realname")
QUEST_FAMILIES = frozenset({"main_quest", "quest"})
MAX_SPEAKERS = 8
MIN_GLOSSARY_LETTERS = 3
MIN_PREFIX_PAGES = 2
MIN_PREFIX_LENGTH = 4
MIN_MENTION_LENGTH = 4
PREFIX_STOPWORDS = frozenset(
    {"The", "Old", "New", "Great", "Grand", "Upper", "Lower", "North", "South"}
)


class AliasKind:
    REDIRECT = "redirect"
    RENAME = "rename"
    OTHER_LANGUAGE = "other_language"
    INFOBOX = "infobox"
    INFERRED = "inferred"


# Entities known only from infobox data: their pages are in no text tier yet (ING-014).
STRUCTURED_ONLY = "structured"


@dataclass(frozen=True)
class StructuredPage:
    """Infobox data of a page outside the text tiers; a page with none stays recorded."""

    revid: int
    infoboxes: tuple[dict[str, str], ...]
    redirects: tuple[str, ...] = ()


@dataclass(frozen=True)
class LocationEdge:
    child: str
    parent: str
    source: str


@dataclass(frozen=True)
class Alias:
    alias: str
    target: str
    kind: str
    confidence: str
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class Entity:
    page_id: int
    title: str
    entity_type: str | None
    fields: dict[str, str]
    # Inference sources are recorded because both may be absent or guessed (E7, E8).
    nation: str | None
    nation_source: str | None
    game_version: str | None
    version_source: str | None


def has_corpus_text(entity: Entity) -> bool:
    """A name with no text to retrieve would only send entity channels to empty results."""
    return entity.entity_type != STRUCTURED_ONLY


@dataclass(frozen=True)
class GlossaryTerm:
    term: str
    definition: str
    pages: int
    variants: tuple[str, ...] = ()


@dataclass(frozen=True)
class Quest:
    page_id: int
    title: str
    fields: dict[str, str]
    description: str | None
    summary: str | None
    steps: tuple[str, ...]
    # Deterministic narration lines stand in for the Summary most quests lack (E6).
    narration: tuple[str, ...]
    speakers: tuple[str, ...]
    locations: tuple[str, ...] = ()


@dataclass(frozen=True)
class KnowledgeBase:
    entities: tuple[Entity, ...]
    aliases: tuple[Alias, ...]
    glossary: tuple[GlossaryTerm, ...]
    quests: tuple[Quest, ...]
    locations: tuple[LocationEdge, ...]


def build_location_edges(states: Iterable[PageState]) -> list[LocationEdge]:
    edges = []
    for state in states:
        if state.status is PageStatus.DELETED:
            continue
        for category in state.categories:
            match = LOCATION_CATEGORY.match(category)
            if match and match[1] not in GENERIC_LOCATION_PARENTS and match[1] != state.title:
                edges.append(LocationEdge(state.title, match[1], f"category:{match[1]} Locations"))
    return edges


def location_chain(place: str, parents: Mapping[str, Sequence[str]]) -> list[str]:
    """Walk up every parent breadth first; `seen` guards against cycles in wiki categories."""
    chain, queue, seen = [], list(parents.get(place, ())), {place}
    while queue:
        current = queue.pop(0)
        if current not in seen:
            seen.add(current)
            chain.append(current)
            queue.extend(parents.get(current, ()))
    return chain


def _parents_of(edges: Iterable[LocationEdge]) -> dict[str, list[str]]:
    parents: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        parents[edge.child].append(edge.parent)
    return parents


def _infer_nation(
    title: str,
    fields: Mapping[str, str],
    parents: Mapping[str, Sequence[str]],
    nations: frozenset[str],
) -> tuple[str | None, str | None]:
    """Order from E8: infobox nation, infobox location through the graph, own categories."""
    for name in NATION_FIELDS:
        if fields.get(name):
            return fields[name].split("\n")[0], "infobox"
    for name in LOCATION_FIELDS:
        place = fields.get(name, "").split("\n")[0]
        found = _nation_on_chain(place, parents, nations)
        if place and found:
            return found, "location_graph"
    found = _nation_on_chain(title, parents, nations)
    return (found, "category") if found else (None, None)


def _nation_on_chain(
    place: str, parents: Mapping[str, Sequence[str]], nations: frozenset[str]
) -> str | None:
    if place in nations:
        return place
    return next((p for p in location_chain(place, parents) if p in nations), None)


def _known_nations(documents: Iterable[CanonicalDocument]) -> frozenset[str]:
    return frozenset(
        box["nation"].split("\n")[0]
        for document in documents
        for box in document.infoboxes
        if box.get("nation")
    )


def _version_of(state: PageState) -> str | None:
    for category in state.categories:
        match = VERSION_CATEGORY.match(category)
        if match:
            return match[1]
    return None


def _merged_fields(document: CanonicalDocument) -> dict[str, str]:
    fields: dict[str, str] = {}
    for box in document.infoboxes:
        for key, value in box.items():
            fields.setdefault(key, value)
    return fields


def build_entities(
    documents: Sequence[CanonicalDocument],
    states: Mapping[int, PageState],
    edges: Iterable[LocationEdge],
) -> list[Entity]:
    """Subpages inherit a missing nation and version from their parent page (E7)."""
    parents = _parents_of(edges)
    nations = _known_nations(documents)
    by_title = {document.title: document for document in documents}
    versions = {d.title: _version_of(states[d.page_id]) for d in documents if d.page_id in states}
    entities = []
    for document in documents:
        root = document.title.split("/")[0]
        source_document = by_title.get(root, document)
        fields = _merged_fields(source_document)
        nation, nation_source = _infer_nation(root, fields, parents, nations)
        version, version_source = _resolve_version(document.title, root, versions)
        entities.append(
            Entity(
                document.page_id,
                document.title,
                document.family,
                _merged_fields(document),
                nation,
                nation_source,
                version,
                version_source,
            )
        )
    return entities


def _resolve_version(
    title: str, root: str, versions: Mapping[str, str | None]
) -> tuple[str | None, str | None]:
    if versions.get(title):
        return versions[title], "category"
    if versions.get(root):
        return versions[root], "propagated"
    return None, None


def build_aliases(
    documents: Sequence[CanonicalDocument],
    states: Mapping[int, PageState],
    edges: Sequence[LocationEdge],
) -> list[Alias]:
    aliases: dict[tuple[str, str], Alias] = {}

    def add(alias: Alias) -> None:
        # The first source wins, and sources are added from most to least trusted.
        if alias.alias and alias.alias != alias.target:
            aliases.setdefault((alias.alias.casefold(), alias.target), alias)

    for document in documents:
        state = states.get(document.page_id)
        for title in state.redirects if state else ():
            add(Alias(title, document.title, AliasKind.REDIRECT, "high"))
        for title in state.aliases if state else ():
            add(Alias(title, document.title, AliasKind.RENAME, "high"))
        for language, name in document.other_names:
            add(Alias(name, document.title, AliasKind.OTHER_LANGUAGE, "high", (language,)))
        fields = _merged_fields(document)
        for key in ALIAS_FIELDS:
            for value in fields.get(key, "").split("\n"):
                add(Alias(value.strip(), document.title, AliasKind.INFOBOX, "medium", (key,)))
    for alias in infer_prefix_aliases(edges, _common_words(documents)):
        add(alias)
    return list(aliases.values())


def infer_prefix_aliases(
    edges: Iterable[LocationEdge], common_words: frozenset[str] = frozenset()
) -> list[Alias]:
    """Places sharing a leading word inside one region name that region ("Honami" -> Chronorift)."""
    edges = list(edges)
    places = _place_names(edges)
    parents = _parents_of(edges)
    by_prefix: dict[tuple[str, str], list[str]] = defaultdict(list)
    for edge in edges:
        prefix = edge.child.split(" ")[0].removesuffix("'s").rstrip("':,")
        if _is_usable_prefix(prefix, places) and prefix.casefold() not in common_words:
            by_prefix[(prefix, edge.parent)].append(edge.child)
    targets: dict[str, set[str]] = defaultdict(set)
    for (prefix, parent), children in by_prefix.items():
        if len(children) >= MIN_PREFIX_PAGES and prefix not in parent:
            targets[prefix].add(parent)
    return [
        Alias(
            prefix,
            parent,
            AliasKind.INFERRED,
            "inferred",
            tuple(sorted(by_prefix[(prefix, parent)])),
        )
        for prefix, parents_found in sorted(targets.items())
        for parent in sorted(_most_specific(parents_found, parents))
    ]


def _common_words(documents: Iterable[CanonicalDocument]) -> frozenset[str]:
    """Words seen in lower case are ordinary nouns ("port"); proper names never are ("Honami")."""
    return frozenset(
        word
        for document in documents
        for block in document.blocks
        for word in LOWERCASE_WORD.findall(block.text)
    )


def _is_usable_prefix(prefix: str, places: frozenset[str]) -> bool:
    # A prefix that is itself a place already resolves by name, so it needs no alias.
    return (
        len(prefix) >= MIN_PREFIX_LENGTH
        and prefix[0].isupper()
        and prefix not in PREFIX_STOPWORDS
        and prefix not in places
    )


def _most_specific(targets: set[str], parents: Mapping[str, Sequence[str]]) -> set[str]:
    """Pages sit in both a district and its nation; only the district names the prefix."""
    ancestors = {place for target in targets for place in location_chain(target, parents)}
    return (targets - ancestors) or targets


def _place_names(edges: Iterable[LocationEdge]) -> frozenset[str]:
    return frozenset(name for edge in edges for name in (edge.child, edge.parent))


def _is_valid_term(term: str) -> bool:
    """E10: tooltips also carry UI hints ("???", "Found you!") and choices ("(Comfort her.)")."""
    letters = sum(character.isalpha() for character in term)
    return (
        letters >= MIN_GLOSSARY_LETTERS
        and not term.endswith(("!", "?"))
        and not term.startswith("(")
    )


def build_glossary(documents: Iterable[CanonicalDocument]) -> list[GlossaryTerm]:
    """The canonical definition is the most frequent, then the longest; others stay as variants."""
    definitions: dict[str, Counter[str]] = defaultdict(Counter)
    for document in documents:
        for entry in document.glossary:
            if _is_valid_term(entry.term):
                definitions[entry.term][entry.definition] += 1
    terms = []
    for term, counts in sorted(definitions.items()):
        ranked = sorted(counts, key=lambda text: (-counts[text], -len(text), text))
        terms.append(GlossaryTerm(term, ranked[0], sum(counts.values()), tuple(ranked[1:])))
    return terms


def _section_text(document: CanonicalDocument, section: str) -> str | None:
    texts = [
        b.text
        for b in document.blocks
        if b.section[:1] == (section,) and b.kind is not BlockKind.DIALOGUE
    ]
    return "\n\n".join(texts) or None


def _quest_locations(
    document: CanonicalDocument, fields: Mapping[str, str], places: frozenset[str]
) -> tuple[str, ...]:
    """`startLocation` is empty on most quests, so linked places count as where a quest goes."""
    start = [part.strip() for part in fields.get("startLocation", "").split(",")]
    linked = [link for link in document.links if link in places]
    return tuple(dict.fromkeys(place for place in (*start, *linked) if place))


def _with_named_places(
    quests: Iterable[Quest], places: frozenset[str], aliases: Iterable[Alias]
) -> tuple[Quest, ...]:
    """Places without a page ("Honami") are never linked, so also read the quest's own card."""
    canonical = {place: place for place in places}
    for alias in aliases:
        if alias.kind == AliasKind.INFERRED:
            canonical.setdefault(alias.alias, alias.target)
    pattern = _mention_pattern(canonical)
    return tuple(
        replace(
            quest,
            locations=tuple(
                dict.fromkeys(
                    (*quest.locations, *(canonical[m] for m in pattern.findall(_card_text(quest))))
                )
            ),
        )
        for quest in quests
    )


def _is_playable(quest: Quest) -> bool:
    """Overview pages ("Chapter II", "Main Quest") share the category but are not quests."""
    return bool(quest.fields.get("chapter") or quest.steps or quest.narration)


def _card_text(quest: Quest) -> str:
    # Dialogue is left out on purpose: characters mention places they are not in.
    parts = (quest.description or "", quest.summary or "", *quest.steps, *quest.narration)
    return "\n".join(parts)


def quests_in_place(knowledge: KnowledgeBase, name: str) -> list[Quest]:
    """Resolve a place name through aliases, then match quests anywhere inside that place."""
    wanted = name.casefold()
    roots = {alias.target for alias in knowledge.aliases if alias.alias.casefold() == wanted}
    children: dict[str, list[str]] = defaultdict(list)
    names: dict[str, str] = {}
    for edge in knowledge.locations:
        children[edge.parent].append(edge.child)
        names[edge.child.casefold()] = edge.child
        names[edge.parent.casefold()] = edge.parent
    if wanted in names:
        roots.add(names[wanted])
    inside = set(roots)
    for root in roots:
        inside.update(location_chain(root, children))
    return [quest for quest in knowledge.quests if inside.intersection(quest.locations)]


def build_quest(document: CanonicalDocument, places: frozenset[str] = frozenset()) -> Quest:
    narration: dict[str, None] = {}
    speakers: Counter[str] = Counter()
    description = None
    for block in document.blocks:
        if block.title == "Quest Description":
            description = block.text
        for turn in block.turns:
            if turn.kind is TurnKind.NARRATION and turn.depth == 0:
                narration.setdefault(turn.text, None)
            elif turn.speaker:
                speakers[turn.speaker] += 1
    fields = _merged_fields(document)
    steps = _section_text(document, "Steps") or ""
    return Quest(
        page_id=document.page_id,
        title=document.title,
        fields=fields,
        description=description or fields.get("description"),
        summary=_section_text(document, "Summary"),
        steps=tuple(line.removeprefix("- ") for line in steps.split("\n") if line),
        narration=tuple(narration),
        speakers=tuple(name for name, _ in speakers.most_common(MAX_SPEAKERS)),
        locations=_quest_locations(document, fields, places),
    )


def _mention_pattern(names: Iterable[str]) -> re.Pattern[str]:
    """Longest names first so "Black Shores Archipelago" wins over "Black Shores"."""
    usable = {name for name in names if len(name) >= MIN_MENTION_LENGTH}
    if not usable:
        return re.compile(r"(?!)")
    ordered = sorted(usable, key=lambda name: (-len(name), name))
    return re.compile(r"(?<!\w)(?:" + "|".join(map(re.escape, ordered)) + r")(?!\w)")


def enrich_chunks(chunks: Sequence[Chunk], knowledge: KnowledgeBase) -> list[Chunk]:
    """Add the KNW-003 metadata; only trusted aliases count, inferred ones wait for eval."""
    if not knowledge.entities:
        return list(chunks)
    canonical = {
        entity.title: entity.title for entity in knowledge.entities if has_corpus_text(entity)
    }
    known = frozenset(canonical)
    for alias in knowledge.aliases:
        if alias.confidence == "high" and alias.target in known:
            canonical.setdefault(alias.alias, alias.target)
    pattern = _mention_pattern(canonical)
    by_page = {entity.page_id: entity for entity in knowledge.entities}
    return [_enriched(chunk, by_page.get(chunk.page_id), pattern, canonical) for chunk in chunks]


def _enriched(
    chunk: Chunk, entity: Entity | None, pattern: re.Pattern[str], canonical: Mapping[str, str]
) -> Chunk:
    mentions = dict.fromkeys(canonical[match] for match in pattern.findall(chunk.text))
    own = chunk.title.split("/")[0]
    entities = dict.fromkeys([own, *mentions])
    if entity is None:
        return replace(chunk, entities=tuple(entities))
    return replace(
        chunk, entities=tuple(entities), nation=entity.nation, game_version=entity.game_version
    )


def knowledge_counts(knowledge: KnowledgeBase) -> dict[str, int]:
    return {
        "entities": len(knowledge.entities),
        "aliases": len(knowledge.aliases),
        "glossary": len(knowledge.glossary),
        "quests": len(knowledge.quests),
        "location_edges": len(knowledge.locations),
    }


def _structured_entities(
    structured: Mapping[int, StructuredPage],
    states: Mapping[int, PageState],
    edges: Iterable[LocationEdge],
    nations: frozenset[str],
) -> list[Entity]:
    parents = _parents_of(edges)
    entities = []
    for page_id, page in sorted(structured.items()):
        state = states.get(page_id)
        if state is None or not page.infoboxes:
            continue
        fields: dict[str, str] = {}
        for box in page.infoboxes:
            for key, value in box.items():
                fields.setdefault(key, value)
        nation, nation_source = _infer_nation(state.title, fields, parents, nations)
        version = _version_of(state)
        entities.append(
            Entity(
                page_id,
                state.title,
                STRUCTURED_ONLY,
                fields,
                nation,
                nation_source,
                version,
                "category" if version else None,
            )
        )
    return entities


def _structured_aliases(
    structured: Mapping[int, StructuredPage], states: Mapping[int, PageState]
) -> Iterator[Alias]:
    for page_id, page in sorted(structured.items()):
        state = states.get(page_id)
        if state is None or not page.infoboxes:
            continue
        yield from (Alias(t, state.title, AliasKind.REDIRECT, "high") for t in page.redirects)
        yield from (Alias(t, state.title, AliasKind.RENAME, "high") for t in state.aliases)


def build_knowledge(
    documents: Sequence[CanonicalDocument],
    states: Mapping[int, PageState],
    structured: Mapping[int, StructuredPage] | None = None,
) -> KnowledgeBase:
    """Locations use every known page, so places outside the text tiers still anchor the graph."""
    edges = build_location_edges(states.values())
    places = _place_names(edges)
    wiki_wide = structured or {}
    aliases = (*build_aliases(documents, states, edges), *_structured_aliases(wiki_wide, states))
    built = (build_quest(d, places) for d in documents if d.family in QUEST_FAMILIES)
    quests = tuple(quest for quest in built if _is_playable(quest))
    return KnowledgeBase(
        entities=(
            *build_entities(documents, states, edges),
            *_structured_entities(wiki_wide, states, edges, _known_nations(documents)),
        ),
        aliases=aliases,
        glossary=tuple(build_glossary(documents)),
        quests=_with_named_places(quests, places, aliases),
        locations=tuple(edges),
    )
