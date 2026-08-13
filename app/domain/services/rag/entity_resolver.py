import json
import re
from typing import Set, Dict
from pathlib import Path
from app.domain.entities.dictionary import LoreEntityNode, EntityDictionary
from app.shared.utils.logger import get_logger

log = get_logger(__name__)

class EntityResolver:
    """
    In-memory Entity Resolver using Regex mapping over canonical names and aliases.
    """
    def __init__(self, dict_path: str = "data/lore/entities.json"):
        self.dict_path = Path(dict_path)
        self.dictionary: EntityDictionary = EntityDictionary()
        self._alias_map: Dict[str, str] = {}
        self._pattern: re.Pattern | None = None
        self._is_loaded = False
        
    def load(self):
        """Loads entities from JSON and builds the regex pattern."""
        if not self.dict_path.exists():
            log.warning("Entity dictionary not found. Entity resolution will be empty.", path=str(self.dict_path))
            return

        try:
            with open(self.dict_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            entities = {}
            alias_map = {}
            for key, val in data.items():
                # The dictionary structure is assumed to be: "Canonical Name": { "aliases": [...], "type": "..." }
                node = LoreEntityNode(canonical_name=key, **val)
                entities[key] = node
                alias_map[key.lower()] = key
                
                for alias in node.aliases:
                    alias_map[alias.lower()] = key
                    
            self.dictionary = EntityDictionary(entities=entities)
            self._alias_map = alias_map
            
            # Build regex pattern
            # Sort aliases by length descending to match longest phrases first
            sorted_aliases = sorted(alias_map.keys(), key=len, reverse=True)
            if sorted_aliases:
                escaped_aliases = [re.escape(a) for a in sorted_aliases]
                # Regex boundary \b might fail for CJK characters, but assuming Wuthering Waves aliases are Latin/English primarily,
                # or we can use a more robust matching if CJK is involved. We'll use \b for safety with English.
                # Since Chisa is Vietnamese/English mixed, let's use a standard lookaround if needed, but \b is a good start.
                pattern_str = r'\b(' + '|'.join(escaped_aliases) + r')\b'
                self._pattern = re.compile(pattern_str, re.IGNORECASE)
            
            self._is_loaded = True
            log.info("Entity dictionary loaded successfully", entities=len(entities), aliases=len(alias_map))
        except Exception as e:
            log.error("Failed to load entity dictionary", error=str(e))
            
    def extract_entities(self, text: str) -> Set[str]:
        """
        Extracts canonical entity names from the given text.
        """
        if not self._is_loaded or not self._pattern:
            return set()
            
        canonical_names = set()
        for match in self._pattern.finditer(text):
            matched_text = match.group(1).lower()
            canonical = self._alias_map.get(matched_text)
            if canonical:
                canonical_names.add(canonical)
                
        return canonical_names
        
    def expand_entities(self, canonical_names: Set[str]) -> Set[str]:
        """
        Expands a set of primary entities to include their related regions, factions, and related entities.
        """
        expanded = set(canonical_names)
        for name in canonical_names:
            node = self.dictionary.entities.get(name)
            if not node:
                continue
                
            if node.region:
                expanded.add(node.region)
            if node.faction:
                expanded.add(node.faction)
            if node.parent:
                expanded.add(node.parent)
            for related in node.related:
                expanded.add(related)
                
        return expanded
