"""
Removes duplicate entities using signature-based deduplication.

Generates unique signatures (flight: airline+number+date, event: title+time) to
detect duplicates across multiple emails from same thread. Selects best entity by
importance and confidence.

Key: EntityDeduplicator.deduplicate() groups by signature and selects highest-ranked entity.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

from mailq.classification.models import (
    DeadlineEntity,
    Entity,
    EventEntity,
    FlightEntity,
    NotificationEntity,
    PromoEntity,
)


def _normalize_signature_part(value: Any) -> str:
    """Convert signature parts to a safe, comparable string."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip().lower()
    # Fall back to string conversion for other data types (e.g. datetime)
    return str(value).strip().lower()


def generate_signature(entity: Entity) -> str:
    """
    Generate unique signature for entity deduplication.

    Signatures:
    - Flight: airline + flight_number + departure_time
    - Event: title + event_time
    - Deadline: title + due_date + from_whom
    - Promo: merchant + offer
    - Default: type + source_subject
    """
    if isinstance(entity, FlightEntity):
        parts = [
            _normalize_signature_part(entity.airline),
            _normalize_signature_part(entity.flight_number),
            _normalize_signature_part(entity.departure_time),
        ]
        return f"flight_{'_'.join(parts)}"

    if isinstance(entity, EventEntity):
        parts = [
            _normalize_signature_part(entity.title),
            _normalize_signature_part(entity.event_time),
        ]
        return f"event_{'_'.join(parts)}"

    if isinstance(entity, DeadlineEntity):
        parts = [
            _normalize_signature_part(entity.title),
            _normalize_signature_part(entity.due_date),
            _normalize_signature_part(entity.from_whom),
        ]
        return f"deadline_{'_'.join(parts)}"

    if isinstance(entity, PromoEntity):
        parts = [
            _normalize_signature_part(entity.merchant),
            _normalize_signature_part(entity.offer),
        ]
        return f"promo_{'_'.join(parts)}"

    # Notification entities: use normalized subject (removes status/action words)
    if isinstance(entity, NotificationEntity):
        import re

        # Normalize subject by removing delivery status and action words
        subject = _normalize_signature_part(entity.source_subject)
        original_subject = subject  # Keep for fallback

        # Remove common status/action PHRASES (use word boundaries for precision)
        status_patterns = [
            r"\bdelivered\b",
            r"\bout for delivery\b",
            r"\bshipped\b",
            r"\barriving\s+(soon|today|tomorrow)?\b",
            r"\barriving\b",
            r"\brate your experience\b",
            r"\breview\s+request\b",
            r"\breview\b",
            r"\bconfirm\b",
            r"\btrack\b",
            r"\bhas been\b",
            r"\bwill be\b",
            r"\bis\s+(now|ready|available)\b",  # Only remove in specific contexts
            r"\bnow\b",
        ]

        for pattern in status_patterns:
            subject = re.sub(pattern, "", subject, flags=re.IGNORECASE)

        # Remove extra whitespace and punctuation debris
        subject = re.sub(r"[,;]+", "", subject)  # Remove dangling commas/semicolons
        subject = " ".join(subject.split())  # Normalize whitespace

        # VALIDATION: Ensure we have a meaningful subject after normalization
        if not subject or len(subject) < 3:
            # Fall back to original subject if normalization removed everything
            subject = original_subject

        # Extract category for additional uniqueness
        category = _normalize_signature_part(getattr(entity, "category", ""))

        # Include email ID prefix for sender differentiation
        # (prevents different senders from colliding)
        # Use source_email_id as a proxy for sender
        # (different emails = different senders usually)
        email_id = _normalize_signature_part(entity.source_email_id or "")[
            :20
        ]  # Truncate for safety

        return f"notification_{category}_{email_id}_{subject}"

    # Default signature: type + subject (guarding against missing subject)
    return (
        f"{_normalize_signature_part(entity.type)}_"
        f"{_normalize_signature_part(entity.source_subject)}"
    )


class EntityDeduplicator:
    """Deduplicate entities based on signatures and thread grouping"""

    def __init__(self) -> None:
        pass

    @staticmethod
    def _importance_rank(importance: str) -> int:
        ranking = {"critical": 3, "time_sensitive": 2, "routine": 1}
        return ranking.get(importance, 0)

    def _select_best_entity(self, group: list[Entity]) -> Entity:
        def sort_key(entity: Entity) -> tuple[int, float, float]:
            timestamp = getattr(entity, "timestamp", None)
            ts_value = timestamp.timestamp() if isinstance(timestamp, datetime) else float("-inf")
            return (
                self._importance_rank(getattr(entity, "importance", "")),
                getattr(entity, "confidence", 0.0),
                ts_value,
            )

        return max(group, key=sort_key)

    def deduplicate(self, entities: list[Entity]) -> list[Entity]:
        """
        Deduplicate entities using signature matching.

        Args:
            entities: List of entities to deduplicate

        Returns:
            Deduplicated list of entities (keeps highest confidence)

        Side Effects:
            None (pure function - returns new deduplicated list)
        """
        if not entities:
            return []

        # First, deduplicate within the same Gmail thread to avoid showing
        # multiple status updates for the same delivery/event.
        thread_groups = defaultdict(list)
        for entity in entities:
            thread_id = getattr(entity, "source_thread_id", "") or ""
            if thread_id:
                thread_groups[thread_id].append(entity)

        retained_ids = set()
        thread_deduped: list[Entity] = []

        for _thread_id, group in thread_groups.items():
            if len(group) == 1:
                entity = group[0]
                thread_deduped.append(entity)
                retained_ids.add(id(entity))
            else:
                best = self._select_best_entity(group)
                thread_deduped.append(best)
                retained_ids.add(id(best))

        # Add entities that did not belong to any thread group
        for entity in entities:
            if id(entity) not in retained_ids and not getattr(entity, "source_thread_id", None):
                thread_deduped.append(entity)

        # Group by signature on the thread-deduped list to catch near duplicates
        signature_groups = defaultdict(list)

        for entity in thread_deduped:
            sig = generate_signature(entity)
            signature_groups[sig].append(entity)

        # Keep one entity per signature (highest confidence)
        deduplicated = []

        for _sig, group in signature_groups.items():
            if len(group) == 1:
                deduplicated.append(group[0])
            else:
                best_entity = self._select_best_entity(group)
                deduplicated.append(best_entity)

        return deduplicated

    def deduplicate_by_thread(
        self, entities: list[Entity], email_threads: dict[str, str] | None = None
    ) -> list[Entity]:
        """
        Deduplicate entities that come from the same Gmail thread.

        Args:
            entities: List of entities
            email_threads: Optional mapping of email_id -> thread_id

        Returns:
            Deduplicated entities

        Side Effects:
            None (pure function - returns new deduplicated list)
        """
        if not email_threads:
            # If no thread info, fall back to signature-based deduplication
            return self.deduplicate(entities)

        # Group entities by thread
        thread_groups: dict[str, list[Entity]] = defaultdict(list)

        for entity in entities:
            thread_id = email_threads.get(entity.source_email_id, entity.source_email_id)
            thread_groups[thread_id].append(entity)

        # Within each thread, deduplicate by signature
        deduplicated = []

        for _thread_id, thread_entities in thread_groups.items():
            # Deduplicate within thread
            thread_deduped = self.deduplicate(thread_entities)
            deduplicated.extend(thread_deduped)

        return deduplicated

    def merge_similar_entities(
        self, entities: list[Entity], _similarity_threshold: float = 0.8
    ) -> list[Entity]:
        """
        Merge entities that are very similar (e.g., same flight with slightly different details).

        For MVP, this just calls deduplicate(). Can be enhanced later.
        """
        return self.deduplicate(entities)


def group_by_importance(entities: list[Entity]) -> dict[str, list[Entity]]:
    """
    Group entities by importance level.

    Returns:
        {
            'critical': [entity1, entity2, ...],
            'time_sensitive': [entity3, entity4, ...],
            'routine': [entity5, entity6, ...]
        }
    """
    groups: dict[str, list[Entity]] = {
        "critical": [],
        "time_sensitive": [],
        "routine": [],
    }

    for entity in entities:
        importance = entity.importance
        if importance in groups:
            groups[importance].append(entity)
        else:
            # Default to routine if unknown
            groups["routine"].append(entity)

    return groups
