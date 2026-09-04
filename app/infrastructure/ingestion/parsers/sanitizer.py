"""
Wikitext Sanitizer — Raw wikitext cleaning via ordered regex operations.

Implements §3.2 Stage 1 (Sanitization) + Stage 4 (Wikitext→Markdown) +
Stage 5 (Boilerplate Removal) of the Architecture Document.

Operations are applied in a strict order to avoid regex interactions:
    1. Strip HTML comments <!-- ... -->
    2. Strip <ref> tags and content
    3. Strip <gallery> blocks
    4. Strip categories [[Category:...]]
    5. Strip interwiki links [[zh:...]], [[ja:...]]
    6. Strip magic words __NOTOC__, __NOEDITSECTION__
    7. Strip image-only lines (50px, 20px patterns)
    8. Normalize line endings (CRLF → LF)
    9. Collapse 3+ consecutive blank lines → 2

Design:
    - Pure functions, no state, no I/O.
    - All regexes pre-compiled at module level for performance (50K pages).
    - structlog for issue detection reporting.
"""

from __future__ import annotations
import json
import os
import re
import yaml
import mwparserfromhell
import structlog
from typing import Any, Dict, FrozenSet, List, Optional, Set, Tuple

logger = structlog.get_logger(__name__)

RULES_CONFIG_PATH = os.path.join(
    os.path.dirname(__file__), "..", "config", "pipeline_rules.yaml"
)

class RuleEngine:
    """Config-driven rule engine loading pipeline_rules.yaml for AST sanitization and Quality Gate."""
    def __init__(self, config_path: str = RULES_CONFIG_PATH):
        self.config_path = config_path
        self.strip_templates: Set[str] = set()
        self.unroll_rules: Dict[str, Dict[str, Any]] = {}
        self.quality_gate: Dict[str, Any] = {}
        self.stopwords: Set[str] = set()
        self.blacklist: Set[str] = set()
        self.unknown_templates: Dict[str, int] = {}
        self.load_config()

    def load_config(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
            except Exception as exc:
                logger.warning("failed_to_load_pipeline_rules_yaml", error=str(exc))
                data = {}
        else:
            data = {}

        self.strip_templates = set(t.lower() for t in data.get("templates", {}).get("strip", []))
        self.unroll_rules = {k.lower(): v for k, v in data.get("templates", {}).get("unroll", {}).items()}
        self.quality_gate = data.get("quality_gate", {
            "min_tokens": 15,
            "min_text_len": 20,
            "borderline_score_min": 0.5,
            "borderline_score_max": 0.7,
            "boilerplate_patterns": [
                r"is a note found during .* and is added to (?:its )?archives",
                r"for the complete properties and abilities of .*, see",
                r"description from the official website",
            ]
        })
        self.stopwords = set(s.lower() for s in data.get("entities", {}).get("stopwords", []))
        self.blacklist = set(b.lower() for b in data.get("entities", {}).get("blacklist", []))
        self.category_junk_patterns = [
            re.compile(p, re.IGNORECASE) for p in data.get("categories", {}).get("junk_patterns", [])
        ]
        self.category_blacklist = set(b.lower() for b in data.get("categories", {}).get("blacklist", []))

    def is_junk_category(self, category: str) -> bool:
        if not category:
            return True
        c_low = category.strip().lower()
        if c_low in self.category_blacklist:
            return True
        for pattern in self.category_junk_patterns:
            if pattern.search(category):
                return True
        return False

    def log_unknown_template(self, template_name: str):
        t_low = template_name.lower().strip()
        self.unknown_templates[t_low] = self.unknown_templates.get(t_low, 0) + 1
        logger.debug("unknown_template_detected", template=t_low)

_DEFAULT_RULE_ENGINE: Optional[RuleEngine] = None

def get_rule_engine() -> RuleEngine:
    global _DEFAULT_RULE_ENGINE
    if _DEFAULT_RULE_ENGINE is None:
        _DEFAULT_RULE_ENGINE = RuleEngine()
    return _DEFAULT_RULE_ENGINE

AST_TEMPLATE_BLOCKLIST: FrozenSet[str] = frozenset({
    "resonator tabs",
    "intro/resonator",
    "skill navbox",
    "nodes navbox",
    "quests and events",
    "featured",
    "resonator navbox",
    "reflist",
    "skill upgrade",
    "character ascensions and stats",
    "main",
    "change history",
    "other languages",
    "trophies",
    "resonator instructions",
    "forte table",
    "chain table",
    "tabber",
    "transclude",
    "infobox gallery",
    "trials by character",
    "character mentions",
    "stub",
    "stubs",
    "notice",
    "wip",
    "needs image",
    "cleanup",
    "expand",
    "disclaimer",
    "spoiler",
    "warning",
    "note",
})



# ─────────────────────────────────────────────────────────────
# Pre-compiled regex patterns (compiled once at import time)
# ─────────────────────────────────────────────────────────────

# Stage 1: HTML comments (potentially multi-line)
_RE_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)

# Stage 2: <ref> tags (self-closing and paired)
_RE_REF_SELF_CLOSING = re.compile(r"<ref\s*[^/>]*/>", re.IGNORECASE)
_RE_REF_PAIRED = re.compile(r"<ref[^>]*>.*?</ref>", re.DOTALL | re.IGNORECASE)

# Stage 3: <gallery> blocks
_RE_GALLERY = re.compile(r"<gallery[^>]*>.*?</gallery>", re.DOTALL | re.IGNORECASE)

# Stage 4: Categories [[Category:...]]
_RE_CATEGORY = re.compile(r"\[\[Category:[^\]]*\]\]", re.IGNORECASE)

# Stage 5: Interwiki links [[xx:...]] where xx is a 2-3 char language code
_RE_INTERWIKI = re.compile(r"\[\[[a-z]{2,3}:[^\]]*\]\]")

# Stage 5b: Bare interwiki links on their own line (e.g., "zh:星炬学院")
_RE_BARE_INTERWIKI = re.compile(r"^[a-z]{2,3}:\S+.*$", re.MULTILINE)

# Stage 6: Magic words
_RE_MAGIC_WORDS = re.compile(
    r"__(?:NOTOC|NOEDITSECTION|FORCETOC|TOC|NEWSECTIONLINK|"
    r"NONEWSECTIONLINK|NOGALLERY|HIDDENCAT|NOCONTENTCONVERT|"
    r"NOCC|NOTITLECONVERT|NOTC|INDEX|NOINDEX|STATICREDIRECT)__"
)

# Stage 7: Image-only lines (standalone image references like "50px" or "|50px")
_RE_IMAGE_LINE = re.compile(r"^\s*\|?\s*\d+px\s*$", re.MULTILINE)

# Stage 8: CRLF normalization
_RE_CRLF = re.compile(r"\r\n")
_RE_CR = re.compile(r"\r")

# Stage 9: Excessive blank lines (3+ consecutive → 2)
_RE_EXCESS_BLANK_LINES = re.compile(r"\n{3,}")

# Wikitext → Markdown conversion patterns (Stage 4 from §3.2)
_RE_BOLD_ITALIC = re.compile(r"'{5}(.+?)'{5}")  # '''''bold italic'''''
_RE_BOLD = re.compile(r"'{3}(.+?)'{3}")          # '''bold'''
_RE_ITALIC = re.compile(r"'{2}(.+?)'{2}")        # ''italic''
_RE_WIKILINK_DISPLAY = re.compile(r"\[\[[^\]|]+\|([^\]]+)\]\]")  # [[Page|Display]]
_RE_WIKILINK_SIMPLE = re.compile(r"\[\[([^\]|]+)\]\]")           # [[Page Name]]
_RE_HEADING = re.compile(r"^(=+)\s*(.+?)\s*=+\s*$", re.MULTILINE)
_RE_EXTERNAL_LINK = re.compile(r"\[https?://[^\s\]]+ ([^\]]+)\]")  # [url text]
_RE_EXTERNAL_LINK_BARE = re.compile(r"\[https?://[^\s\]]+\]")      # [url]

# Display-only templates with no text content or nested transclusions
_RE_DISPLAY_TEMPLATES = re.compile(
    r"\{\{(?:[^\}|]+\s+by\s+Category\s+(?:Table|List)|Files\s+by|Resonators\s+by|Quest\s+by|"
    r"Echoes\s+by|Weapons\s+by|Enemy\s+List|Item\s+List|Navbox[^\}|]*|Resonator Tabs|"
    r"Intro/Resonator|Skill Navbox|Nodes Navbox|Quests and Events|Featured|Resonator Navbox|"
    r"Reflist|Skill Upgrade|Character Ascensions and Stats|Main|Change History|Other Languages|"
    r"Trophies|Resonator Instructions|Forte Table|Chain Table|Tabber|Transclude|Trials by Character|"
    r"Character Mentions|Stub|Stubs|Notice|WIP|Needs Image|Cleanup|Expand|"
    r"Disclaimer|Spoiler|Warning|Note|Archive|Dialogue Start|Dialogue End|DIcon|sic|tx|color|"
    r"Reward|Exit|Play|Sound|Prompt|Option|Choice)[^}]*\}\}",
    re.IGNORECASE,
)

# MediaWiki Magic Words / Variables
_RE_PAGENAME = re.compile(r"\{\{(?:PAGE|FULLPAGE|BASEPAGE|SUBPAGE)NAME(?:\|[^\}]*)?\}\}", re.IGNORECASE)

# Inline formatting templates to convert to plain text
_RE_MC_TEMPLATE = re.compile(r"\{\{MC\|(?:m=([^|}]*)\|f=([^|}]*)|f=([^|}]*)\|m=([^|}]*))\}\}", re.IGNORECASE)
_RE_W_TEMPLATE = re.compile(r"\{\{w\|(?:[^|}]*\|)?([^}]+)\}\}", re.IGNORECASE)
_RE_LANG_TEMPLATE = re.compile(r"\{\{Lang\|[^|}]*\|([^}]+)\}\}", re.IGNORECASE)
_RE_RUBI_TEMPLATE = re.compile(r"\{\{Rubi\|([^|]+)\|[^}]*\}\}", re.IGNORECASE)

# Broken heading patterns (from startorch_academy.md — §3.1 #4)
_RE_BROKEN_HEADING = re.compile(
    r"^(#{1,6})\s*=+\s*'{0,3}(.+?)'{0,3}\s*=+\s*$",
    re.MULTILINE,
)

# Inline image references embedded in lists/text (e.g., "20px Chisa")
_RE_INLINE_IMAGE = re.compile(r"\d+px\s*")

# Residual template parameter lines (e.g., |mention1 = ...)
_RE_MENTION_LINE = re.compile(r"^\s*\|mention\d*\s*=.*$", re.MULTILINE)


# ─────────────────────────────────────────────────────────────
# Default boilerplate section blocklist
# ─────────────────────────────────────────────────────────────

DEFAULT_BOILERPLATE_SECTIONS: FrozenSet[str] = frozenset({
    "other languages",
    "references",
    "navigation",
    "external links",
    "change log",
    "patch history",
    "change history",
    "availability",
    "event convenes",
    "combat overview",
    "ascension material",
    "ascension materials",
    "ascension",
    "stat bonus",
    "stat bonuses",
    "forte upgrade",
    "forte upgrades",
    "character ascensions and stats",
    "character ascensions",
    "forte",
    "resonance chain",
    "quests and events",
    "instructions",
    "trophies",
    "notes",
    "gallery",
    "see also",
    "character trials",
    "character mentions",
    "trials by character",
    "dialogue",
    "dialogues",
    "transcript",
    "transcripts",
    "minigame",
    "minigames",
    "riddle",
    "riddles",
    "event rules",
    "booth",
    "stall",
    "audio",
    "voicelines",
    "outfit",
    "outfits",
})

# Sections to keep even if they seem like boilerplate (per page type)
# Key: page_type, Value: set of lowercase section titles to preserve
KEEP_SECTIONS_BY_TYPE: dict[str, FrozenSet[str]] = {
    "CHARACTER": frozenset({"trivia", "gallery"}),
    "QUEST": frozenset({"trivia"}),
}


def sanitize_html_tags(text: str) -> str:
    """Sanitize and convert HTML tags to clean Markdown."""
    if not text:
        return ""
    # Convert <u>...</u> -> **...**
    text = re.sub(r"<u[^>]*>(.*?)</u>", r"**\1**", text, flags=re.DOTALL | re.IGNORECASE)
    # Convert <b>...</b> -> **...**
    text = re.sub(r"<b[^>]*>(.*?)</b>", r"**\1**", text, flags=re.DOTALL | re.IGNORECASE)
    # Convert <i>...</i> -> *\1*
    text = re.sub(r"<i[^>]*>(.*?)</i>", r"*\1*", text, flags=re.DOTALL | re.IGNORECASE)
    # Convert <br>, <br/>, <br /> -> \n
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    # Strip any remaining HTML tags
    text = re.sub(r"<[^>]+>", "", text)
    return text


def sanitize_header_title(title: str) -> str:
    """Sanitize section heading titles by stripping Markdown formatting & HTML tags."""
    if not title:
        return ""
    # Strip Markdown formatting (*, _, #, ~, `)
    clean = re.sub(r"[\*\_\#\~\`]", "", title)
    # Strip HTML tags
    clean = re.sub(r"<[^>]+>", "", clean)
    return clean.strip()


def _cleanup_orphaned_brackets(text: str) -> str:
    """Remove orphaned }} or {{ brackets left behind by partial template stripping."""
    if not text:
        return ""
    # Remove lines containing only }} or {{
    text = re.sub(r"^\s*\}\}\s*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*\{\{\s*$", "", text, flags=re.MULTILINE)
    # Remove trailing }} at end of text/lines
    text = re.sub(r"\}\}\s*$", "", text)
    text = re.sub(r"^\s*\}\}", "", text)
    return text


# ─────────────────────────────────────────────────────────────
# Core sanitization function
# ─────────────────────────────────────────────────────────────


def extract_infobox_to_text(text: str, default_title: str = "") -> Tuple[str, str]:
    """
    Extracts {{Resonator Infobox ...}} parameters into a clean natural language summary,
    and removes the entire raw Infobox template block from text (handling nested templates).
    """
    idx = text.find("{{Resonator Infobox")
    if idx == -1:
        idx = text.find("{{resonator infobox")
    if idx == -1:
        return "", text

    # Find matching closing }} for {{Resonator Infobox ...
    depth = 0
    end_idx = idx
    for i in range(idx, len(text) - 1):
        if text[i:i+2] == "{{":
            depth += 1
        elif text[i:i+2] == "}}":
            depth -= 1
            if depth == 0:
                end_idx = i + 2
                break

    if end_idx == idx:
        end_idx = len(text)

    raw_infobox = text[idx:end_idx]
    fields: dict[str, str] = {}
    for line in raw_infobox.split("\n"):
        line = line.strip()
        if line.startswith("|") and "=" in line:
            parts = line[1:].split("=", 1)
            key = parts[0].strip().lower()
            val = parts[1].strip()
            if val and not val.startswith("<!--") and not val.startswith("{{Infobox") and not val.startswith("<gallery"):
                # Clean markup inside values
                val = re.sub(r"<ref[^>]*>.*?</ref>", "", val, flags=re.DOTALL)
                val = re.sub(r"\[\[[^\]|]+\|([^\]]+)\]\]", r"\1", val)
                val = re.sub(r"\[\[([^\]]+)\]\]", r"\1", val)
                val = re.sub(r"\{\{w\|(?:[^|}]*\|)?([^}]+)\}\}", r"\1", val)
                val = re.sub(r"\{\{Lang\|[^|}]*\|([^}]+)\}\}", r"\1", val)
                val = re.sub(r"\{\{zh\|([^}]+)\}\}", r"\1", val)
                val = re.sub(r"\[https?://[^\s\]]+\s+([^\]]+)\]", r"\1", val)
                val = val.strip()
                if val:
                    fields[key] = val

    name = fields.get("name", default_title)
    res_title = fields.get("title", "")
    rarity = fields.get("rarity", "")
    attribute = fields.get("attribute", "")
    weapon = fields.get("weapon", "")
    nation = fields.get("nation", "")
    birthplace = fields.get("birthplace", "")
    affiliation = fields.get("affiliation", "")
    affiliation2 = fields.get("affiliation2", "")
    relative = fields.get("relative", "")

    summary_parts = []
    if name:
        summary_parts.append(f"# {name}")

    meta_items = []
    if res_title:
        meta_items.append(f"Title: {res_title}")
    if rarity:
        meta_items.append(f"Rarity: {rarity}★")
    if attribute:
        meta_items.append(f"Attribute: {attribute}")
    if weapon:
        meta_items.append(f"Weapon: {weapon}")
    if birthplace or nation:
        meta_items.append(f"Origin: {birthplace or nation}")
    if affiliation:
        affs = [affiliation]
        if affiliation2 and affiliation2 not in affs:
            affs.append(affiliation2)
        meta_items.append(f"Affiliation: {', '.join(affs)}")
    if relative:
        meta_items.append(f"Relative: {relative}")

    if meta_items:
        summary_parts.append(f"**Profile**: {', '.join(meta_items)}.")

    summary_text = "\n\n".join(summary_parts)
    cleaned_text = text[:idx] + summary_text + "\n\n" + text[end_idx:]
    return summary_text, cleaned_text


def sanitize_wikitext(text: str, page_id: Optional[int] = None, page_title: Optional[str] = None) -> str:
    """
    Sanitize raw MediaWiki wikitext using mwparserfromhell AST node traversal.
    Ensures 100% precise template filtering without brittle regex matching.
    """
    if not text:
        return ""

    original_length = len(text)
    try:
        code = mwparserfromhell.parse(text)
    except Exception as exc:
        logger.warning("AST parsing failed, fallback to regex", error=str(exc))
        return sanitize_wikitext_regex(text, page_id=page_id, page_title=page_title)

    # 1. Remove HTML comments
    for comment in code.filter_comments():
        try:
            code.remove(comment)
        except ValueError:
            pass

    # 2. Remove <ref> and <gallery> tags
    for tag in code.filter_tags():
        tag_name = str(tag.tag).lower()
        if tag_name in ("ref", "gallery"):
            try:
                code.remove(tag)
            except ValueError:
                pass

    # 3. Extract Infobox to text & remove raw template
    infobox_summary = ""
    for tmpl in list(code.filter_templates()):
        tmpl_name = str(tmpl.name).strip().lower()
        if tmpl_name in ("infobox gallery", "gallery"):
            try:
                code.remove(tmpl)
            except ValueError:
                pass
            continue

        if "infobox" in tmpl_name:
            fields: dict[str, str] = {}
            for param in tmpl.params:
                p_name = str(param.name).strip().lower()
                p_val = str(param.value).strip()
                if p_val and not p_val.startswith("<!--") and not p_val.startswith("{{Infobox") and not p_val.startswith("<gallery"):
                    # Clean wikitext inside param value
                    val_code = mwparserfromhell.parse(p_val)
                    p_val_clean = str(val_code.strip_code()).strip()
                    p_val_clean = re.sub(r"\[https?://[^\s\]]+\s+([^\]]+)\]", r"\1", p_val_clean)
                    if p_val_clean:
                        fields[p_name] = p_val_clean

            if "faction" in tmpl_name:
                name = fields.get("title", "") or fields.get("name", "")
                leader = fields.get("leader", "")
                founder = fields.get("founder", "")
                base = fields.get("base", "")
                ally = fields.get("ally", "")
                enemy = fields.get("enemy", "")

                meta_items = []
                if leader:
                    meta_items.append(f"Leader: {leader}")
                if founder:
                    meta_items.append(f"Founder: {founder}")
                if base:
                    meta_items.append(f"Base: {base}")
                if ally:
                    meta_items.append(f"Allies: {ally}")
                if enemy:
                    meta_items.append(f"Enemies: {enemy}")

                parts = []
                if name:
                    parts.append(f"# {name}")
                if meta_items:
                    parts.append(f"**Faction Profile**: {', '.join(meta_items)}.")
                if parts:
                    infobox_summary = "\n\n".join(parts)
            else:
                name = fields.get("name", "")
                res_title = fields.get("title", "")
                rarity = fields.get("rarity", "")
                attribute = fields.get("attribute", "")
                weapon = fields.get("weapon", "")
                origin = fields.get("birthplace") or fields.get("nation") or ""
                affiliation = fields.get("affiliation", "")
                affiliation2 = fields.get("affiliation2", "")
                relative = fields.get("relative", "")
                gender = fields.get("gender", "")
                res_type = fields.get("type", "")

                meta_items = []
                if res_title:
                    meta_items.append(f"Title: {res_title}")
                if res_type:
                    meta_items.append(f"Status: {res_type}")
                if gender:
                    meta_items.append(f"Gender: {gender}")
                if rarity:
                    meta_items.append(f"Rarity: {rarity}★")
                if attribute:
                    meta_items.append(f"Attribute: {attribute}")
                if weapon:
                    meta_items.append(f"Weapon: {weapon}")
                if origin:
                    meta_items.append(f"Origin: {origin}")
                if affiliation:
                    affs = [affiliation]
                    if affiliation2 and affiliation2 not in affs:
                        affs.append(affiliation2)
                    meta_items.append(f"Affiliation: {', '.join(affs)}")
                if relative:
                    meta_items.append(f"Relative: {relative}")

                parts = []
                if name:
                    parts.append(f"# {name}")
                if meta_items:
                    parts.append(f"**Profile**: {', '.join(meta_items)}.")
                if parts:
                    infobox_summary = "\n\n".join(parts)

            try:
                code.remove(tmpl)
            except ValueError:
                pass

    # 4. Handle special inline templates first, then remove blocklisted templates
    for tmpl in code.filter_templates():
        t_name = str(tmpl.name).strip().lower()

        if "character archives" in t_name or "character archive" in t_name:
            unrolled_blocks = []
            power = ""
            evaluation = ""
            overclock = ""
            info = ""

            if tmpl.has("power"):
                p_code = mwparserfromhell.parse(str(tmpl.get("power").value).strip())
                power = str(p_code.strip_code()).strip()
            if tmpl.has("evaluation"):
                e_code = mwparserfromhell.parse(str(tmpl.get("evaluation").value).strip())
                evaluation = str(e_code.strip_code()).strip()
                # Clean html line breaks
                evaluation = re.sub(r"<br\s*/?>", "\n", evaluation, flags=re.IGNORECASE)
            if tmpl.has("overclock"):
                o_code = mwparserfromhell.parse(str(tmpl.get("overclock").value).strip())
                overclock = str(o_code.strip_code()).strip()
                overclock = re.sub(r"<br\s*/?>", "\n", overclock, flags=re.IGNORECASE)
            if tmpl.has("info"):
                i_code = mwparserfromhell.parse(str(tmpl.get("info").value).strip())
                info = str(i_code.strip_code()).strip()
                info = re.sub(r"<br\s*/?>", "\n", info, flags=re.IGNORECASE)

            if power:
                unrolled_blocks.append(f"**Resonance Power**: {power}")
            if evaluation:
                unrolled_blocks.append(f"### Forte Examination Report\n{evaluation}")
            if overclock:
                unrolled_blocks.append(f"### Overclock Diagnostic Report\n{overclock}")
            if info:
                unrolled_blocks.append(f"### Character Profile\n{info}")

            if unrolled_blocks:
                try:
                    code.replace(tmpl, "\n\n" + "\n\n".join(unrolled_blocks) + "\n\n")
                except ValueError:
                    pass

        elif "cherished items" in t_name or "cherished item" in t_name:
            unrolled_blocks = []
            param_dict = {str(p.name).strip().lower(): str(p.value).strip() for p in tmpl.params}
            i = 1
            while f"name{i}" in param_dict or f"text{i}" in param_dict or f"item{i}" in param_dict:
                name = param_dict.get(f"name{i}") or param_dict.get(f"item{i}") or f"Item {i}"
                text_val = param_dict.get(f"text{i}") or param_dict.get(f"desc{i}") or ""
                if text_val:
                    text_code = mwparserfromhell.parse(text_val)
                    text_clean = str(text_code.strip_code()).strip()
                    unrolled_blocks.append(f"### {name}\n{text_clean}")
                i += 1
            if unrolled_blocks:
                try:
                    code.replace(tmpl, "\n\n".join(unrolled_blocks))
                except ValueError:
                    pass

        elif "character stories" in t_name or "character story" in t_name:
            unrolled_blocks = []
            param_dict = {str(p.name).strip().lower(): str(p.value).strip() for p in tmpl.params}
            i = 1
            while f"title{i}" in param_dict or f"text{i}" in param_dict or f"story{i}" in param_dict:
                title_val = param_dict.get(f"title{i}") or param_dict.get(f"story{i}") or f"Story {i}"
                text_val = param_dict.get(f"text{i}") or ""
                if text_val:
                    text_code = mwparserfromhell.parse(text_val)
                    text_clean = str(text_code.strip_code()).strip()
                    unrolled_blocks.append(f"### {title_val}\n{text_clean}")
                i += 1
            if unrolled_blocks:
                try:
                    code.replace(tmpl, "\n\n".join(unrolled_blocks))
                except ValueError:
                    pass

        elif any(b in t_name for b in AST_TEMPLATE_BLOCKLIST):
            try:
                code.remove(tmpl)
            except ValueError:
                pass
        elif t_name == "description":
            desc_val = ""
            if tmpl.has(1):
                desc_val = str(tmpl.get(1).value).strip()
            elif tmpl.has("text"):
                desc_val = str(tmpl.get("text").value).strip()
            if desc_val:
                desc_code = mwparserfromhell.parse(desc_val)
                desc_clean = str(desc_code.strip_code()).strip()
                try:
                    code.replace(tmpl, desc_clean)
                except ValueError:
                    pass
        elif t_name == "quote":
            q_text = str(tmpl.get(1).value).strip() if tmpl.has(1) else ""
            q_author = str(tmpl.get(2).value).strip() if tmpl.has(2) else ""
            if q_author and not q_author.startswith("http"):
                replacement = f"> {q_text}\n> — {q_author}"
            else:
                replacement = f"> {q_text}"
            try:
                code.replace(tmpl, replacement)
            except ValueError:
                pass
        elif t_name in ("mc", "w", "lang", "rubi", "zh"):
            if tmpl.has(1):
                clean_val = str(tmpl.get(1).value).strip()
                if "|" in clean_val:
                    clean_val = clean_val.split("|")[-1]
                try:
                    code.replace(tmpl, clean_val)
                except ValueError:
                    pass
        elif t_name in ("pagename", "fullpagename", "basepagename", "subpagename"):
            replacement = ""
            if page_title:
                if t_name == "basepagename":
                    replacement = page_title.split("/")[0].strip()
                elif t_name == "subpagename":
                    replacement = page_title.split("/")[-1].strip()
                else:
                    replacement = page_title
            elif tmpl.has(1):
                replacement = str(tmpl.get(1).value).strip()
            try:
                code.replace(tmpl, replacement)
            except ValueError:
                pass

    # 5. Remove Category and Language Interwiki links
    for wikilink in code.filter_wikilinks():
        target = str(wikilink.title).strip()
        if target.lower().startswith("category:") or re.match(r"^[a-z]{2,3}:", target.lower()):
            try:
                code.remove(wikilink)
            except ValueError:
                pass

    cleaned = str(code)
    if infobox_summary:
        cleaned = f"{infobox_summary}\n\n{cleaned}"

    # Replace residual PAGENAME magic words if any
    if page_title:
        cleaned = _RE_PAGENAME.sub(page_title, cleaned)
    else:
        cleaned = _RE_PAGENAME.sub("", cleaned)

    # Normalize whitespace & remove excess blank lines
    cleaned = _RE_INTERWIKI.sub("", cleaned)
    cleaned = _RE_BARE_INTERWIKI.sub("", cleaned)
    cleaned = _RE_MAGIC_WORDS.sub("", cleaned)
    cleaned = _RE_IMAGE_LINE.sub("", cleaned)
    cleaned = _RE_MENTION_LINE.sub("", cleaned)
    cleaned = _RE_CRLF.sub("\n", cleaned)
    cleaned = _RE_CR.sub("\n", cleaned)

    # HTML Sanitization
    cleaned = sanitize_html_tags(cleaned)

    # Orphaned Bracket Cleanup
    cleaned = _cleanup_orphaned_brackets(cleaned)

    cleaned = _RE_EXCESS_BLANK_LINES.sub("\n\n", cleaned).strip()

    removed_chars = original_length - len(cleaned)
    if removed_chars > 0:
        logger.debug(
            "sanitize_wikitext_ast_complete",
            page_id=page_id,
            chars_removed=removed_chars,
            reduction_pct=round((removed_chars / original_length) * 100, 1),
        )

    return cleaned


def sanitize_wikitext_regex(text: str, page_id: Optional[int] = None, page_title: Optional[str] = None) -> str:
    """
    Clean raw MediaWiki wikitext by removing noise elements and converting infoboxes to clean text.

    Applies 9 ordered operations as specified in §3.2 Stage 1.
    Pure function — no side effects, no I/O.

    Args:
        text: Raw MediaWiki wikitext content.
        page_id: Optional page ID for structured log context.
        page_title: Optional page title for {{PAGENAME}} replacement.

    Returns:
        Sanitized wikitext with dangerous/noisy elements removed.

    Example::

        raw = "'''Bold''' text<!-- hidden --><ref>cite</ref>"
        clean = sanitize_wikitext(raw)
        # Result: "'''Bold''' text"
    """
    if not text:
        return ""

    original_length = len(text)
    log_ctx = {"page_id": page_id} if page_id else {}

    # Replace PAGENAME magic words if title is known
    if page_title:
        text = _RE_PAGENAME.sub(page_title, text)
    else:
        text = _RE_PAGENAME.sub("", text)

    # ── Operation 1: Strip HTML comments ──
    text = _RE_HTML_COMMENT.sub("", text)

    # ── Operation 2: Strip <ref> tags and content ──
    text = _RE_REF_SELF_CLOSING.sub("", text)
    text = _RE_REF_PAIRED.sub("", text)

    # ── Operation 3: Strip <gallery> blocks ──
    text = _RE_GALLERY.sub("", text)

    # ── Operation 4: Strip categories ──
    text = _RE_CATEGORY.sub("", text)

    # ── Operation 5: Strip interwiki links ──
    text = _RE_INTERWIKI.sub("", text)
    text = _RE_BARE_INTERWIKI.sub("", text)

    # ── Operation 6: Strip magic words ──
    text = _RE_MAGIC_WORDS.sub("", text)

    # ── Operation 6a: Transform Infobox into clean text ──
    _, text = extract_infobox_to_text(text)

    # ── Operation 6b: Strip display templates & convert inline templates ──
    text = _RE_DISPLAY_TEMPLATES.sub("", text)

    # Inline template cleanup
    text = _RE_MC_TEMPLATE.sub(lambda m: m.group(1) or m.group(2) or m.group(3) or m.group(4) or "", text)
    text = _RE_W_TEMPLATE.sub(r"\1", text)
    text = _RE_LANG_TEMPLATE.sub(r"\1", text)
    text = _RE_RUBI_TEMPLATE.sub(r"\1", text)

    # Convert Quotes {{Quote|Text|Author}} -> > Text — Author
    def _quote_replacer(match: re.Match[str]) -> str:
        parts = match.group(1).split("|")
        q_text = parts[0].strip()
        q_author = parts[1].strip() if len(parts) > 1 else ""
        if q_author and not q_author.startswith("http"):
            return f"> {q_text}\n> — {q_author}"
        return f"> {q_text}"

    text = re.sub(r"\{\{Quote\|([^}]+)\}\}", _quote_replacer, text, flags=re.IGNORECASE)

    # Convert ParserFunction Quotes {{#SQuote: Text | author = Author}} -> > Text — Author
    def _squote_replacer(match: re.Match[str]) -> str:
        content = match.group(1).strip()
        parts = [p.strip() for p in content.split("|") if p.strip()]
        if not parts:
            return ""
        q_text = parts[0]
        q_author = ""
        for p in parts[1:]:
            if p.lower().startswith("author="):
                q_author = p.split("=", 1)[1].strip()
            elif not q_author and not p.startswith("http") and not p.startswith("source="):
                q_author = p
        if q_author:
            return f"> \"{q_text}\"\n> — {q_author}"
        return f"> \"{q_text}\""

    text = re.sub(r"\{\{#SQuote:([^}]+)\}\}", _squote_replacer, text, flags=re.IGNORECASE)

    # Convert {{Extra Effect|Name|Display|Description}} -> Display (Description)
    def _extra_effect_replacer(match: re.Match[str]) -> str:
        content = match.group(1).strip()
        parts = [p.strip() for p in content.split("|") if p.strip()]
        if not parts:
            return ""
        if len(parts) >= 3:
            name = parts[1] or parts[0]
            desc = parts[2]
            return f"{name} ({desc})"
        elif len(parts) == 2:
            return f"{parts[0]} ({parts[1]})"
        return parts[0]

    text = re.sub(r"\{\{Extra Effect\|([^}]+)\}\}", _extra_effect_replacer, text, flags=re.IGNORECASE)
    text = re.sub(r"\{\{Tooltip\|([^}|]+)\|([^}]+)\}\}", r"\1 (\2)", text, flags=re.IGNORECASE)

    # Unpack Game Entity Macros: {{Enemy|Name}}, {{Item|Name}}, {{Resonator|Name}}, {{Faction|Name}}, {{Location|Name}}, {{Echo|Name}}, {{Weapon|Name}}
    text = re.sub(r"\{\{(?:Enemy|Item|Resonator|Location|Faction|Echo|Weapon|Character)\|([^}|]+)(?:\|[^}]+)?\}\}", r"\1", text, flags=re.IGNORECASE)
    text = re.sub(r"\{\{(?:Icon|Color|Card|Asset)\|[^}]*\}\}", "", text, flags=re.IGNORECASE)

    # Strip remaining untransformed display templates
    text = _RE_DISPLAY_TEMPLATES.sub("", text)

    # ── Operation 7: Strip image-only lines ──
    text = _RE_IMAGE_LINE.sub("", text)

    # ── Operation 8: Normalize line endings ──
    text = _RE_CRLF.sub("\n", text)
    text = _RE_CR.sub("\n", text)

    # ── Operation 9: Fix punctuation spacing glitches ──
    # Fix glued quotation mark to sentence start: "rest?"She -> "rest?" She
    text = re.sub(r'([.?!",])([A-Z])', r'\1 \2', text)
    # Fix orphan dot: from .Her -> from Her
    text = re.sub(r'\bfrom\s+\.\s*([A-Z])', r'from \1', text)
    # Fix space before punctuation
    text = re.sub(r'\s+([,.:;?!])', r'\1', text)

    # ── Operation 10: Collapse excessive blank lines ──
    text = _RE_EXCESS_BLANK_LINES.sub("\n\n", text)

    # Trim leading/trailing whitespace
    text = text.strip()

    removed_chars = original_length - len(text)
    if removed_chars > 0:
        logger.debug(
            "sanitize_wikitext_complete",
            chars_removed=removed_chars,
            reduction_pct=round((removed_chars / max(original_length, 1)) * 100, 1),
            **log_ctx,
        )

    return text


# ─────────────────────────────────────────────────────────────
# Wikitext → Markdown Conversion
# ─────────────────────────────────────────────────────────────


def convert_mediawiki_tables_to_markdown(text: str) -> str:
    """
    Converts MediaWiki table syntax ({| ... |}) to clean GFM Markdown tables or lists.
    Properly handles multi-line cells, bullet lists within cells, and cell attributes.
    """
    if "{|" not in text:
        return text

    table_block_pattern = re.compile(r"\{\|[^\n]*\n.*?\|\}", re.DOTALL)

    def _clean_cell_content(raw: str) -> str:
        if not raw:
            return ""
        # Strip cell HTML/CSS attributes like style="...", class="...", id="...", width="..."
        if "|" in raw:
            parts = raw.split("|")
            first = parts[0].strip()
            if any(attr in first.lower() for attr in ("style=", "class=", "id=", "width=", "colspan=", "rowspan=", "align=", "valign=")):
                raw = "|".join(parts[1:]).strip()

        # Format multi-line list items within cell
        lines = [line.strip() for line in raw.split("\n") if line.strip()]
        cleaned_items = []
        for line in lines:
            # Strip bullet prefixes (*, **, #, -)
            cleaned_line = re.sub(r"^[\*\#\-]+\s*", "", line).strip()
            if cleaned_line:
                cleaned_items.append(cleaned_line)

        cell_text = "; ".join(cleaned_items) if len(cleaned_items) > 1 else (cleaned_items[0] if cleaned_items else "")
        # Clean wikitext artifacts
        cell_text = re.sub(r"\[\[(?:File|Image):[^\]]*\]\]", "", cell_text, flags=re.IGNORECASE)
        cell_text = re.sub(r"\[\[(?:[^\]|]+\|)?([^\]]+)\]\]", r"\1", cell_text)
        cell_text = re.sub(r"\{\{(?:Enemy|Item|Resonator|Location|Faction|Echo|Weapon|Character)\|([^}|]+)(?:\|[^}]+)?\}\}", r"\1", cell_text, flags=re.IGNORECASE)
        cell_text = re.sub(r"\{\{(?:Icon|Color|Card|Asset)\|[^}]*\}\}", "", cell_text, flags=re.IGNORECASE)
        cell_text = re.sub(r"'{2,3}", "", cell_text)
        cell_text = cell_text.replace("|", "\\|").strip()
        return cell_text

    def _table_to_markdown(match: re.Match[str]) -> str:
        raw_table = match.group(0)
        lines = raw_table.split("\n")
        if not lines:
            return ""

        headers: List[str] = []
        rows: List[List[str]] = []
        current_row: List[str] = []
        current_cell_lines: List[str] = []
        in_header = False

        def flush_cell():
            nonlocal current_cell_lines
            if current_cell_lines:
                raw_cell = "\n".join(current_cell_lines).strip()
                cleaned_val = _clean_cell_content(raw_cell)
                if in_header:
                    headers.append(cleaned_val)
                else:
                    current_row.append(cleaned_val)
                current_cell_lines = []

        def flush_row():
            nonlocal current_row
            flush_cell()
            if current_row:
                rows.append(current_row)
                current_row = []

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("{|") or stripped == "|}":
                continue

            if stripped.startswith("|-"):
                flush_row()
                in_header = False
                continue

            # Header definitions (! Col1 ! Col2 or ! Col1 !! Col2)
            if stripped.startswith("!"):
                flush_row()
                in_header = True
                content = stripped[1:].strip()
                parts = re.split(r"\s*!{1,2}\s*", content)
                for p in parts:
                    headers.append(_clean_cell_content(p))
                current_cell_lines = []
                continue

            # Data cell definitions (| Cell1 || Cell2 or | Cell1)
            if stripped.startswith("|"):
                in_header = False
                content = stripped[1:].strip()
                parts = re.split(r"\s*\|\|\s*", content)
                flush_cell()
                for p in parts[:-1]:
                    current_row.append(_clean_cell_content(p))
                current_cell_lines = [parts[-1]] if parts else []
                continue

            # Continuation line for the current cell
            if current_cell_lines is not None:
                current_cell_lines.append(stripped)

        flush_row()

        cols_to_keep: List[int] = []
        if headers:
            for idx, h in enumerate(headers):
                if h.lower() not in ("image", "icon", "picture", "file", "thumb", "photo"):
                    cols_to_keep.append(idx)
        else:
            max_cols = max((len(r) for r in rows), default=0)
            cols_to_keep = list(range(max_cols))

        if not rows:
            return ""

        md_lines = []
        if headers and cols_to_keep:
            active_headers = [headers[i] if i < len(headers) else f"Column {i+1}" for i in cols_to_keep]
            md_lines.append("| " + " | ".join(active_headers) + " |")
            md_lines.append("| " + " | ".join(["---"] * len(active_headers)) + " |")

        for r in rows:
            row_cells = []
            for i in cols_to_keep:
                c_val = r[i] if i < len(r) else ""
                row_cells.append(c_val.strip())
            if any(c for c in row_cells if c):
                if not headers:
                    non_empty = [c for c in row_cells if c]
                    if non_empty:
                        md_lines.append("- " + ": ".join(non_empty))
                else:
                    md_lines.append("| " + " | ".join(row_cells) + " |")

        return "\n\n" + "\n".join(md_lines) + "\n\n"

    return table_block_pattern.sub(_table_to_markdown, text)


def wikitext_to_markdown(text: str) -> str:
    """Convert wikitext markup to clean Markdown formatting."""
    if not text:
        return ""

    # Convert MediaWiki tables ({| ... |}) to clean GFM Markdown tables first
    text = convert_mediawiki_tables_to_markdown(text)

    # Fix broken headings first
    text = _RE_BROKEN_HEADING.sub(r"\1 \2", text)

    # Bold and Italic
    text = _RE_BOLD_ITALIC.sub(r"***\1***", text)
    text = _RE_BOLD.sub(r"**\1**", text)
    text = _RE_ITALIC.sub(r"*\1*", text)

    # Unpack templates into clean Markdown text
    def _squote_replacer(match: re.Match[str]) -> str:
        content = match.group(1).strip()
        parts = [p.strip() for p in content.split("|") if p.strip()]
        if not parts:
            return ""
        q_text = parts[0]
        q_author = ""
        for p in parts[1:]:
            if p.lower().startswith("author="):
                q_author = p.split("=", 1)[1].strip()
            elif not q_author and not p.startswith("http") and not p.startswith("source="):
                q_author = p
        if q_author:
            return f"> \"{q_text}\"\n> — {q_author}"
        return f"> \"{q_text}\""

    text = re.sub(r"\{\{#SQuote:([^}]+)\}\}", _squote_replacer, text, flags=re.IGNORECASE)

    def _extra_effect_replacer(match: re.Match[str]) -> str:
        content = match.group(1).strip()
        parts = [p.strip() for p in content.split("|") if p.strip()]
        if not parts:
            return ""
        if len(parts) >= 3:
            name = parts[1] or parts[0]
            desc = parts[2]
            return f"{name} ({desc})"
        elif len(parts) == 2:
            return f"{parts[0]} ({parts[1]})"
        return parts[0]

    text = re.sub(r"\{\{Extra Effect\|([^}]+)\}\}", _extra_effect_replacer, text, flags=re.IGNORECASE)
    text = re.sub(r"\{\{Tooltip\|([^}|]+)\|([^}]+)\}\}", r"\1 (\2)", text, flags=re.IGNORECASE)

    # Unpack Game Entity Macros: {{Enemy|Name}}, {{Item|Name}}, {{Resonator|Name}}, {{Faction|Name}}, {{Location|Name}}, {{Echo|Name}}, {{Weapon|Name}}
    text = re.sub(r"\{\{(?:Enemy|Item|Resonator|Location|Faction|Echo|Weapon|Character)\|([^}|]+)(?:\|[^}]+)?\}\}", r"\1", text, flags=re.IGNORECASE)
    text = re.sub(r"\{\{(?:Icon|Color|Card|Asset)\|[^}]*\}\}", "", text, flags=re.IGNORECASE)

    # Strip display and dynamic category table templates
    text = _RE_DISPLAY_TEMPLATES.sub("", text)

    # Wiki links → plain text
    text = _RE_WIKILINK_DISPLAY.sub(r"\1", text)
    text = _RE_WIKILINK_SIMPLE.sub(r"\1", text)

    # External links
    text = _RE_EXTERNAL_LINK.sub(r"\1", text)
    text = _RE_EXTERNAL_LINK_BARE.sub("", text)

    # Wiki headings == Title == → ## Title
    def _heading_replacer(match: re.Match[str]) -> str:
        level = len(match.group(1))
        title = match.group(2).strip()
        return f"{'#' * level} {title}"

    text = _RE_HEADING.sub(_heading_replacer, text)

    # Remove inline image size references
    text = _RE_INLINE_IMAGE.sub("", text)

    # Fix punctuation spacing glitches
    text = re.sub(r'([.?!",])([A-Z])', r'\1 \2', text)
    text = re.sub(r'\bfrom\s+\.\s*([A-Z])', r'from \1', text)
    text = re.sub(r'\s+([,.:;?!])', r'\1', text)

    # Collapse any newly-created excessive blank lines
    text = _RE_EXCESS_BLANK_LINES.sub("\n\n", text)

    return text.strip()


# Backward compatibility alias
convert_wikitext_to_markdown = wikitext_to_markdown


# ─────────────────────────────────────────────────────────────
# Boilerplate section removal
# ─────────────────────────────────────────────────────────────


def strip_boilerplate_sections(
    text: str,
    *,
    page_type: Optional[str] = None,
    blocklist: Optional[FrozenSet[str]] = None,
    extra_keep: Optional[FrozenSet[str]] = None,
) -> Tuple[str, List[str]]:
    """

    Args:
        text: Normalized markdown text (post wikitext→markdown conversion).
        page_type: Page type string for type-specific keep rules.
            E.g., CHARACTER pages keep "Trivia".
        blocklist: Custom set of lowercase section titles to remove.
            Defaults to ``DEFAULT_BOILERPLATE_SECTIONS``.
        extra_keep: Additional lowercase section titles to preserve
            regardless of blocklist.

    Returns:
        Tuple of (cleaned_text, list_of_removed_section_titles).

    Example::

        text = "## Lore\\nSome content\\n\\n## Other Languages\\nJP: ...\\n## Navigation\\n"
        cleaned, removed = strip_boilerplate_sections(text)
        # cleaned = "## Lore\\nSome content"
        # removed = ["Other Languages", "Navigation"]
    """
    if not text:
        return "", []

    if blocklist is None:
        blocklist = DEFAULT_BOILERPLATE_SECTIONS

    # Determine which sections to preserve for this page type
    keep_set: FrozenSet[str] = frozenset()
    if page_type and page_type in KEEP_SECTIONS_BY_TYPE:
        keep_set = KEEP_SECTIONS_BY_TYPE[page_type]
    if extra_keep:
        keep_set = keep_set | extra_keep

    # Effective blocklist: original minus type-specific keeps
    effective_blocklist = blocklist - keep_set

    # Parse into sections by heading (supports both Markdown ## and Wikitext ==)
    lines = text.split("\n")

    # Build section boundaries: [(start_line, level, title), ...]
    sections: List[Tuple[int, int, str]] = []
    for i, line in enumerate(lines):
        line_clean = line.strip()
        m = re.match(r"^(=+|#+)\s*(.+?)\s*\1?$", line_clean)
        if m:
            h_level = len(m.group(1))
            h_text = m.group(2).strip()
            if h_text:
                sections.append((i, h_level, h_text))

    if not sections:
        return text, []

    # Determine which line ranges to remove
    removed_titles: List[str] = []
    lines_to_remove: set[int] = set()

    for idx, (start_line, level, title) in enumerate(sections):
        t_low = title.lower().strip()
        if t_low in effective_blocklist or any(b in t_low for b in ("ascension", "stat bonus", "forte upgrade", "character ascensions")):
            # Find end of this section (next heading of same or higher level)
            if idx + 1 < len(sections):
                end_line = sections[idx + 1][0]
            else:
                end_line = len(lines)

            for line_num in range(start_line, end_line):
                lines_to_remove.add(line_num)

            removed_titles.append(title)

    if not lines_to_remove:
        return text, []

    # Rebuild text without removed lines
    cleaned_lines = [
        line for i, line in enumerate(lines) if i not in lines_to_remove
    ]
    cleaned_text = "\n".join(cleaned_lines).strip()

    # Collapse excessive blank lines introduced by removal
    cleaned_text = _RE_EXCESS_BLANK_LINES.sub("\n\n", cleaned_text)

    logger.debug(
        "boilerplate_removed",
        sections_removed=removed_titles,
        lines_removed=len(lines_to_remove),
    )

    return cleaned_text, removed_titles


# ─────────────────────────────────────────────────────────────
# Phase 2 AST-First + Config-Driven Chunk Sanitization API
# ─────────────────────────────────────────────────────────────

def clean_entities(
    entities: Any,
    engine: Optional[RuleEngine] = None,
    text_content: Optional[str] = None,
) -> List[str]:
    """Sanitize entity list by filtering trash phrases, stopwords, and ensuring entities actually exist in text_content."""
    if engine is None:
        engine = get_rule_engine()
    if not isinstance(entities, list):
        entities = []

    # Common English non-entity words, pronouns, adverbs, and verbs to exclude from NER
    NOISE_WORDS = {
        "profile", "title", "origin", "affiliation", "lead", "during", "however", "also", 
        "its", "they", "this", "that", "these", "those", "upon", "while", "certain", "known", 
        "main", "chapter", "part", "what", "well", "both", "despite", "his", "her", "their",
        "some", "many", "more", "other", "another", "such", "only", "first", "second", "third",
        "last", "next", "same", "different", "every", "each", "all", "any", "no", "not",
        "with", "without", "into", "onto", "over", "under", "above", "below", "between",
        "through", "before", "after", "from", "up", "down",
        "in", "out", "on", "off", "again", "further", "then", "once",
        "here", "there", "when", "where", "why", "how", "few", "most", "nor", "own",
        "so", "than", "too", "very", "can", "will", "just", "should", "now",
        "hahaha", "huh", "dicon", "reward", "correct", "unfortunately", "talk", "please", "chat",
        "something", "yes", "sure", "come", "don", "eyeing", "set", "humans", "loans", "memories",
        "the moon", "ahem", "sic", "tx", "color", "exit", "leave", "thanks", "sorry", "wait",
        "hey", "hello", "hi", "okay", "fine", "cool", "nice", "good", "bad", "riddle",
        "riddles", "stall", "booth", "dialogue", "dialogue start", "dialogue end", "prof", "professor",
        "name", "image", "images", "description", "intro", "location", "locations", "areas", "area",
        "points", "interest", "item", "items", "bell", "situated", "according", "details", "summary",
        "type", "category", "rarity", "cost", "source", "effect", "stats", "attribute", "attributes",
        "unlocked", "level", "rank", "stat", "value", "property", "properties", "table", "column", "row",
        "making", "could", "would", "she", "he", "it", "yet", "but", "one", "nutri",
        "pack", "aren", "pattern", "relatively", "previous", "class", "subsequent", "presently", "routine",
        "release", "cleanse", "category table", "these resonators", "extra effect", "mutant resonators",
        "ex42978", "although", "gold", "finally", "silence", "numb", "teachers", "among", "soon", "back",
        "normally", "occasionally", "wind", "sitting", "seeing", "beneath", "tears", "heartbeat",
        "someone", "anyone", "everyone", "nobody", "anything", "everything", "nothing"
    }

    cleaned: List[str] = []
    text_low = text_content.lower() if text_content else None

    for ent in entities:
        ent_str = ent if isinstance(ent, str) else str(ent.get("name", "")) if isinstance(ent, dict) else ""
        if not ent_str:
            continue

        # Strip linebreaks and markdown syntax inside entity string
        ent_str = re.sub(r"\s+", " ", ent_str).strip()
        ent_str = re.sub(r"^[\*\_>#\-\s]+|[\*\_>#\-\s]+$", "", ent_str).strip()
        
        words = ent_str.split()
        if words and words[0].lower() in engine.stopwords and len(words) > 1:
            ent_str = " ".join(words[1:])

        ent_low = ent_str.lower()
        if ent_low in engine.blacklist or len(ent_str) < 2 or len(ent_str) > 40:
            continue

        if ent_low in NOISE_WORDS:
            continue

        # Noise entity pattern filter (e.g. "His Resonance Liberation", "Sometimes Aalto", "Official Website", "Diagnostic Report")
        if re.search(r"^(His|Her|Their|Its|Sometimes|Always|Many|Some|Other|Although|These|Those|This|That)\b", ent_str, re.IGNORECASE):
            continue
        if re.search(r"\b(Report|Assessment|Diagnostic|Evaluation|Website|Table|List)$", ent_str, re.IGNORECASE):
            continue

        # If text_content is supplied, ensure entity actually appears in this chunk!
        if text_low and ent_low not in text_low:
            continue

        if ent_str not in cleaned:
            cleaned.append(ent_str)

    return cleaned


def should_drop_chunk(chunk: Dict[str, Any], engine: Optional[RuleEngine] = None) -> bool:
    """Evaluate Quality Gate conditions to drop low-value/junk chunks."""
    if engine is None:
        engine = get_rule_engine()

    text = chunk.get("text_content", "") or chunk.get("content", "") or ""
    tokens = chunk.get("token_count_approx", len(text.split()))
    text_lower = text.lower().strip()

    min_tokens = engine.quality_gate.get("min_tokens", 15)
    min_text_len = engine.quality_gate.get("min_text_len", 20)

    if tokens < min_tokens or len(text_lower) < min_text_len:
        return True

    if text_lower in {"{{stub}}", "stub", ""} or "page under construction" in text_lower:
        return True

    if text_lower.startswith("{{files by") or text_lower.startswith("{{resonator navbox"):
        return True

    if tokens < 45:
        patterns = engine.quality_gate.get("boilerplate_patterns", [])
        for pattern in patterns:
            if re.search(pattern, text_lower):
                return True

    return False


def clean_and_filter_chunk(raw_json_line: str, engine: Optional[RuleEngine] = None) -> Optional[str]:
    """
    Main Phase 2 ETL Ingestion function: AST-First Sanitization + Anomaly Monitoring + Quality Gate Filter.

    Args:
        raw_json_line: Single JSON line string from chunks.jsonl or canonical.jsonl.
        engine: Optional custom RuleEngine instance.

    Returns:
        Sanitized JSON string ready for Vector DB, or None if dropped by Quality Gate.
    """
    if engine is None:
        engine = get_rule_engine()

    if not raw_json_line or not raw_json_line.strip():
        return None

    try:
        data: Dict[str, Any] = json.loads(raw_json_line)
    except json.JSONDecodeError:
        return None

    text_key = "text_content" if "text_content" in data else "content" if "content" in data else "text_content"
    raw_text = data.get(text_key, "")
    page_title = data.get("page_title", "")
    canonical_name = data.get("canonical_name", "")

    # 1. Clean Content Text via AST Sanitizer
    sanitized_text = sanitize_wikitext(raw_text, page_title=page_title)
    cleaned_markdown = convert_wikitext_to_markdown(sanitized_text)

    data[text_key] = cleaned_markdown
    data["token_count_approx"] = len(cleaned_markdown.split())

    # 2. Clean Entities
    if "entities" in data:
        data["entities"] = clean_entities(data["entities"], engine=engine, text_content=cleaned_markdown)

    # 3. Clean Section Title
    if "section_title" in data and data["section_title"]:
        data["section_title"] = sanitize_header_title(data["section_title"])

    # 4. Context Loss Enhancement
    if "context_prefix" in data and data.get("heading_path"):
        entity_anchor = canonical_name or (page_title.split("/")[0] if page_title else "")
        page_type = data.get("page_type", "ENTITY")
        sec_title = data.get("section_title", "General")
        data["context_prefix"] = f"[{page_type}: {entity_anchor} | Section: {entity_anchor} > {sec_title}]"

    # 5. Quality Gate Evaluation
    if should_drop_chunk(data, engine=engine):
        return None

    # 6. Flag Borderline Chunks for Micro-LLM Async Rewrite
    q_score = float(data.get("quality_score", 0.9))
    min_b = float(engine.quality_gate.get("borderline_score_min", 0.5))
    max_b = float(engine.quality_gate.get("borderline_score_max", 0.7))
    data["needs_llm_rewrite"] = (min_b <= q_score <= max_b)

    return json.dumps(data, ensure_ascii=False)


def clean_categories(categories: Any, engine: Optional[RuleEngine] = None) -> List[str]:
    """Sanitize category tags by filtering junk gameplay/mechanics and system maintenance tags."""
    if engine is None:
        engine = get_rule_engine()
    if not isinstance(categories, list):
        return []

    cleaned: List[str] = []
    for cat in categories:
        cat_str = str(cat).strip()
        if not cat_str or engine.is_junk_category(cat_str):
            continue
        if cat_str not in cleaned:
            cleaned.append(cat_str)
    return cleaned


