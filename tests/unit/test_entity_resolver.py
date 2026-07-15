import pytest
import json
from pathlib import Path
from app.domain.services.rag.entity_resolver import EntityResolver

@pytest.fixture
def mock_dict_path(tmp_path):
    dict_file = tmp_path / "entities.json"
    data = {
        "Kuchiba Chisa": {
            "aliases": ["Chisa", "Black Swordsman"],
            "type": "Character",
            "region": "Septimont",
            "faction": "Startorch Academy",
            "related": ["Rover", "Instructor A"]
        },
        "Startorch Academy": {
            "aliases": ["The Academy"],
            "type": "Organization",
            "region": "Rinascita",
            "faction": "Huanglong",
            "related": ["Chisa"]
        }
    }
    dict_file.write_text(json.dumps(data), encoding="utf-8")
    return str(dict_file)

def test_entity_resolver_load(mock_dict_path):
    resolver = EntityResolver(dict_path=mock_dict_path)
    resolver.load()
    assert resolver._is_loaded is True
    assert "Kuchiba Chisa" in resolver.dictionary.entities
    assert "Startorch Academy" in resolver.dictionary.entities

def test_entity_resolver_extract(mock_dict_path):
    resolver = EntityResolver(dict_path=mock_dict_path)
    resolver.load()
    
    text = "Where did Chisa train? Was it at The Academy?"
    extracted = resolver.extract_entities(text)
    
    assert "Kuchiba Chisa" in extracted
    assert "Startorch Academy" in extracted
    assert len(extracted) == 2

def test_entity_resolver_expand(mock_dict_path):
    resolver = EntityResolver(dict_path=mock_dict_path)
    resolver.load()
    
    expanded = resolver.expand_entities({"Kuchiba Chisa"})
    assert "Kuchiba Chisa" in expanded
    assert "Septimont" in expanded
    assert "Startorch Academy" in expanded
    assert "Rover" in expanded
    assert "Instructor A" in expanded
    assert len(expanded) == 5

def test_entity_resolver_longest_match(tmp_path):
    # Test that "Black Swordsman" matches before "Black" or "Swordsman" if they were aliases
    dict_file = tmp_path / "entities.json"
    data = {
        "Kuchiba Chisa": {
            "aliases": ["Black Swordsman", "Swordsman"],
            "type": "Character",
        }
    }
    dict_file.write_text(json.dumps(data), encoding="utf-8")
    
    resolver = EntityResolver(dict_path=str(dict_file))
    resolver.load()
    
    text = "The Black Swordsman is cool."
    extracted = resolver.extract_entities(text)
    assert "Kuchiba Chisa" in extracted
