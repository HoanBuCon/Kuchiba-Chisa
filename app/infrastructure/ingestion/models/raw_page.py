"""
Raw Page Schema — Unprocessed wiki page data from MediaWiki API crawl.

This represents the very first stage of the pipeline: raw, untouched wikitext
plus its API-provided metadata sidecar. Stored as individual files:
    - data/raw_wiki/{page_id}.wikitext   (raw markup)
    - data/raw_wiki/{page_id}.meta.json  (this model, serialized)

Design principle: NEVER modify raw data. This is the immutable document lake
that allows full re-processing without re-crawling (7+ hours at 50K pages).
"""

from __future__ import annotations
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field

class RawPageMeta(BaseModel):
    """
    API-provided metadata sidecar for a raw wiki page.

    Extracted from MediaWiki ``action=query&prop=revisions`` response.
    Stored alongside the raw wikitext file as ``{page_id}.meta.json``.
    """

    model_config = ConfigDict(
        extra="ignore",
        str_strip_whitespace=True,
    )

    page_id: int = Field(
        ...,
        description="MediaWiki page ID — unique, stable numeric identifier.",
    )
    title: str = Field(
        ...,
        description="Page title exactly as returned by the API.",
    )
    revision_id: int = Field(
        ...,
        description="Latest revision ID used for incremental change detection.",
    )
    revision_timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="ISO-8601 timestamp of the revision.",
    )
    namespace: int = Field(
        default=0,
        description="MediaWiki namespace ID. 0 = main content.",
    )
    categories: List[str] = Field(
        default_factory=list,
        description="Wiki categories extracted from the page (e.g., ['Resonators', '5-Star']).",
    )
    content_length_bytes: int = Field(
        default=0,
        description="Byte length of raw wikitext, used for quick size filtering.",
    )
    is_redirect: bool = Field(
        default=False,
        description="Whether the page is a redirect (starts with #REDIRECT).",
    )
    redirect_target: Optional[str] = Field(
        default=None,
        description="Target page title if this is a redirect.",
    )
    crawled_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when the page was crawled.",
    )


class RawPage(BaseModel):
    """
    Complete raw page record combining metadata + wikitext content.

    Used as in-memory representation during the Parse stage. The ``wikitext``
    field holds the full, unmodified MediaWiki markup. This model is NOT
    persisted directly — metadata and wikitext are stored as separate files.

    Typical usage::

        meta = RawPageMeta.model_validate_json(meta_path.read_text())
        wikitext = wikitext_path.read_text(encoding="utf-8")
        raw_page = RawPage(meta=meta, wikitext=wikitext)
    """

    model_config = ConfigDict(extra="ignore")

    meta: RawPageMeta = Field(
        ...,
        description="API-provided metadata sidecar.",
    )
    wikitext: str = Field(
        ...,
        description="Raw MediaWiki markup, unmodified from API response.",
    )
