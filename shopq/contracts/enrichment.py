"""
Enrichment Operation Protocols

Defines interfaces for temporal decay, deduplication, and filtering operations
used by digest pipeline.

Design Principles (P1-P4):
- P2: Operations with side effects explicitly named (e.g., enrich_and_mutate)
- P3: Type-safe function signatures
- P4: Dependencies explicit in signatures
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from shopq.contracts.entities import DigestEntity


class EntityEnricher(Protocol):
    """Protocol for temporal enrichment operations."""

    def enrich_entities(
        self, entities: list[DigestEntity], now: datetime | None = None
    ) -> list[DigestEntity]:
        """Apply temporal decay enrichment to entities.

        Args:
            entities: List of entities to enrich
            now: Current time for temporal calculations (defaults to datetime.now())

        Returns:
            Enriched entities with resolved_importance, decay_reason, etc.

        Side Effects:
            None - returns new/modified entity instances
        """
        ...


class EntityDeduplicator(Protocol):
    """Protocol for entity deduplication."""

    def deduplicate(self, entities: list[DigestEntity]) -> list[DigestEntity]:
        """Remove duplicate entities based on signatures.

        Args:
            entities: List of entities to deduplicate

        Returns:
            Deduplicated list with highest-confidence entities

        Side Effects:
            None - pure function
        """
        ...


class EntityFilter(Protocol):
    """Protocol for filtering operations (expired events, self-emails, etc.)."""

    def __call__(self, entities: list[DigestEntity]) -> list[DigestEntity]:
        """Filter entities based on criteria.

        Args:
            entities: List of entities to filter

        Returns:
            Filtered list

        Side Effects:
            None - pure function
        """
        ...


# Function type aliases for common filter operations
EmailFilter = Callable[[list[dict]], list[dict]]
EntityFilterFn = Callable[[list[DigestEntity]], list[DigestEntity]]
