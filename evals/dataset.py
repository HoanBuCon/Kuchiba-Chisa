"""Golden v2 dataset model; survives corpus rebuilds by referencing wiki page ids, not chunk ids."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Category(StrEnum):
    LORE_SINGLE_HOP = "lore_single_hop"
    ENUMERATION = "enumeration"
    MULTI_HOP = "multi_hop"
    DIALOGUE_DETAIL = "dialogue_detail"
    OUT_OF_SCOPE = "out_of_scope"
    MEMORY = "memory"
    PERSONA = "persona"


class Language(StrEnum):
    VI = "vi"
    EN = "en"
    VI_NO_DIACRITICS = "vi_no_diacritics"
    TEENCODE = "teencode"


class Mode(StrEnum):
    ADVANCED = "advanced"
    AGENTIC = "agentic"
    BOTH = "both"


class Behavior(StrEnum):
    ANSWER = "answer"
    ABSTAIN = "abstain"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Turn(_Strict):
    session: int = Field(default=1, ge=1)
    message: str = Field(min_length=1, max_length=4000)


class PageRef(_Strict):
    title: str = Field(min_length=1)
    pageid: int = Field(ge=1)


class PersonaCheck(_Strict):
    require_senpai: bool = False
    forbidden_patterns: tuple[str, ...] = ()


class GoldenCase(_Strict):
    id: str = Field(pattern=r"^[a-z]+(-[a-z0-9]+)*-\d{3}$")
    category: Category
    language: Language
    mode: Mode = Mode.BOTH
    turns: tuple[Turn, ...] = Field(min_length=1)
    expected_behavior: Behavior = Behavior.ANSWER
    # Each inner tuple is one fact; any one of its surface forms counts as a match.
    expected_facts: tuple[tuple[str, ...], ...] = ()
    min_fact_recall: float = Field(default=1.0, ge=0.0, le=1.0)
    relevant_pages: tuple[PageRef, ...] = ()
    persona: PersonaCheck = PersonaCheck()
    verified: bool = False
    notes: str = ""

    @model_validator(mode="after")
    def _behavior_matches_expectations(self) -> GoldenCase:
        if self.expected_behavior is Behavior.ANSWER and not self.expected_facts:
            raise ValueError(f"{self.id}: answer cases need expected_facts")
        if self.expected_behavior is Behavior.ABSTAIN and (
            self.expected_facts or self.relevant_pages
        ):
            raise ValueError(f"{self.id}: abstain cases cannot expect facts or pages")
        if any(not fact for fact in self.expected_facts):
            raise ValueError(f"{self.id}: every fact needs at least one surface form")
        return self

    @property
    def sessions(self) -> int:
        return max(turn.session for turn in self.turns)


class Approval(_Strict):
    status: str = Field(pattern=r"^(draft|approved)$")
    approved_by: str | None = None
    approved_at: str | None = None


class GoldenSet(_Strict):
    dataset_version: str = Field(min_length=1)
    source_snapshot: str = Field(min_length=1)
    approval: Approval
    abstain_markers: tuple[str, ...] = Field(min_length=1)
    cases: tuple[GoldenCase, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _ids_are_unique(self) -> GoldenSet:
        ids = [case.id for case in self.cases]
        duplicates = sorted({case_id for case_id in ids if ids.count(case_id) > 1})
        if duplicates:
            raise ValueError(f"duplicate case ids: {', '.join(duplicates)}")
        return self


def load_golden_set(path: Path) -> GoldenSet:
    """Load and validate a golden set YAML file."""
    return GoldenSet.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
