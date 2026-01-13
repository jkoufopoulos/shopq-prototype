"""
Temporal Enrichment - Apply Phase 4 temporal decay to entities before digest rendering.

Integration point: After entity extraction (Stage 1), before digest categorization (Stage 2).

This module:
1. Takes entities with stored_importance from Gemini classification
2. Applies temporal decay rules (resolve_temporal_importance)
3. Enriches entities with resolved_importance, decay_reason, was_modified
4. Logs decisions for telemetry and debugging

Usage:
    from mailq.classification.enrichment import enrich_entities_with_temporal_decay

    # After entity extraction
    entities = extract_entities(emails)

    # Apply temporal decay
    enriched_entities = enrich_entities_with_temporal_decay(entities)

    # Feed to digest categorizer (uses resolved_importance)
    digest = format_digest(enriched_entities)
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from threading import Lock
from typing import Any

from mailq.classification.models import DeadlineEntity, Entity, EventEntity
from mailq.classification.temporal import (
    EntityType,
    get_digest_section,
    should_show_in_digest,
)
from mailq.observability.logging import get_logger

logger = get_logger(__name__)

# HIGH FIX: Import fallback to prevent pipeline breakage if structured logging fails
try:
    from mailq.observability.structured import EventType
    from mailq.observability.structured import get_logger as get_structured_logger

    s_logger = get_structured_logger()  # Structured logger for temporal decisions
except (ImportError, AttributeError) as e:
    # Fallback: NoOp logger if structured logging unavailable
    logger.warning("Structured logging unavailable: %s", e)

    class NoOpLogger:
        def log_event(self, *args: Any, **kwargs: Any) -> None:
            pass

        def temporal_resolve(self, *args: Any, **kwargs: Any) -> None:
            pass

    s_logger = NoOpLogger()  # type: ignore[assignment]

# Thread-safe telemetry counters (for metrics)
_temporal_stats_lock = Lock()
_temporal_stats: dict[str, Any] = {
    "total_processed": 0,
    "escalated": 0,
    "downgraded": 0,
    "unchanged": 0,
    "hidden": 0,
    "parse_errors": 0,
    "decay_reasons": defaultdict(int),  # Prevents KeyError
}


def get_temporal_stats() -> dict[str, Any]:
    """Get temporal decay statistics for monitoring (thread-safe).

    Side Effects:
        None (pure function - builds local dict copy only)
    """
    with _temporal_stats_lock:
        return {
            **_temporal_stats,
            "decay_reasons": dict(_temporal_stats["decay_reasons"]),  # Copy nested dict
        }


def reset_temporal_stats() -> None:
    """
    Reset statistics (for testing, thread-safe)

    Side Effects:
        - Resets global _temporal_stats counters to zero
        - Clears decay_reasons dictionary
    """
    with _temporal_stats_lock:
        _temporal_stats["total_processed"] = 0
        _temporal_stats["escalated"] = 0
        _temporal_stats["downgraded"] = 0
        _temporal_stats["unchanged"] = 0
        _temporal_stats["hidden"] = 0
        _temporal_stats["parse_errors"] = 0
        _temporal_stats["decay_reasons"].clear()


def _extract_temporal_fields(entity: Entity) -> tuple[datetime | None, datetime | None]:
    """
    Extract temporal_start and temporal_end from entity.

    Returns:
        (temporal_start, temporal_end) as datetime objects or (None, None)
    """
    # EventEntity has event_time and event_end_time
    if isinstance(entity, EventEntity) and entity.event_time:
        # Convert event_time to datetime if it's a string
        if isinstance(entity.event_time, datetime):
            temporal_start = entity.event_time
        elif isinstance(entity.event_time, str):
            try:
                temporal_start = datetime.fromisoformat(entity.event_time.replace("Z", "+00:00"))
            except (ValueError, TypeError) as e:
                logger.warning(
                    f"temporal_parse_error: failed to parse event_time "
                    f"type={type(entity).__name__} error={type(e).__name__}"
                )
                # STRUCTURED LOG: Parse error
                s_logger.log_event(
                    EventType.TEMPORAL_PARSE_ERROR,
                    email_id=getattr(entity, "source_email_id", None),
                    timestamp=str(entity.event_time),
                    error=type(e).__name__,
                )
                with _temporal_stats_lock:
                    _temporal_stats["parse_errors"] += 1
                return (None, None)
        else:
            logger.error(
                "temporal_type_error: unexpected event_time "
                f"type={type(entity.event_time).__name__}"
            )
            return (None, None)

        # Extract event_end_time if available
        temporal_end = None
        if entity.event_end_time:
            if isinstance(entity.event_end_time, datetime):
                temporal_end = entity.event_end_time
            elif isinstance(entity.event_end_time, str):
                try:
                    temporal_end = datetime.fromisoformat(
                        entity.event_end_time.replace("Z", "+00:00")  # noqa: E501
                    )
                except (ValueError, TypeError) as e:
                    logger.warning(
                        f"temporal_parse_error: failed to parse event_end_time "
                        f"type={type(entity).__name__} error={type(e).__name__}"
                    )
                    # Don't fail the whole extraction, just log and continue without end time
                    temporal_end = None

        return (temporal_start, temporal_end)

    # DeadlineEntity has due_date
    if isinstance(entity, DeadlineEntity) and entity.due_date:
        if isinstance(entity.due_date, datetime):
            temporal_start = entity.due_date
        elif isinstance(entity.due_date, str):
            try:
                temporal_start = datetime.fromisoformat(entity.due_date.replace("Z", "+00:00"))
            except (ValueError, TypeError) as e:
                logger.warning(
                    f"temporal_parse_error: failed to parse due_date "
                    f"type={type(entity).__name__} error={type(e).__name__}"
                )
                with _temporal_stats_lock:
                    _temporal_stats["parse_errors"] += 1
                return (None, None)
        else:
            logger.error(
                f"temporal_type_error: unexpected due_date type={type(entity.due_date).__name__}"
            )
            return (None, None)

        # Deadlines don't have an end time (they're a point in time)
        return (temporal_start, None)

    # Could extract from source_subject patterns (e.g., "@ Mon Nov 21, 2025 6pm - 7pm")
    # For now, return None - entity extraction should populate these fields

    return (None, None)


def enrich_entity_with_temporal_decay(entity: Entity, now: datetime | None = None) -> Entity:
    """
    Enrich a single entity with temporal decay.

    Args:
        entity: Entity with stored_importance from ImportanceClassifier
        now: Current time (UTC), defaults to datetime.now(UTC)

    Returns:
        Entity enriched with:
        - resolved_importance (post-temporal decay)
        - stored_importance (original from ImportanceClassifier)
        - decay_reason (why it was modified)
        - was_modified (bool flag)
        - digest_section (NOW/SOON/LATER)
        - hide_in_digest (bool flag)

    Side Effects:
        - Modifies entity attributes in-place (stored_importance, resolved_importance, etc.)
        - Updates global _temporal_stats counters (thread-safe)
        - Writes structured log events (via s_logger)
        - Writes standard log entries for temporal decisions
    """
    if now is None:
        from datetime import UTC

        now = datetime.now(UTC)

    # Get stored importance (Stage 1 output from ImportanceClassifier)
    stored_importance = getattr(entity, "importance", "routine")

    # Get entity type (EntityType from temporal.py - NOT EmailType from storage/classification.py)
    email_type: EntityType = entity.type  # type: ignore[assignment]

    # Extract temporal fields
    temporal_start, temporal_end = _extract_temporal_fields(entity)

    # Check OTP/shipping logic first (notifications only)
    decay_result = None
    if email_type == "notification":
        from mailq.classification.temporal import resolve_otp_shipping_importance

        decay_result = resolve_otp_shipping_importance(entity, stored_importance, now)  # type: ignore[arg-type]

    # Apply standard temporal decay (events/deadlines) if OTP/shipping didn't apply
    if decay_result is None:
        from mailq.classification.temporal import resolve_temporal_importance

        decay_result = resolve_temporal_importance(
            email_type=email_type,
            stored_importance=stored_importance,  # type: ignore[arg-type]
            temporal_start=temporal_start,
            temporal_end=temporal_end,
            now=now,
        )

    # Enrich entity with Stage 2 fields
    entity.stored_importance = stored_importance  # Preserve Stage 1 output
    entity.resolved_importance = decay_result.resolved_importance  # Stage 2 output
    entity.decay_reason = decay_result.decay_reason
    entity.was_modified = decay_result.was_modified

    # Determine digest section (NOW / COMING_UP / WORTH_KNOWING)
    digest_section = get_digest_section(decay_result.resolved_importance)
    entity.digest_section = digest_section

    # Determine if should be hidden from digest (expired events)
    hide = not should_show_in_digest(
        email_type, decay_result.resolved_importance, temporal_end, now, temporal_start
    )
    entity.hide_in_digest = hide

    # Update telemetry (thread-safe)
    with _temporal_stats_lock:
        _temporal_stats["total_processed"] += 1

        if hide:
            _temporal_stats["hidden"] += 1

        if decay_result.was_modified:
            is_escalation = _is_escalation(stored_importance, decay_result.resolved_importance)
            if is_escalation:
                _temporal_stats["escalated"] += 1
            else:
                _temporal_stats["downgraded"] += 1

            # STRUCTURED LOG: Temporal decision
            hours_until = None
            if temporal_start:
                hours_until = (temporal_start - now).total_seconds() / 3600

            s_logger.temporal_resolve(
                email_id=getattr(entity, "source_email_id", None) or "unknown",
                decision="escalated" if is_escalation else "downgraded",
                reason=decay_result.decay_reason,
                hours_until=round(hours_until, 1) if hours_until is not None else None,
            )
        else:
            _temporal_stats["unchanged"] += 1

        # Track decay reasons (defaultdict prevents KeyError)
        _temporal_stats["decay_reasons"][decay_result.decay_reason] += 1

    # Log decision (no PII - subject lines removed for privacy)
    if decay_result.was_modified or hide:
        from datetime import UTC

        utc_time = now.astimezone(UTC) if now and now.tzinfo else now
        logger.info(
            f"temporal_resolve: type={email_type} stored={stored_importance} "
            f"resolved={decay_result.resolved_importance} reason={decay_result.decay_reason} "
            f"section={digest_section} modified={decay_result.was_modified} hidden={hide} "
            f"now_local={now.isoformat() if now else 'N/A'} "
            f"now_utc={utc_time.isoformat() if utc_time else 'N/A'}"
        )

    return entity


def enrich_entities_with_temporal_decay(
    entities: list[Entity], now: datetime | None = None
) -> list[Entity]:
    """
    Enrich a batch of entities with temporal decay.

    Args:
        entities: List of entities from entity extractor
        now: Current time (UTC), defaults to datetime.now(UTC)

    Returns:
        List of enriched entities with temporal decay applied

    Side Effects:
        - Modifies entity attributes in-place (via enrich_entity_with_temporal_decay)
        - Updates global _temporal_stats counters (thread-safe)
        - Writes structured log events (via s_logger)
        - Writes standard log entries for temporal decisions
    """
    if now is None:
        now = datetime.now(UTC)

    enriched = []
    for entity in entities:
        enriched_entity = enrich_entity_with_temporal_decay(entity, now)
        enriched.append(enriched_entity)

    return enriched


def filter_visible_entities(entities: list[Entity]) -> list[Entity]:
    """
    Filter out entities that should be hidden from digest (expired events).

    Args:
        entities: List of entities enriched with temporal decay

    Returns:
        List of entities where hide_in_digest == False
    """
    visible = [e for e in entities if not getattr(e, "hide_in_digest", False)]

    hidden_count = len(entities) - len(visible)
    if hidden_count > 0:
        logger.info(
            f"filtered_expired: total={len(entities)} visible={len(visible)} hidden={hidden_count}"
        )

    return visible


def group_by_digest_section(entities: list[Entity]) -> dict[str, list[Entity]]:
    """
    Group entities by digest section for rendering.

    Args:
        entities: List of entities enriched with temporal decay

    Returns:
        Dict mapping section name to list of entities:
        {
            'NOW': [critical entities],
            'COMING_UP': [time_sensitive entities],
            'WORTH_KNOWING': [routine entities]
        }
    """
    sections: dict[str, list[Entity]] = {
        "NOW": [],
        "COMING_UP": [],
        "WORTH_KNOWING": [],
    }

    for entity in entities:
        section = getattr(entity, "digest_section", "WORTH_KNOWING")
        if section in sections:
            sections[section].append(entity)
        else:
            # Fallback for unexpected section names
            logger.warning(f"Unknown digest section: {section}, defaulting to WORTH_KNOWING")
            sections["WORTH_KNOWING"].append(entity)

    return sections


def _is_escalation(stored: str, resolved: str) -> bool:
    """Check if resolved importance is higher than stored."""
    importance_order = {"routine": 0, "time_sensitive": 1, "critical": 2}
    return importance_order.get(resolved, 0) > importance_order.get(stored, 0)


# Guardrails (CI enforcement)


def enforce_temporal_guardrails(entity: Entity, now: datetime | None = None) -> list[str]:
    """
    Enforce temporal decay guardrails from STAGE_1_STAGE_2_CONTRACTS.md.

    Returns:
        List of guardrail violations (empty if all pass)
        Side Effects:
            Modifies local data structures
    """
    if now is None:
        now = datetime.now(UTC)

    violations: list[str] = []

    resolved = getattr(entity, "resolved_importance", None)
    email_type = entity.type

    if not resolved:
        return violations  # Not yet enriched

    # Guardrail: Newsletters cannot be critical (unless account_risk)
    if email_type == "newsletter" and resolved == "critical":
        violations.append(f"Newsletter marked as critical: {entity.source_subject[:50]}")

    # Guardrail: Expired events should not be time_sensitive or critical
    temporal_end = _extract_temporal_fields(entity)[1]
    if temporal_end:
        try:
            if isinstance(temporal_end, str):
                end_dt = datetime.fromisoformat(temporal_end.replace("Z", "+00:00"))
            else:
                end_dt = temporal_end

            if end_dt < now and resolved in ["time_sensitive", "critical"]:
                violations.append(
                    f"Expired event marked as {resolved}: {entity.source_subject[:50]}"
                )
        except (ValueError, AttributeError) as e:
            logger.debug("Could not parse temporal markers for entity: %s", e)

    return violations
