from __future__ import annotations

from typing import Any, Optional, Protocol

class ICacheProvider(Protocol):
    """
    Domain adapter port for Caching and Distributed Locks.
    """

    async def get(self, key: str) -> Optional[str]:
        """Gets a string value from cache."""
        ...

    async def set(self, key: str, value: str, ttl: Optional[int] = None) -> None:
        """Sets a string value in cache with optional TTL."""
        ...

    async def get_json(self, key: str) -> Optional[Any]:
        """Gets a JSON parsed value from cache."""
        ...

    async def set_json(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Sets a JSON serializable value in cache with optional TTL."""
        ...

    async def delete(self, key: str) -> None:
        """Deletes a key from cache."""
        ...

    async def exists(self, key: str) -> bool:
        """Checks if a key exists in cache."""
        ...

    async def expire(self, key: str, ttl: int) -> None:
        """Sets an expiration TTL on a key."""
        ...

    async def acquire_lock(self, lock_key: str, ttl: int = 5, token: Optional[str] = None) -> Any:
        """Acquires a distributed lock. Returns token string or True if successful, None/False if failed."""
        ...

    async def release_lock(self, lock_key: str, token: Optional[str] = None) -> bool:
        """Releases a distributed lock safely using token comparison."""
        ...
