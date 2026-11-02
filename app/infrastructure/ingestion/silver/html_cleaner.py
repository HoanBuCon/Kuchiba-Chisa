"""Clean rendered Fandom HTML into a CanonicalDocument with lxml (ING-003, ING-012)."""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field, replace

import lxml.html
from lxml import etree
from lxml.html import HtmlElement

from app.domain.ingestion.documents import (
    Block,
    BlockKind,
    CanonicalDocument,
    DialogueTurn,
    GlossaryEntry,
    TurnKind,
)
from app.domain.ingestion.text_normalization import normalize_text
from app.domain.interfaces.silver import CleaningError
from app.domain.interfaces.wiki_ingestion import ParsedPage
from app.infrastructure.ingestion.silver.rules import CleaningRules

HEADINGS = {"h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}
LINE_BREAKING = {"p", "div", "li", "tr", "dd", "dt", "dl", "ul", "ol", "table", "blockquote"}
LINE_ENDING = {"br", "hr"}
NESTED_STRUCTURE = (
    './/table|.//div[contains(@class, "wds-tabber")]|.//div[contains(@class, "dialogue")]'
)
LIST_TAGS = {"ul", "ol", "dl"}
INLINE_TAGS = {
    "a",
    "b",
    "i",
    "em",
    "strong",
    "span",
    "small",
    "sup",
    "sub",
    "u",
    "s",
    "abbr",
    "code",
}
EDIT_BRACKETS = re.compile(r"\[\s*\]")
NON_ARTICLE_LINK = re.compile(r"^(File|Category|Template|Special|User|Module|Media):")


def _classes(element: HtmlElement) -> set[str]:
    return set((element.get("class") or "").split())


def _has_class(element: HtmlElement, name: str) -> bool:
    return name in _classes(element)


def _first(element: HtmlElement, class_name: str) -> HtmlElement | None:
    found = element.xpath(
        f'.//*[contains(concat(" ", normalize-space(@class), " "), " {class_name} ")]'
    )
    return found[0] if found else None


def extract_text(element: HtmlElement, *, skip_tags: frozenset[str] = frozenset()) -> str:
    """Visible text with line breaks where the browser would break lines."""
    parts: list[str] = []
    _collect_text(element, skip_tags, parts)
    return normalize_text("".join(parts))


def _collect_text(node: HtmlElement, skip_tags: frozenset[str], parts: list[str]) -> None:
    if node.tag == "rp":
        return
    opening, closing = _text_boundaries(node.tag)
    parts.append(opening)
    if node.text:
        parts.append(node.text)
    for child in node:
        if isinstance(child.tag, str) and child.tag not in skip_tags:
            _collect_text(child, skip_tags, parts)
        if child.tail:
            parts.append(child.tail)
    parts.append(closing)


def _text_boundaries(tag: str) -> tuple[str, str]:
    # Ruby glosses carry meaning ("gourds" read as "Terminals"), so keep both readable.
    if tag == "rt":
        return " (", ")"
    # A line break ends one line; block elements also separate paragraphs.
    if tag in LINE_ENDING:
        return "\n", ""
    return ("\n", "\n") if tag in LINE_BREAKING else ("", "")


def _remove(element: HtmlElement) -> None:
    # drop_tree keeps the tail text, which belongs to the parent's flow.
    element.drop_tree()


@dataclass
class _Context:
    rules: CleaningRules
    removed: Counter[str] = field(default_factory=Counter)
    glossary: dict[str, str] = field(default_factory=dict)
    links: dict[str, None] = field(default_factory=dict)

    def discard(self, element: HtmlElement, reason: str) -> None:
        self.removed[reason] += len(element.text_content())
        _remove(element)


class HtmlCleaner:
    def __init__(self, rules: CleaningRules) -> None:
        self._rules = rules

    @property
    def version(self) -> str:
        return f"{self._rules.cleaner_version}+{self._rules.config_hash}"

    def clean(self, page: ParsedPage, family: str | None) -> CanonicalDocument:
        context = _Context(self._rules)
        try:
            body = _body(lxml.html.fromstring(page.html or "<div></div>"))
        except etree.ParserError as error:
            raise CleaningError(f"page {page.page_id}: unparseable HTML") from error
        _resolve_tooltips(body, context)
        _drop_noise(body, context)
        _drop_generated_tables(body, context)
        dom_infoboxes = _take_infoboxes(body, context)
        _wrap_inline_runs(body)
        blocks = tuple(self._blocks(body, context))
        return CanonicalDocument(
            page_id=page.page_id,
            title=page.title,
            revid=page.revid,
            family=family,
            cleaner_version=self.version,
            blocks=blocks,
            infoboxes=_pageprops_infoboxes(page.properties) or dom_infoboxes,
            glossary=tuple(GlossaryEntry(t, d) for t, d in context.glossary.items()),
            links=tuple(context.links),
            removed=dict(context.removed),
        )

    def _blocks(self, body: HtmlElement, context: _Context) -> Iterator[Block]:
        path: list[tuple[int, str]] = []
        for element in list(body):
            if not isinstance(element.tag, str):
                continue
            if element.tag in HEADINGS:
                path = _push_heading(path, HEADINGS[element.tag], element)
                continue
            section = tuple(name for _, name in path)
            if any(self._rules.skip_sections.search(name) for name in section):
                context.discard(element, "skipped_section")
                continue
            _collect_links(element, context)
            for block in _element_blocks(element, section, self._rules):
                cleaned = _without_boilerplate(block, self._rules, context)
                if cleaned is not None:
                    yield cleaned


def _body(root: HtmlElement) -> HtmlElement:
    found = root.xpath(
        '//div[contains(concat(" ", normalize-space(@class), " "), " mw-parser-output ")]'
    )
    return found[0] if found else root


def _wrap_inline_runs(body: HtmlElement) -> None:
    """Lead sentences are bare text and inline tags under the body; wrap each run in a paragraph."""
    run: HtmlElement | None = None
    if body.text and body.text.strip():
        run = body.makeelement("p")
        run.text, body.text = body.text, None
        body.insert(0, run)
    for child in list(body):
        if not isinstance(child.tag, str) or child is run:
            continue
        if child.tag in INLINE_TAGS:
            if run is None:
                run = body.makeelement("p")
                child.addprevious(run)
            run.append(child)
            continue
        run = None
        if child.tail and child.tail.strip():
            run = body.makeelement("p")
            run.text, child.tail = child.tail, None
            child.addnext(run)


def _push_heading(
    path: list[tuple[int, str]], level: int, heading: HtmlElement
) -> list[tuple[int, str]]:
    name = EDIT_BRACKETS.sub("", extract_text(heading)).strip()
    return [entry for entry in path if entry[0] < level] + [(level, name)]


def _take_infoboxes(body: HtmlElement, context: _Context) -> tuple[dict, ...]:
    """Fallback structured data from the DOM, used only when pageprops has none."""
    boxes = []
    for aside in body.xpath('.//aside[contains(@class, "portable-infobox")]'):
        fields = {
            item.get("data-source"): extract_text(value)
            for item in aside.xpath('.//*[contains(@class, "pi-data")][@data-source]')
            if (value := _first(item, "pi-data-value")) is not None
        }
        if fields:
            boxes.append(fields)
        context.discard(aside, "infobox")
    return tuple(boxes)


def _pageprops_infoboxes(properties: dict[str, str]) -> tuple[dict, ...]:
    """Flatten PortableInfobox JSON to {source: text}; values are HTML snippets."""
    try:
        raw = json.loads(properties.get("infoboxes") or "[]")
    except json.JSONDecodeError:
        return ()
    return tuple(box for box in (_flatten_infobox(item) for item in raw) if box)


def _flatten_infobox(infobox: dict) -> dict[str, str]:
    fields: dict[str, str] = {}
    for item_type, data in _infobox_items(infobox.get("data", [])):
        source, value = data.get("source"), data.get("value")
        if item_type in {"data", "title"} and source and isinstance(value, str) and value.strip():
            fields[source] = _infobox_value(value)
    return fields


def _infobox_value(html: str) -> str:
    fragment = lxml.html.fromstring(f"<div>{html}</div>")
    # Citations and tooltip bodies are not part of the field's value.
    hidden = (
        './/sup[contains(@class, "reference")]|.//*[contains(@class, "mw-collapsible-content")]'
    )
    for node in fragment.xpath(hidden):
        _remove(node)
    return extract_text(fragment)


def _infobox_items(items: list) -> Iterator[tuple[str, dict]]:
    """Groups, panels and sections nest items; yield (type, data) of each leaf."""
    for item in items:
        data = item.get("data") if isinstance(item, dict) else None
        if not isinstance(data, dict):
            continue
        nested = data.get("value")
        if item.get("type") in {"group", "panel", "section"} and isinstance(nested, list):
            yield from _infobox_items(nested)
        else:
            yield item.get("type", ""), data


def _resolve_tooltips(body: HtmlElement, context: _Context) -> None:
    """Keep the visible toggle text inline; move real definitions to the glossary."""
    for wrapper in body.xpath('.//*[contains(@class, "custom-tt-wrapper")]'):
        toggle = _first(wrapper, "mw-collapsible-toggle")
        content = _first(wrapper, "mw-collapsible-content")
        visible = extract_text(toggle) if toggle is not None else ""
        if content is not None:
            _record_glossary(content, visible, context)
        replacement = lxml.html.fromstring("<span></span>")
        replacement.text = visible
        replacement.tail = wrapper.tail
        wrapper.getparent().replace(wrapper, replacement)


def _record_glossary(content: HtmlElement, visible: str, context: _Context) -> None:
    header = _first(content, "wuwa-extra-effect-header")
    definition_node = _first(content, "wuwa-extra-effect-content")
    term = extract_text(header) if header is not None else visible
    definition = extract_text(definition_node if definition_node is not None else content)
    if context.rules.variant_tooltips.search(definition):
        return
    if term and definition and definition != term:
        context.glossary.setdefault(term, definition)


def _drop_noise(body: HtmlElement, context: _Context) -> None:
    rules = context.rules
    for element in list(body.iter()):
        if not isinstance(element.tag, str) or element.getparent() is None:
            continue
        reason = _drop_reason(element, rules)
        if reason is not None and _attached(element, body):
            context.discard(element, reason)


def _drop_reason(element: HtmlElement, rules: CleaningRules) -> str | None:
    if element.tag in rules.drop_tags:
        return rules.drop_tags[element.tag]
    # Broken embeds are typed "mw:Error mw:File", so match each token.
    for token in (element.get("typeof") or "").split():
        if token in rules.drop_typeof:
            return rules.drop_typeof[token]
    for name in _classes(element):
        if name in rules.drop_classes:
            return rules.drop_classes[name]
    hidden = _has_class(element, "hidden") and element.tag not in rules.keep_hidden_tags
    return "hidden_variant" if hidden else None


def _drop_generated_tables(body: HtmlElement, context: _Context) -> None:
    """DPL listings repeat other pages' data (ING-003); only their links survive, as relations."""
    for intro in body.xpath(".//p"):
        if not context.rules.generated_table_intro.search(extract_text(intro)):
            continue
        table = intro.getnext()
        if table is not None and table.tag == "table":
            _collect_links(table, context)
            context.discard(table, "generated_table")
        context.discard(intro, "generated_table")


def _attached(element: HtmlElement, body: HtmlElement) -> bool:
    """True while no ancestor has already been dropped."""
    node = element
    while node is not None and node is not body:
        node = node.getparent()
    return node is body


def _collect_links(element: HtmlElement, context: _Context) -> None:
    for title in element.xpath(".//a/@title"):
        if not NON_ARTICLE_LINK.match(title):
            context.links.setdefault(title, None)


def _element_blocks(
    element: HtmlElement, section: tuple[str, ...], rules: CleaningRules
) -> Iterator[Block]:
    if _has_class(element, "wds-tabber"):
        yield from _tabber_blocks(element, section, rules)
    elif _has_class(element, "dialogue"):
        yield from _dialogue_blocks(element, section)
    elif _has_class(element, "description-wrapper") or element.xpath(
        './div[contains(@class, "description-wrapper")]'
    ):
        yield from _description_block(element, section)
    elif element.tag == "div" and element.xpath(NESTED_STRUCTURE):
        yield from _container_blocks(element, section, rules)
    elif element.xpath('.//div[contains(@class, "dialogue")]'):
        yield from _dialogue_blocks(element, section)
    elif element.tag == "table":
        yield from _table_blocks(element, section, rules)
    elif element.tag in LIST_TAGS:
        yield from _list_block(element, section)
    elif element.tag == "blockquote" or _has_class(element, "pull-quote"):
        yield from _text_block(BlockKind.QUOTE, element, section)
    else:
        yield from _text_block(BlockKind.PROSE, element, section)


def _container_blocks(
    container: HtmlElement, section: tuple[str, ...], rules: CleaningRules
) -> Iterator[Block]:
    """Wrapper divs must not flatten the tables or dialogue inside them into glued prose."""
    _wrap_inline_runs(container)
    for child in container:
        if isinstance(child.tag, str):
            yield from _element_blocks(child, section, rules)


def _tabber_blocks(
    tabber: HtmlElement, section: tuple[str, ...], rules: CleaningRules
) -> Iterator[Block]:
    """Tabs such as Rover's Male/Female voicelines become variants instead of merged text (E5)."""
    labels = [
        extract_text(label)
        for label in tabber.xpath('./ul//*[contains(@class, "wds-tabs__tab-label")]')
    ]
    contents = tabber.xpath('./div[contains(@class, "wds-tab__content")]')
    for label, content in zip(labels, contents, strict=False):
        _wrap_inline_runs(content)
        for child in content:
            if not isinstance(child.tag, str):
                continue
            for block in _element_blocks(child, section, rules):
                variant = "; ".join(filter(None, (label, block.variant)))
                yield replace(block, variant=variant or None)


def _text_block(kind: BlockKind, element: HtmlElement, section: tuple[str, ...]) -> Iterator[Block]:
    text = extract_text(element)
    if text:
        yield Block(kind, section, text)


def _list_block(element: HtmlElement, section: tuple[str, ...]) -> Iterator[Block]:
    items = [extract_text(item) for item in element.xpath("./li|./dt|./dd")]
    lines = [f"- {' '.join(item.split())}" for item in items if item]
    if lines:
        yield Block(BlockKind.LIST, section, "\n".join(lines))


def _description_block(element: HtmlElement, section: tuple[str, ...]) -> Iterator[Block]:
    wrapper = (
        element
        if _has_class(element, "description-wrapper")
        else _first(element, "description-wrapper")
    )
    element = wrapper if wrapper is not None else element
    title_node = _first(element, "description-title")
    content = _first(element, "description-content")
    text = extract_text(content if content is not None else element)
    if text:
        yield Block(
            BlockKind.PROSE,
            section,
            text,
            title=extract_text(title_node) if title_node is not None else None,
        )


def _table_blocks(
    table: HtmlElement, section: tuple[str, ...], rules: CleaningRules
) -> Iterator[Block]:
    rows = [row for row in table.xpath(".//tr") if row.xpath("./th|./td")]
    facts: list[str] = []
    pending_title: str | None = None
    generic: list[HtmlElement] = []
    for position, row in enumerate(rows):
        headers, cells = row.xpath("./th"), row.xpath("./td")
        if headers and not cells and _single_cell(rows, position + 1):
            # Story tables put the title and its unlock condition in one header row.
            pending_title = "\n".join(filter(None, map(extract_text, headers))) or pending_title
        elif len(cells) == 1 and len(headers) <= 1:
            title = extract_text(headers[0]) if headers else pending_title
            yield from _titled_cell(title, cells[0], section, rules, facts)
            pending_title = None
        else:
            generic.append(row)
    if facts:
        yield Block(BlockKind.FACTS, section, "\n".join(facts))
    yield from _generic_table(generic, section)


def _single_cell(rows: list[HtmlElement], position: int) -> bool:
    return (
        position < len(rows)
        and not rows[position].xpath("./th")
        and len(rows[position].xpath("./td")) == 1
    )


def _titled_cell(
    title: str | None,
    cell: HtmlElement,
    section: tuple[str, ...],
    rules: CleaningRules,
    facts: list[str],
) -> Iterator[Block]:
    text = extract_text(cell)
    if not text:
        return
    heading, _, variant = (title or "").partition("\n")
    if len(text) < rules.story_min_chars and heading:
        facts.append(f"{heading}: {text}")
        return
    yield Block(
        BlockKind.STORY, section, text, title=heading or None, variant=variant.strip() or None
    )


def _generic_table(rows: list[HtmlElement], section: tuple[str, ...]) -> Iterator[Block]:
    """Repeat the header on every row so each line stands alone after chunking."""
    if not rows:
        return
    header = [extract_text(cell) for cell in rows[0].xpath("./th")]
    body_rows = rows[1:] if header and not rows[0].xpath("./td") else rows
    lines = []
    for row in body_rows:
        values = [extract_text(cell) for cell in row.xpath("./th|./td")]
        pairs = (
            zip(header, values, strict=False)
            if len(header) == len(values)
            else (("", v) for v in values)
        )
        line = "; ".join(f"{k}: {v}" if k else v for k, v in pairs if v)
        if line:
            lines.append(line)
    if lines:
        yield Block(BlockKind.TABLE, section, "\n".join(lines))


def _dialogue_blocks(element: HtmlElement, section: tuple[str, ...]) -> Iterator[Block]:
    containers = (
        [element]
        if _has_class(element, "dialogue")
        else element.xpath('.//div[contains(@class, "dialogue")]')
    )
    turns = tuple(turn for container in containers for turn in _dialogue_turns(container, depth=0))
    if turns:
        yield Block(BlockKind.DIALOGUE, section, "\n".join(t.render() for t in turns), turns=turns)


def _dialogue_turns(container: HtmlElement, depth: int) -> Iterator[DialogueTurn]:
    for dl in container.xpath("./dl"):
        for item in dl:
            if item.tag == "dt":
                text = extract_text(item)
                if text:
                    yield DialogueTurn(TurnKind.NARRATION, text, depth=depth)
            elif item.tag == "dd":
                yield from _dialogue_item(item, depth)


def _dialogue_item(item: HtmlElement, depth: int) -> Iterator[DialogueTurn]:
    own_text = extract_text(item, skip_tags=frozenset({"dl"}))
    nested = item.xpath("./dl")
    if nested:
        if own_text:
            yield DialogueTurn(TurnKind.CHOICE, own_text, depth=depth)
        yield from _dialogue_turns(item, depth + 1)
        return
    if own_text:
        yield _line(item, own_text, depth)


def _line(item: HtmlElement, text: str, depth: int) -> DialogueTurn:
    bold = item.xpath("./b")
    label = extract_text(bold[0]) if bold else ""
    if label.endswith(":") and text.startswith(label):
        return DialogueTurn(
            TurnKind.LINE, text[len(label) :].strip(), speaker=label[:-1].strip(), depth=depth
        )
    return DialogueTurn(TurnKind.LINE, text, depth=depth)


def _without_boilerplate(block: Block, rules: CleaningRules, context: _Context) -> Block | None:
    text = _repaired(block.text, rules, context)
    if block.kind is not BlockKind.DIALOGUE:
        kept = [line for line in text.split("\n") if not rules.boilerplate_lines.search(line)]
        context.removed["boilerplate"] += len(text) - sum(len(line) for line in kept)
        text = normalize_text("\n".join(kept))
    if not text:
        return None
    return replace(block, text=text)


def _repaired(text: str, rules: CleaningRules, context: _Context) -> str:
    for pattern, replacement in rules.repairs:
        text, count = pattern.subn(replacement, text)
        context.removed["repaired_markup"] += count
    return text
