"""Silver HTML cleaner on markup shaped like the 2026-11 Fandom render (ING-003, ING-012, E3-E5)."""

import json
from datetime import UTC, datetime

import pytest

from app.domain.ingestion.documents import BlockKind, TurnKind
from app.domain.interfaces.wiki_ingestion import ParsedPage
from app.infrastructure.ingestion.silver.html_cleaner import HtmlCleaner
from app.infrastructure.ingestion.silver.rules import load_cleaning_rules

RULES = load_cleaning_rules()
TOOLTIP = (
    '<span class="custom-tt-wrapper mw-collapsible">'
    '<span class="mw-collapsible-toggle">{visible}</span>'
    '<span class="mw-collapsible-content"><span class="wuwa-extra-effect-header">{visible}</span>'
    '<span class="wuwa-extra-effect-content">{definition}</span></span></span>'
)
GENDER = (
    '<span>(‍<span class="custom-tt-wrapper"><span class="mw-collapsible-toggle">he</span>'
    '<span class="mw-collapsible-content">Text for male Rover</span></span>‍/'
    '<span class="custom-tt-wrapper"><span class="mw-collapsible-toggle">she</span>'
    '<span class="mw-collapsible-content">Text for female Rover</span></span>‍)</span>'
)
NAME = (
    '(‍<span class="custom-tt-wrapper"><span class="mw-collapsible-toggle">Rover</span>'
    '<span class="mw-collapsible-content">The player\'s chosen name for Rover</span></span>‍)'
)


def _clean(body: str, family: str | None = "lore", properties: dict | None = None):
    page = ParsedPage(
        page_id=1,
        title="Page",
        revid=2,
        html=f'<div class="mw-parser-output">{body}</div>',
        categories=(),
        templates=(),
        sections=(),
        properties=properties or {},
        url="u",
        license="CC BY-SA",
        fetched_at=datetime(2026, 11, 2, tzinfo=UTC),
    )
    return HtmlCleaner(RULES).clean(page, family)


def test_lead_sentence_split_by_inline_tags_stays_one_paragraph() -> None:
    doc = _clean(
        '<b>Chisa</b> is a <a title="Resonator">Resonator</a> from '
        '<a title="Ashinohara">Ashinohara</a>.'
    )

    assert [(b.kind, b.text) for b in doc.blocks] == [
        (BlockKind.PROSE, "Chisa is a Resonator from Ashinohara.")
    ]
    assert doc.links == ("Resonator", "Ashinohara")


def test_sections_are_tracked_and_non_lore_sections_skipped() -> None:
    doc = _clean(
        '<h2><span class="mw-headline">Story</span><span class="mw-editsection">[edit]</span></h2>'
        "<p>Kept.</p>"
        "<h3>Childhood</h3><p>Nested.</p><h2>Gallery</h2><p>Dropped.</p><h2>Change History</h2>"
        "<p>Gone.</p>"
    )

    assert [(b.section, b.text) for b in doc.blocks] == [
        (("Story",), "Kept."),
        (("Story", "Childhood"), "Nested."),
    ]
    assert doc.removed["skipped_section"] > 0


def test_ui_media_and_navboxes_are_removed_with_reasons() -> None:
    doc = _clean(
        '<p>Text<sup class="reference">[1]</sup> here.</p><table class="navbox"><tr><td>Nav</td>'
        "</tr></table>"
        '<span class="audio-button"><a>Media:X.ogg</a></span><div class="toc">Contents</div>'
    )

    assert [b.text for b in doc.blocks] == ["Text here."]
    assert {"references", "ui", "media"} <= doc.removed.keys()


def test_tooltips_feed_the_glossary_and_rendering_hints_do_not() -> None:
    tooltip = TOOLTIP.format(visible="Ashinohara", definition="A nation.")
    doc = _clean(f"<p>Born in {tooltip}. Hi {NAME}, {GENDER} said.</p>")

    assert doc.blocks[0].text == "Born in Ashinohara. Hi Rover, (he/she) said."
    assert [(g.term, g.definition) for g in doc.glossary] == [("Ashinohara", "A nation.")]


def test_dialogue_keeps_speakers_narration_and_choice_branches() -> None:
    doc = _clean(
        '<h2>Dialogue</h2><div class="dialogue"><dl><dt>Head to the city</dt>'
        '<dd><span class="audio-button">a</span> <b>Ciaccona:</b> A song.</dd>'
        "<dd>What about it?<dl><dd><b>Rover:</b> Tell me more.</dd></dl></dd></dl></div>"
    )

    [block] = doc.blocks
    assert block.kind is BlockKind.DIALOGUE
    assert [(t.kind, t.speaker, t.text, t.depth) for t in block.turns] == [
        (TurnKind.NARRATION, None, "Head to the city", 0),
        (TurnKind.LINE, "Ciaccona", "A song.", 0),
        (TurnKind.CHOICE, None, "What about it?", 0),
        (TurnKind.LINE, "Rover", "Tell me more.", 1),
    ]
    assert block.text.splitlines()[-1] == "  Rover: Tell me more."


def test_voiceline_rows_keep_desktop_title_and_unlock_condition() -> None:
    doc = _clean(
        '<h2>About Voicelines</h2><table class="wikitable"><tr class="hidden"><th>Title</th>'
        "<th>Details</th></tr>"
        '<tr><th class="mobile-only">Thoughts: II</th></tr>'
        '<tr><th class="hidden">Thoughts: II<hr/><div><small><i>Intimacy Lv. 1</i></small></div>'
        "</th>"
        '<td><span class="audio-button hidden">Media:x.ogg</span>'
        "When I was little, I'd sit on the porch listening to cicadas "
        "while cutting colored paper into goldfish."
        '</td></tr><tr><th class="hidden">Greeting</th><td>Hello.</td></tr></table>'
    )

    story, facts = doc.blocks
    assert (story.kind, story.title, story.variant) == (
        BlockKind.STORY,
        "Thoughts: II",
        "Intimacy Lv. 1",
    )
    assert story.text.startswith("When I was little")
    assert (facts.kind, facts.text) == (BlockKind.FACTS, "Greeting: Hello.")


def test_story_tables_use_the_multi_header_row_as_title() -> None:
    doc = _clean(
        '<table class="article-table"><tr><th>The Long Rainy Season</th><th>'
        "<small>Unlocks at Intimacy Lv. 2</small></th></tr>"
        '<tr><td colspan="2"><p>Her fifteenth summer smelled of pencil shavings.<br/>'
        "<br/>Second paragraph of the story.</p></td></tr></table>"
    )

    [story] = doc.blocks
    assert (story.title, story.variant) == ("The Long Rainy Season", "Unlocks at Intimacy Lv. 2")
    assert (
        story.text
        == "Her fifteenth summer smelled of pencil shavings.\n\nSecond paragraph of the story."
    )


def test_generic_tables_repeat_the_header_on_each_row() -> None:
    doc = _clean(
        "<table><tr><th>Event</th><th>Version</th></tr><tr><td>Cubie Wars</td><td>3.4</td></tr>"
        "<tr><td>Artisan's Search</td><td>3.6</td></tr></table>"
    )

    assert (
        doc.blocks[0].text
        == "Event: Cubie Wars; Version: 3.4\nEvent: Artisan's Search; Version: 3.6"
    )


def test_tabbers_become_variants_instead_of_merged_text() -> None:
    doc = _clean(
        '<div class="wds-tabber"><ul class="wds-tabs"><li>'
        '<div class="wds-tabs__tab-label">Male</div></li>'
        '<li><div class="wds-tabs__tab-label">Female</div></li></ul>'
        '<div class="wds-tab__content"><p>His line.</p></div><div class="wds-tab__content">'
        "<p>Her line.</p></div></div>"
    )

    assert [(b.text, b.variant) for b in doc.blocks] == [
        ("His line.", "Male"),
        ("Her line.", "Female"),
    ]


def test_lists_render_one_item_per_line() -> None:
    doc = _clean("<h2>Steps</h2><ol><li>Return to the city</li><li>Find <b>Ciaccona</b></li></ol>")

    assert doc.blocks[0].text == "- Return to the city\n- Find Ciaccona"


def test_boilerplate_lines_and_broken_wikitext_are_cleaned() -> None:
    doc = _clean(
        "<p>Disclaimer: This is a compilation of Skip summary and may not reflect the story.</p>"
        "<p>See [[Cubie Wars|]] and the False Sovereign|figure]] ahead}}.</p>"
    )

    assert [b.text for b in doc.blocks] == ["See Cubie Wars and the figure ahead."]
    assert doc.removed["repaired_markup"] == 3


def test_description_wrapper_keeps_its_title() -> None:
    doc = _clean(
        '<dd><div class="description-wrapper"><div class="description-title">'
        "<b>Quest Description</b></div>"
        '<hr class="description-separator"/>'
        '<div class="description-content">A swordsman arrives.</div></div></dd>'
    )

    assert [(b.title, b.text) for b in doc.blocks] == [
        ("Quest Description", "A swordsman arrives.")
    ]


def test_pageprops_infobox_is_flattened_and_preferred_over_the_dom() -> None:
    infobox = [
        {
            "data": [
                {"type": "title", "data": {"value": "Chisa", "source": "name"}},
                {"type": "image", "data": [{"url": "x"}]},
                {
                    "type": "group",
                    "data": {
                        "value": [
                            {
                                "type": "data",
                                "data": {
                                    "source": "voiceCN",
                                    "value": 'Zhang Qi<sup class="reference"><a>[1]</a></sup>',
                                },
                            },
                            {"type": "data", "data": {"source": "ally", "value": "A<br/>B"}},
                        ]
                    },
                },
            ]
        }
    ]
    dom = (
        '<aside class="portable-infobox"><div class="pi-data" data-source="name">'
        '<div class="pi-data-value">DOM</div></div></aside><p>Body.</p>'
    )

    doc = _clean(dom, properties={"infoboxes": json.dumps(infobox)})

    assert doc.infoboxes == ({"name": "Chisa", "voiceCN": "Zhang Qi", "ally": "A\nB"},)
    assert [b.text for b in doc.blocks] == ["Body."]


def test_dom_infobox_is_the_fallback() -> None:
    doc = _clean(
        '<aside class="portable-infobox"><div class="pi-data" data-source="age">'
        '<div class="pi-data-value">18<sup class="reference">[1]</sup></div></div></aside>'
    )

    assert doc.infoboxes == ({"age": "18"},)


@pytest.mark.parametrize("html", ["", "<div></div>", '<p class="mw-empty-elt"></p>'])
def test_empty_pages_yield_no_blocks(html: str) -> None:
    assert _clean(html).blocks == ()


def test_version_changes_with_the_config() -> None:
    assert HtmlCleaner(RULES).version == f"{RULES.cleaner_version}+{RULES.config_hash}"


def test_ruby_glosses_stay_readable_instead_of_gluing_words() -> None:
    doc = _clean("<p>Our <ruby>gourds<rp>(</rp><rt>Terminals</rt><rp>)</rp></ruby> are out.</p>")

    assert doc.blocks[0].text == "Our gourds (Terminals) are out."


def test_horizontal_rules_separate_lines() -> None:
    doc = _clean("<div><big><b>Field Report</b></big><hr/><b>No. 10826</b></div>")

    assert doc.blocks[0].text == "Field Report\nNo. 10826"


def test_tables_inside_wrapper_divs_stay_tables() -> None:
    doc = _clean(
        '<div class="mw-collapsible"><p>Rank table</p><table><tr><th>UL</th><th>EXP</th></tr>'
        "<tr><td>1</td><td>400</td></tr></table></div>"
    )

    assert [(b.kind, b.text) for b in doc.blocks] == [
        (BlockKind.PROSE, "Rank table"),
        (BlockKind.TABLE, "UL: 1; EXP: 400"),
    ]


def test_broken_file_embeds_leave_no_file_name() -> None:
    doc = _clean(
        '<p>See <span typeof="mw:Error mw:File"><a><span>File:Lily.png</span></a></span> here.</p>'
    )

    assert doc.blocks[0].text == "See here."


def test_dpl_listing_is_dropped_but_its_links_become_relations() -> None:
    doc = _clean(
        "<p>Intro stays.</p><p><b>1</b> Resonator matches the category selection:</p>"
        '<table><tr><th>Resonator</th></tr><tr><td><a title="Lily">Lily</a></td></tr></table>'
    )

    assert [b.text for b in doc.blocks] == ["Intro stays."]
    assert doc.links == ("Lily",)
    assert doc.removed["generated_table"] > 0


def test_game_client_tags_are_resolved() -> None:
    doc = _clean(
        "<p>The next 2 {Cus:Sap,S=stage P=stages SapTag=A} use "
        "{Cus:Ipt,Touch=Tap PC=Press Gamepad=Press}.</p>"
    )

    assert doc.blocks[0].text == "The next 2 stages use Tap."


def test_infobox_values_keep_tooltip_toggles_only() -> None:
    value = (
        '<span class="custom-tt-wrapper"><span class="mw-collapsible-toggle">Lord</span>'
        '<span class="mw-collapsible-content">Text for male Rover</span></span> Arbiter'
    )
    infobox = [{"data": [{"type": "data", "data": {"source": "title2", "value": value}}]}]

    doc = _clean("<p>Body.</p>", properties={"infoboxes": json.dumps(infobox)})

    assert doc.infoboxes == ({"title2": "Lord Arbiter"},)


def test_gendered_game_tags_and_attachment_markers_are_repaired() -> None:
    doc = _clean("<p>An army in {Male=him;Female=her}! [ATTACHMENT:Lemonblast.jpg]</p>")

    assert doc.blocks[0].text == "An army in him/her!"
