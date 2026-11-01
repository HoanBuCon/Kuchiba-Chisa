"""Load the versioned wiki-sync YAML (families, templates, sync policy) into domain objects."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from app.domain.ingestion.change_detection import FetchPolicy, TemplateClassifier
from app.domain.ingestion.families import FamilyCatalog, FamilyRule

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config" / "ingestion"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class _Family(_Strict):
    name: str
    tier: str = Field(pattern=r"^[AB]$")
    suffixes: tuple[str, ...] = ()
    categories: tuple[str, ...] = ()
    titles: tuple[str, ...] = ()
    subcategory_parents: tuple[str, ...] = ()


class _Families(_Strict):
    version: int
    enabled_tiers: tuple[str, ...]
    excluded_suffixes: tuple[str, ...] = ()
    families: tuple[_Family, ...] = Field(min_length=1)


class _Templates(_Strict):
    version: int
    content_patterns: tuple[str, ...] = ()
    chrome_patterns: tuple[str, ...] = ()


class SourceSettings(_Strict):
    api_url: str
    page_url: str
    license: str
    user_agent: str = Field(min_length=8)
    timeout_seconds: float = Field(gt=0, le=120)
    min_interval_seconds: float = Field(ge=0.5)
    max_retries: int = Field(ge=0, le=5)
    max_wait_seconds: float = Field(gt=0)
    max_response_bytes: int = Field(gt=0)


class _Fetch(_Strict):
    stabilization_hours: float = Field(ge=0)
    release_mode_stabilization_hours: float = Field(ge=0)
    rolling_refresh_fraction: float = Field(ge=0, le=1)
    max_pages_per_run: int = Field(ge=1)


class _Sync(_Strict):
    version: int
    source: SourceSettings
    fetch: _Fetch


class WikiSyncConfig(_Strict):
    catalog: FamilyCatalog
    classifier: TemplateClassifier
    policy: FetchPolicy
    release_mode_policy: FetchPolicy
    source: SourceSettings
    config_versions: dict[str, int]


def _read(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_wiki_sync_config(directory: Path = CONFIG_DIR) -> WikiSyncConfig:
    families = _Families.model_validate(_read(directory / "families.yaml"))
    templates = _Templates.model_validate(_read(directory / "templates.yaml"))
    sync = _Sync.model_validate(_read(directory / "sync.yaml"))
    fetch = sync.fetch

    def policy(hours: float) -> FetchPolicy:
        return FetchPolicy(
            stabilization=timedelta(hours=hours),
            rolling_fraction=fetch.rolling_refresh_fraction,
            budget=fetch.max_pages_per_run,
        )

    return WikiSyncConfig(
        catalog=FamilyCatalog(
            rules=tuple(FamilyRule(**family.model_dump()) for family in families.families),
            excluded_suffixes=families.excluded_suffixes,
            enabled_tiers=frozenset(families.enabled_tiers),
        ),
        classifier=TemplateClassifier(templates.chrome_patterns, templates.content_patterns),
        policy=policy(fetch.stabilization_hours),
        release_mode_policy=policy(fetch.release_mode_stabilization_hours),
        source=sync.source,
        config_versions={
            "families": families.version,
            "templates": templates.version,
            "sync": sync.version,
        },
    )
