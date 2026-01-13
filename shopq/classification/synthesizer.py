"""

from __future__ import annotations

Timeline Synthesizer - Build importance-aware timeline from entities

Key principle: If an entity was successfully extracted, it's worth showing.

Timeline structure:
1. Critical items (bills, fraud alerts, financial) - ALL included, sorted by priority
2. Time-sensitive items (deliveries, appointments, events) - ALL included, sorted by priority
3. Routine items - grouped transparently in noise summary

Philosophy change (2025-11-01):
- REMOVED arbitrary limits on time-sensitive entities
- Filtering should happen at importance classification / entity extraction stage
- If we extracted 5 entities, show 5. If we extracted 50, show 50.
- The digest adapts to what actually matters in the inbox, not a fixed number
"""

import os
from dataclasses import dataclass, field
from datetime import UTC, datetime

from shopq.classification.models import (
    DeadlineEntity,
    Entity,
    EventEntity,
    FlightEntity,
    NotificationEntity,
    PromoEntity,
    ReminderEntity,
)
from shopq.observability.logging import get_logger
from shopq.shared.constants import get_friendly_type_name

logger = get_logger(__name__)


def _categorize_routine_by_type(emails: list[dict]) -> dict[str, int]:
    """
    Categorize routine emails by Gemini type for the "everything else" summary.

    Uses email.get("type") from Gemini classification directly.
    Groups by thread_id to count conversations, not individual messages.

    Args:
        emails: List of routine emails

    Returns:
        {'newsletters': 15, 'notifications': 3, 'receipts': 2, ...}
    """
    # Group by thread_id first to count conversations
    thread_to_type: dict[str, str] = {}

    for email in emails:
        thread_id = email.get("thread_id", email.get("id", ""))
        if not thread_id or thread_id in thread_to_type:
            continue

        email_type = email.get("type", "uncategorized")
        friendly_name = get_friendly_type_name(email_type)
        thread_to_type[thread_id] = friendly_name

    # Count by category
    category_counts: dict[str, int] = {}
    for category in thread_to_type.values():
        category_counts[category] = category_counts.get(category, 0) + 1

    return category_counts


@dataclass
class Timeline:
    """Timeline containing featured entities and noise summary"""

    featured: list[Entity] = field(default_factory=list)
    noise_breakdown: dict[str, int] = field(default_factory=dict)
    orphaned_time_sensitive: list[dict] = field(
        default_factory=list
    )  # Time-sensitive emails that failed extraction
    total_emails: int = 0
    critical_count: int = 0
    time_sensitive_count: int = 0
    routine_count: int = 0

    def word_budget(self) -> tuple[int, int]:
        """
        Calculate adaptive word budget based on volume.

        Returns:
            (min_words, max_words) tuple
        """
        if self.total_emails <= 10:
            # Light day: ~60-90 words
            return (60, 90)
        if self.total_emails <= 30:
            # Moderate day: ~90-120 words
            return (90, 120)
        if self.total_emails <= 100:
            # Busy day: ~120-150 words
            return (120, 150)
        # Email storm: ~150-180 words
        return (150, 180)


class TimelineSynthesizer:
    """Build importance-aware timeline from entities"""

    def __init__(self):
        """Initialize timeline synthesizer with DEBUG mode detection"""
        self.verbose = os.getenv("DEBUG", "").lower() in ("true", "1", "yes")

    def calculate_priority(self, entity: Entity) -> float:
        """
        Calculate priority score for entity.

        Factors:
        - Importance (critical=1.0, time_sensitive=0.7, routine=0.3)
        - Confidence (0.0-1.0)
        - Time sensitivity boost (future)

        Returns:
            Priority score (0.0-1.0)
        """
        # Base score from importance (prefer resolved over stored)
        # After Stage 3.5, entities have resolved_importance from temporal decay
        importance_scores = {"critical": 1.0, "time_sensitive": 0.7, "routine": 0.3}
        importance = getattr(entity, "resolved_importance", entity.importance)
        base_score = importance_scores.get(importance, 0.5)

        # Confidence weighting
        confidence_weight = entity.confidence

        # Final priority
        priority = base_score * confidence_weight

        return round(priority, 3)

    def build(self, entities: list[Entity], total_emails: int | None = None) -> Timeline:
        """
        Build timeline from entities.

        Args:
            entities: List of extracted entities
            total_emails: Total number of emails in inbox (for adaptive selection)

        Returns:
            Timeline with featured entities and noise breakdown

        Side Effects: None (pure function - builds and returns local data structures)
        """
        if not entities:
            return Timeline(total_emails=total_emails or 0)

        # Group by importance
        critical = [e for e in entities if e.importance == "critical"]
        time_sensitive = [e for e in entities if e.importance == "time_sensitive"]
        routine = [e for e in entities if e.importance == "routine"]

        # LOG: Show critical entities (always included) - DEBUG mode only
        if self.verbose and critical:
            logger.info(
                "\n[Timeline] %s critical entities (ALWAYS FEATURED):",
                len(critical),
            )
            for i, entity in enumerate(critical, 1):
                subject = getattr(entity, "source_subject", "No subject")[:60]
                logger.info("  %s. [CRITICAL] %s", i, subject)

        # Calculate priorities
        scored_time_sensitive = [
            (entity, self.calculate_priority(entity)) for entity in time_sensitive
        ]
        scored_time_sensitive.sort(key=lambda pair: pair[1], reverse=True)
        time_sensitive = [entity for entity, _ in scored_time_sensitive]

        # NEW APPROACH: Show ALL time-sensitive entities that were extracted
        # Reasoning: If entity extraction succeeded, it's worth showing
        # The filtering should happen earlier (importance classification, entity extraction)
        # not at timeline building stage
        total = total_emails or len(entities)
        max_time_sensitive = len(time_sensitive)  # Show all!

        # LOG: Show priority scores for all time-sensitive entities - DEBUG mode only
        if self.verbose:
            logger.info("\n%s", "=" * 80)
            logger.info(
                "[Timeline] ALL %s time-sensitive entities will be featured",
                len(time_sensitive),
            )
            logger.info(
                "[Timeline] Email volume: %s emails (no limit - showing all extracted entities)",
                total,
            )
            logger.info("%s", "=" * 80)
            for i, (entity, score) in enumerate(scored_time_sensitive, 1):
                subject = getattr(entity, "source_subject", "No subject")[:60]
                logger.info("  %2d. ✅ [%0.3f] %s", i, score, subject)
            logger.info("%s\n", "=" * 80)

        # Build featured list
        featured = []

        # 1. ALWAYS include ALL critical items (never limit these)
        featured.extend(critical)

        # 2. Add time-sensitive items (limited only on busy days)
        featured.extend(time_sensitive[:max_time_sensitive])

        # Create timeline
        return Timeline(
            featured=featured,
            total_emails=total,
            critical_count=len(critical),
            time_sensitive_count=len(time_sensitive),
            routine_count=len(routine),
        )

    def build_with_noise_summary(
        self,
        entities: list[Entity],
        all_emails: list[dict],
        importance_groups: dict[str, list[dict]],
    ) -> Timeline:
        """
        Build timeline with noise breakdown for transparent summary.

        Side Effects: None (pure function - builds and returns local data structures)

        Args:
            entities: Extracted entities
            all_emails: All emails in inbox
            importance_groups: Pre-classified importance groups from ImportanceClassifier

        Returns:
            Timeline with featured entities and noise breakdown
        """
        # Build basic timeline
        timeline = self.build(entities, total_emails=len(all_emails))

        # PRIORITY 3 FIX: Orphaned time-sensitive emails now treated as routine
        # This eliminates numbering confusion in the narrative

        # Create set of email IDs that successfully had entities extracted
        extracted_email_ids = {e.source_email_id for e in entities if e.source_email_id}

        # Find orphaned time-sensitive emails (no entity extracted)
        # These will be added to routine/noise instead of being mentioned separately
        time_sensitive_emails = importance_groups.get("time_sensitive", [])
        orphaned_threads = {}
        for email in time_sensitive_emails:
            email_id = email.get("id")
            thread_id = email.get("thread_id", email_id)

            if email_id not in extracted_email_ids and thread_id not in orphaned_threads:
                orphaned_threads[thread_id] = email

        orphaned_list = list(orphaned_threads.values())

        # Store for observability but don't include in narrative
        timeline.orphaned_time_sensitive = orphaned_list

        # Get routine emails for noise breakdown
        routine_emails = importance_groups.get("routine", [])

        # Add orphaned time-sensitive emails to routine for noise summary
        # This gives users visibility without breaking numbered reference system
        routine_emails = routine_emails + orphaned_list

        # Categorize routine emails by Gemini type (single source of truth)
        # NOTE: ImportanceClassifier removed - using inline categorization
        noise_breakdown = _categorize_routine_by_type(routine_emails)

        timeline.noise_breakdown = noise_breakdown

        return timeline


def format_orphaned_for_llm(orphaned_emails: list[dict], start_number: int = 1) -> str:
    """
    Format orphaned time-sensitive emails (no entity extracted) for LLM.

    Side Effects: None (pure function - builds and returns string)

    Args:
        orphaned_emails: List of time-sensitive email dicts without entities
        start_number: Starting number for references (continues from featured entities)

    Returns:
        Formatted string for LLM prompt
    """
    if not orphaned_emails:
        return "None"

    lines = []
    for i, email in enumerate(orphaned_emails, start=start_number):
        subject = email.get("subject", "No subject")
        snippet = email.get("snippet", "")[:100]  # First 100 chars
        lines.append(f"{i}. {subject}: {snippet}")

    return "\n".join(lines)


def format_featured_for_llm(featured: list[Entity]) -> str:
    """
    Format featured entities for LLM narrative generation with numbered references.

    Side Effects: None (pure function - builds and returns string)

    This function converts REAL entities (extracted from user's emails) into a structured
    format that the LLM uses to generate the digest. No hardcoded examples - this IS
    the example data the LLM sees.

    Output format (numbered for reliable linking):
    Most urgent:
    1. You have a fraud alert from Bank of America ($847.50 flagged)
    2. Your Amazon package is arriving today by 8 PM

    Also important:
    3. Flight UA345 tomorrow at 5 PM to Houston
    4. Dentist reminder: schedule a cleaning

    Returns:
        Formatted string for LLM prompt (real data from current batch)
    """
    if not featured:
        return "No featured items."

    # Group by importance
    critical_items = [e for e in featured if e.importance == "critical"]
    time_sensitive_items = [e for e in featured if e.importance == "time_sensitive"]

    parts = []
    item_number = 1

    if critical_items:
        parts.append("Most urgent:")
        for entity in critical_items:
            parts.append(f"{item_number}. {_entity_to_text(entity)}")
            item_number += 1

    if time_sensitive_items:
        if critical_items:
            parts.append("\nAlso important:")
        else:
            parts.append("Coming up:")

        for entity in time_sensitive_items:
            parts.append(f"{item_number}. {_entity_to_text(entity)}")
            item_number += 1

    return "\n".join(parts)


def _entity_to_text(entity: Entity) -> str:
    """Convert entity to natural language description with age context

    Side Effects: None (pure function - builds and returns string)
    """

    # Calculate email age
    age_context = ""
    if hasattr(entity, "timestamp") and entity.timestamp:
        # Ensure both datetimes are timezone-aware or both are naive
        now = datetime.now()
        entity_timestamp = entity.timestamp

        # If entity timestamp is aware, make now aware too
        if entity_timestamp.tzinfo is not None:
            now = datetime.now(UTC)
            # Convert entity timestamp to UTC if it has a different timezone
            if entity_timestamp.tzinfo != UTC:
                entity_timestamp = entity_timestamp.astimezone(UTC)
        # If entity timestamp is naive, make sure now is naive too
        elif now.tzinfo is not None:
            now = now.replace(tzinfo=None)

        age_days = (now - entity_timestamp).days

        # Add age context for old emails (lowered threshold from 7 days to 2 days)
        if age_days > 14:
            # Very old (>2 weeks)
            age_context = f"[email from {age_days} days ago] "
        elif age_days > 7:
            # Old (>1 week)
            age_context = f"[{age_days} days old] "
        elif age_days > 2:
            # Moderately old (>2 days) - still mark it
            age_context = f"[{age_days} days old] "

    if isinstance(entity, FlightEntity):
        parts = []
        if entity.flight_number:
            parts.append(f"Flight {entity.flight_number}")
        if entity.departure_time:
            parts.append(f"{entity.departure_time}")
        if entity.arrival and entity.arrival.city:
            parts.append(f"to {entity.arrival.city}")

        # Include weather context as available data (let LLM decide if/how to use it)
        base_text = " ".join(parts) if parts else entity.source_subject

        if hasattr(entity, "weather_context") and entity.weather_context:
            return f"{age_context}{base_text} [weather available: {entity.weather_context}]"

        return f"{age_context}{base_text}"

    if isinstance(entity, EventEntity):
        parts = []
        if entity.title:
            parts.append(entity.title)
        if entity.event_time:
            parts.append(f"at {entity.event_time}")
        base_text = " ".join(parts) if parts else entity.source_subject
        return f"{age_context}{base_text}"

    if isinstance(entity, DeadlineEntity):
        parts = []
        if entity.title:
            parts.append(entity.title)
        if entity.due_date:
            parts.append(f"due {entity.due_date}")
        if entity.amount:
            parts.append(f"({entity.amount})")
        base_text = " ".join(parts) if parts else entity.source_subject
        return f"{age_context}{base_text}"

    if isinstance(entity, ReminderEntity):
        if entity.action:
            return f"{age_context}Reminder: {entity.action}"
        return f"{age_context}{entity.source_subject}"

    if isinstance(entity, PromoEntity):
        parts = []
        if entity.merchant:
            parts.append(entity.merchant)
        if entity.offer:
            parts.append(entity.offer)
        if entity.expiry:
            parts.append(f"({entity.expiry})")
        base_text = " ".join(parts) if parts else entity.source_subject
        return f"{age_context}{base_text}"

    if isinstance(entity, NotificationEntity):
        # Use subject as primary description (more concise than snippet)
        fallback_message = entity.message or ""
        subject = entity.source_subject or fallback_message[:100]

        if entity.category == "fraud_alert":
            return f"{age_context}Fraud alert: {subject}"
        if entity.category == "delivery":
            return f"{age_context}{subject}"  # Subject already says "on the way" etc
        if entity.category == "bill":
            return f"{age_context}Bill: {subject}"
        if entity.category == "job_opportunity":
            return f"{age_context}{subject}"  # Subject already describes the job
        if entity.category == "claim":
            return f"{age_context}{subject}"  # Subject has claim number
        if entity.category == "reservation":
            return f"{age_context}{subject}"  # Subject describes reservation
        return f"{age_context}{subject}"

    return f"{age_context}{entity.source_subject}"
