"""
Type Contracts for MailQ

This package defines Protocol-based type contracts that decouple different layers
of the MailQ architecture.

Purpose:
- Prevent circular dependencies between digest/ and classification/
- Define clear interface contracts without coupling to concrete implementations
- Enable type-safe boundaries with mypy/pyright verification

Design Principles (P1-P4):
- P1 (Concepts Are Rooms): All contracts in ONE place (mailq/contracts/)
- P3 (Type Safety): Protocols enforce compile-time type checking
- P4 (Explicit Dependencies): Dependencies flow through contracts, not implementations

Architecture:
    classification/          digest/
         |                      |
         v                      v
    contracts/ (protocols only, no logic)
         ^                      ^
         |                      |
    adapters.py (conversion layer)

Re-exports for convenience:
"""

from mailq.contracts.enrichment import EntityDeduplicator, EntityEnricher, EntityFilter
from mailq.contracts.entities import (
    DigestDeadlineEntity,
    DigestEntity,
    DigestEventEntity,
    DigestFlightEntity,
    DigestLocation,
    DigestNotificationEntity,
    DigestPromoEntity,
    DigestReminderEntity,
)
from mailq.contracts.synthesis import DigestTimeline, TimelineSynthesizer

__all__ = [
    # Entity protocols
    "DigestEntity",
    "DigestLocation",
    "DigestFlightEntity",
    "DigestEventEntity",
    "DigestDeadlineEntity",
    "DigestReminderEntity",
    "DigestPromoEntity",
    "DigestNotificationEntity",
    # Enrichment protocols
    "EntityEnricher",
    "EntityDeduplicator",
    "EntityFilter",
    # Synthesis protocols
    "DigestTimeline",
    "TimelineSynthesizer",
]
