import asyncio
import re
from datetime import datetime
from typing import Set, Dict, Optional

from app.domain.interfaces.repositories import IEntityRepository
from app.shared.utils.logger import get_logger

log = get_logger(__name__)

class EntityCacheManager:
    """
    Manages an in-memory dictionary (Trie/Regex) of Entities and Aliases.
    Polls the database periodically to reload the cache if changes occurred.
    """

    def __init__(self, entity_repo: IEntityRepository, poll_interval_seconds: int = 60):
        self.entity_repo = entity_repo
        self.poll_interval_seconds = poll_interval_seconds
        
        self._last_loaded_timestamp: Optional[datetime] = None
        self._alias_map: Dict[str, str] = {}
        self._pattern: Optional[re.Pattern] = None
        self._is_loaded: bool = False
        self._poll_task: Optional[asyncio.Task] = None

    async def start_polling(self):
        """Starts the background polling task."""
        if self._poll_task and not self._poll_task.done():
            return
            
        await self._load_cache() # Initial load
        self._poll_task = asyncio.create_task(self._poll_loop())
        log.info("EntityCacheManager polling started", interval=self.poll_interval_seconds)

    async def stop_polling(self):
        """Stops the background polling task."""
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
            log.info("EntityCacheManager polling stopped")

    async def _poll_loop(self):
        while True:
            await asyncio.sleep(self.poll_interval_seconds)
            try:
                latest_ts = await self.entity_repo.get_latest_update_timestamp()
                if latest_ts:
                    if not self._last_loaded_timestamp or latest_ts > self._last_loaded_timestamp:
                        log.info("Detected new entities, reloading cache...", previous_ts=self._last_loaded_timestamp, new_ts=latest_ts)
                        await self._load_cache(latest_ts)
            except Exception as e:
                log.error("Error during EntityCacheManager polling", error=str(e))

    async def _load_cache(self, current_ts: Optional[datetime] = None):
        """Reloads the entities from the repository and rebuilds the regex pattern."""
        try:
            entities = await self.entity_repo.get_all_entities()
            alias_map = {}
            
            for entity in entities:
                canonical = entity["canonical_name"]
                alias_map[canonical.lower()] = canonical
                for alias in entity.get("aliases", []):
                    alias_map[alias.lower()] = canonical

            sorted_aliases = sorted(alias_map.keys(), key=len, reverse=True)
            if sorted_aliases:
                escaped_aliases = [re.escape(a) for a in sorted_aliases]
                pattern_str = r'\b(' + '|'.join(escaped_aliases) + r')\b'
                self._pattern = re.compile(pattern_str, re.IGNORECASE)
            else:
                self._pattern = None

            self._alias_map = alias_map
            
            if not current_ts:
                current_ts = await self.entity_repo.get_latest_update_timestamp()
                
            self._last_loaded_timestamp = current_ts
            self._is_loaded = True
            log.info("EntityCacheManager reloaded successfully", entities_count=len(entities), aliases_count=len(alias_map))
        except Exception as e:
            log.error("Failed to load entity cache", error=str(e))

    def extract_entities(self, text: str) -> Set[str]:
        """
        Extracts canonical entity names from the given text using the cached regex pattern.
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
