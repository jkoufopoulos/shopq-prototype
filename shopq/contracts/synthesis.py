"""
Timeline Synthesis Protocols

Defines interfaces for building importance-aware timelines from entities.

Design Principles (P1-P4):
- P1: All timeline contracts in ONE file
- P3: Type-safe timeline construction
- P4: Clear dependencies (entities → timeline)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from shopq.contracts.entities import DigestEntity


@dataclass
class DigestTimeline:
    """Timeline data structure for digest rendering.

    This is a concrete dataclass (not a protocol) because it's the
    OUTPUT format that both classification and digest agree on.
    """

    featured: list[DigestEntity] = field(default_factory=list)
    noise_breakdown: dict[str, int] = field(default_factory=dict)
    orphaned_time_sensitive: list[dict] = field(default_factory=list)
    total_emails: int = 0
    critical_count: int = 0
    time_sensitive_count: int = 0
    routine_count: int = 0

    def word_budget(self) -> tuple[int, int]:
        """Calculate adaptive word budget based on volume.

        Returns:
            (min_words, max_words) tuple
        """
        if self.total_emails <= 10:
            return (60, 90)
        if self.total_emails <= 30:
            return (90, 120)
        if self.total_emails <= 100:
            return (120, 150)
        return (150, 180)


class TimelineSynthesizer(Protocol):
    """Protocol for building importance-aware timelines."""

    def synthesize(
        self,
        entities: list[DigestEntity],
        total_emails: int,
        orphaned_time_sensitive: list[dict] | None = None,
    ) -> DigestTimeline:
        """Build timeline from entities.

        Args:
            entities: Enriched entities to include in timeline
            total_emails: Total email count for noise breakdown
            orphaned_time_sensitive: Time-sensitive emails that failed extraction

        Returns:
            Timeline with featured entities and noise summary

        Side Effects:
            None - pure function
        """
        ...

    def calculate_priority(self, entity: DigestEntity) -> float:
        """Calculate priority score for entity sorting.

        Args:
            entity: Entity to score

        Returns:
            Priority score (0.0-1.0)

        Side Effects:
            None - pure function
        """
        ...
