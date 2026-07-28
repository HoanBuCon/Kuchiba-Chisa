"""
Unit tests for Phase 2 AST-First & Config-Driven Sanitizer API (clean_and_filter_chunk).
"""

import json
import pytest
from app.infrastructure.ingestion.parsers.sanitizer import (
    clean_and_filter_chunk,
    get_rule_engine,
    should_drop_chunk,
    clean_entities,
)

def test_rule_engine_loading():
    engine = get_rule_engine()
    assert len(engine.strip_templates) > 0
    assert "stub" in engine.strip_templates
    assert "quote" in engine.unroll_rules


def test_clean_and_filter_chunk_stub_dropped():
    stub_chunk = json.dumps({
        "chunk_id": "test-stub-1",
        "page_title": "TestPage",
        "text_content": "{{Stub}}",
        "quality_score": 0.3,
        "token_count_approx": 3
    })
    result = clean_and_filter_chunk(stub_chunk)
    assert result is None


def test_clean_and_filter_chunk_valid_cleaned():
    valid_chunk = json.dumps({
        "chunk_id": "test-valid-1",
        "page_title": "Aalto",
        "canonical_name": "Aalto",
        "heading_path": "Aalto > Lead",
        "section_title": "**Lead**",
        "context_prefix": "[CHARACTER: Aalto | Section: Aalto > Lead]",
        "text_content": "'''{{PAGENAME}}''' is an enigmatic Information Broker from the mysterious organization known as the [[Black Shores]].<br>He works as a Consultant alongside Encore during covert intel-gathering missions across the New Federation.",
        "entities": ["Aalto\n\nHe", "Black Shores", "When Aalto"],
        "quality_score": 0.95,
        "token_count_approx": 30
    })
    result = clean_and_filter_chunk(valid_chunk)
    assert result is not None
    data = json.loads(result)
    
    # 1. {{PAGENAME}} substituted & bold wikitext converted to Markdown
    assert "**Aalto** is an enigmatic Information Broker" in data["text_content"]
    # 2. HTML <br> tag sanitized to newline
    assert "<br>" not in data["text_content"]
    # 3. Trash entities cleaned
    assert "Black Shores" in data["entities"]
    assert "When Aalto" not in data["entities"]
    # 4. Section title markdown stripped
    assert data["section_title"] == "Lead"
    # 5. Context prefix enriched
    assert "[ENTITY: Aalto | Section: Aalto > Lead]" in data["context_prefix"]


def test_clean_and_filter_borderline_flagging():
    borderline_chunk = json.dumps({
        "chunk_id": "test-borderline-1",
        "page_title": "Unknown Lore",
        "canonical_name": "Unknown Lore",
        "text_content": "This is a brief note regarding the ancient artifact found in the abyss during an expedition, which requires further study by researchers.",
        "quality_score": 0.6,
        "token_count_approx": 22
    })
    result = clean_and_filter_chunk(borderline_chunk)
    assert result is not None
    data = json.loads(result)
    assert data.get("needs_llm_rewrite") is True
