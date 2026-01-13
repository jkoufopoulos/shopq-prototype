"""
Provides TTL-based in-memory caching for pipeline optimization.

Caches parsed emails and classification results to reduce LLM calls and parsing
overhead. Entries expire automatically after configurable TTL with telemetry tracking.

Key: TTLCache[T] with get/put operations and automatic expiry based on timestamps.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Generic, TypeVar

from mailq.observability.telemetry import counter, log_event

T = TypeVar("T")


@dataclass
class CacheEntry(Generic[T]):
    """Cache entry with value and expiry timestamp."""

    value: T
    expires_at: float


class TTLCache(Generic[T]):
    """Simple TTL-based cache with automatic expiry."""

    def __init__(self, name: str, ttl_seconds: float = 3600.0):
        """
        Initialize cache.

        Args:
            name: Cache name for telemetry (e.g., "parsed_email", "classification")
            ttl_seconds: Time-to-live for cache entries (default 1 hour)
        """
        self.name = name
        self.ttl_seconds = ttl_seconds
        self._store: dict[str, CacheEntry[T]] = {}

    def get(self, key: str) -> T | None:
        """
        Get value from cache if not expired.

        Returns None if key not found or expired.
        """
        entry = self._store.get(key)
        if entry is None:
            counter(f"cache.{self.name}.miss")
            return None

        now = time.time()
        if now > entry.expires_at:
            # Expired, remove and return None
            del self._store[key]
            counter(f"cache.{self.name}.expired")
            log_event("cache.expired", cache=self.name, key_hash=self._hash_key(key))
            return None

        counter(f"cache.{self.name}.hit")
        return entry.value

    def put(self, key: str, value: T) -> None:
        """
        Store value in cache with TTL

        Side Effects:
            - Writes to _store dict (in-memory cache)
            - Increments telemetry counter (cache.{name}.write)
        """
        expires_at = time.time() + self.ttl_seconds
        self._store[key] = CacheEntry(value=value, expires_at=expires_at)
        counter(f"cache.{self.name}.write")

    def invalidate(self, key: str) -> None:
        """
        Remove key from cache

        Side Effects:
            - Deletes entry from _store dict (in-memory cache)
            - Increments telemetry counter (cache.{name}.invalidate)
        """
        if key in self._store:
            del self._store[key]
            counter(f"cache.{self.name}.invalidate")

    def clear(self) -> None:
        """
        Clear all entries

        Side Effects:
            - Clears entire _store dict (in-memory cache)
            - Writes telemetry event with entry count
        """
        count = len(self._store)
        self._store.clear()
        log_event("cache.cleared", cache=self.name, count=count)

    def stats(self) -> dict[str, int]:
        """Get cache statistics."""
        now = time.time()
        active = sum(1 for entry in self._store.values() if now <= entry.expires_at)
        expired = len(self._store) - active

        return {
            "total_entries": len(self._store),
            "active_entries": active,
            "expired_entries": expired,
        }

    def _hash_key(self, key: str) -> str:
        """Return first 12 chars of key for safe logging."""
        return key[:12] if len(key) > 12 else key


# Global caches for pipeline stages
PARSED_EMAIL_CACHE = TTLCache[object](name="parsed_email", ttl_seconds=3600.0)
CLASSIFICATION_CACHE = TTLCache[object](name="classification", ttl_seconds=1800.0)
