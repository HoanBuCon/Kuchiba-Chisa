"""
Unit tests for wikitext_parser module (pypandoc engine + fallback).
"""

from __future__ import annotations
import pytest
from app.infrastructure.ingestion.parsers.wikitext_parser import convert_wikitext_to_markdown


def test_convert_wikitext_basic():
    raw = "'''Bold Text''' and ''Italic Text''"
    md = convert_wikitext_to_markdown(raw)
    assert "Bold Text" in md
    assert "Italic Text" in md


def test_convert_wikitext_heading():
    raw = "== Heading Title =="
    md = convert_wikitext_to_markdown(raw)
    assert "Heading Title" in md


def test_convert_wikitext_force_regex():
    raw = "'''Bold Text''' and [[Page Link|Display]]"
    md_regex = convert_wikitext_to_markdown(raw, force_regex=True)
    assert "**Bold Text**" in md_regex
    assert "Display" in md_regex


def test_convert_wikitext_empty():
    assert convert_wikitext_to_markdown("") == ""
    assert convert_wikitext_to_markdown("   ") == ""
