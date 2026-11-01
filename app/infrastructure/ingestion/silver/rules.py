"""Load the versioned silver cleaning rules (`app/config/ingestion/cleaning.yaml`)."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from app.domain.ingestion.documents import BlockKind
from app.domain.ingestion.page_checks import FamilyContract
from app.infrastructure.ingestion.wiki_sync_config import CONFIG_DIR


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class _Drop(_Strict):
    classes: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    typeof: tuple[str, ...] = ()


class _Repair(_Strict):
    pattern: str
    replace: str


class _Contract(_Strict):
    requires_infobox: bool = False
    required_kinds: tuple[BlockKind, ...] = ()


class _Cleaning(_Strict):
    version: int
    cleaner_version: str = Field(min_length=1)
    drop: dict[str, _Drop]
    keep_hidden_tags: tuple[str, ...] = ()
    skip_sections: tuple[str, ...] = ()
    variant_tooltips: tuple[str, ...] = ()
    boilerplate_lines: tuple[str, ...] = ()
    repairs: tuple[_Repair, ...] = ()
    residue_patterns: tuple[str, ...] = Field(min_length=1)
    story_min_chars: int = Field(gt=0)
    contracts: dict[str, _Contract] = {}


def _any_of(patterns: tuple[str, ...]) -> re.Pattern[str]:
    # An empty alternation would match everything, so no patterns compiles to a never-match.
    alternation = "|".join(f"(?:{p})" for p in patterns) or r"(?!)"
    return re.compile(alternation, re.IGNORECASE)


@dataclass(frozen=True)
class CleaningRules:
    cleaner_version: str
    config_hash: str
    drop_classes: dict[str, str]
    drop_tags: dict[str, str]
    drop_typeof: dict[str, str]
    keep_hidden_tags: frozenset[str]
    skip_sections: re.Pattern[str]
    variant_tooltips: re.Pattern[str]
    boilerplate_lines: re.Pattern[str]
    repairs: tuple[tuple[re.Pattern[str], str], ...]
    residue: re.Pattern[str]
    story_min_chars: int
    contracts: dict[str, FamilyContract]


def load_cleaning_rules(path: Path = CONFIG_DIR / "cleaning.yaml") -> CleaningRules:
    text = path.read_text(encoding="utf-8")
    raw = _Cleaning.model_validate(yaml.safe_load(text))
    return CleaningRules(
        cleaner_version=raw.cleaner_version,
        config_hash=hashlib.sha256(text.encode("utf-8")).hexdigest()[:8],
        drop_classes={c: reason for reason, d in raw.drop.items() for c in d.classes},
        drop_tags={t: reason for reason, d in raw.drop.items() for t in d.tags},
        drop_typeof={t: reason for reason, d in raw.drop.items() for t in d.typeof},
        keep_hidden_tags=frozenset(raw.keep_hidden_tags),
        skip_sections=_any_of(raw.skip_sections),
        variant_tooltips=_any_of(raw.variant_tooltips),
        boilerplate_lines=_any_of(raw.boilerplate_lines),
        repairs=tuple((re.compile(r.pattern), r.replace) for r in raw.repairs),
        residue=_any_of(raw.residue_patterns),
        story_min_chars=raw.story_min_chars,
        contracts={
            family: FamilyContract(c.requires_infobox, frozenset(c.required_kinds))
            for family, c in raw.contracts.items()
        },
    )
