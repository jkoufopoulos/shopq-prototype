"""
Classification Temporal Processing

Consolidates time-based importance modulation:
- Deterministic temporal decay (Phase 4 algorithm)
- Expired event filtering

Phase 2 Architecture Cleanup - Issue #60
Merged from: decay.py, time_decay.py
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

import yaml  # type: ignore[import-untyped]
from dateutil import parser as date_parser

from mailq.observability.logging import get_logger

logger = get_logger(__name__)

ImportanceLevel = Literal["critical", "time_sensitive", "routine"]

# EntityType: Type of entity extracted from email (NOT EmailType from storage/classification.py)
# These are the entity types from models.py (FlightEntity, EventEntity, DeadlineEntity, etc.)
EntityType = Literal[
    "notification",
    "event",
    "deadline",
    "promo",
    "receipt",
    "flight",
    "reminder",
    "unknown",
]


# =============================================================================
# Section 1: Deterministic Temporal Decay (from decay.py)
# =============================================================================


def _load_temporal_config() -> dict:
    """
    Load temporal decay configuration from mailq_policy.yaml.

    Side Effects:
    - Reads config/mailq_policy.yaml file from filesystem

    Returns:
        Dict with keys: grace_period_hours, active_window_hours,
        upcoming_horizon_days, distant_threshold_days

    Raises:
        FileNotFoundError: If config file doesn't exist (returns defaults)
        KeyError: If temporal_decay section missing (returns defaults)
    """
    config_path = Path(__file__).parent.parent / "config" / "mailq_policy.yaml"

    if not config_path.exists():
        # Fallback to hardcoded defaults if config missing
        return {
            "grace_period_hours": 1,
            "active_window_hours": 1,
            "upcoming_horizon_days": 7,
            "distant_threshold_days": 7,
        }

    with open(config_path) as f:
        config = yaml.safe_load(f)

    return config.get(
        "temporal_decay",
        {
            "grace_period_hours": 1,
            "active_window_hours": 1,
            "upcoming_horizon_days": 7,
            "distant_threshold_days": 7,
        },
    )


# Load config once at module import time
_TEMPORAL_CONFIG = _load_temporal_config()


@dataclass
class TemporalDecayResult:
    """Result of temporal decay calculation."""

    resolved_importance: ImportanceLevel
    decay_reason: str
    decayed_at: datetime | None = None
    was_modified: bool = False


def resolve_temporal_importance(
    email_type: EntityType,
    stored_importance: ImportanceLevel,
    temporal_start: datetime | None,
    temporal_end: datetime | None,
    now: datetime | None = None,
) -> TemporalDecayResult:
    """
    Apply deterministic temporal decay rules to resolve final importance.

    Rules (in priority order):
    1. Expired (>1h past end) → routine (grace period for late digests)
    2. Active now (±1h window) → critical (happening soon/now)
    3. Upcoming ≤7 days → time_sensitive (or escalate from routine)
    4. Distant >7 days → routine (unless LLM said critical)

    Side Effects: None (pure function)

    Args:
        email_type: Type of email (only event/deadline use temporal)
        stored_importance: Original LLM classification
        temporal_start: Event/deadline start time (ISO 8601 UTC)
        temporal_end: Event end time (None for deadlines)
        now: Current time (defaults to utcnow, injectable for testing)

    Returns:
        TemporalDecayResult with resolved_importance and reason

    Examples:
        >>> # Expired event
        >>> result = resolve_temporal_importance(
        ...     "event",
        ...     "time_sensitive",
        ...     datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc),
        ...     datetime(2025, 1, 1, 13, 0, tzinfo=timezone.utc),
        ...     now=datetime(2025, 1, 1, 15, 0, tzinfo=timezone.utc)
        ... )
        >>> result.resolved_importance
        'routine'
        >>> result.decay_reason
        'temporal_expired'

        >>> # Active event (starting in 30 min)
        >>> now = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)
        >>> result = resolve_temporal_importance(
        ...     "event",
        ...     "routine",
        ...     now + timedelta(minutes=30),
        ...     now + timedelta(hours=1, minutes=30),
        ...     now=now
        ... )
        >>> result.resolved_importance
        'critical'
    """
    if now is None:
        now = datetime.now(UTC)

    # Validate timezone-aware datetime to prevent comparison errors
    if now.tzinfo is None:
        raise ValueError(
            "now parameter must be timezone-aware. "
            "Use datetime.now(UTC) or ensure tzinfo is set. "
            "This prevents TypeError when comparing with temporal_start/temporal_end."
        )

    # NOTE: OTP temporal logic removed - OTPs handled by guardrails (force_critical)
    # and digest temporal decay (skip from digest). See T0_T1_IMPORTANCE_CLASSIFICATION.md

    # Shipping temporal logic (notification subtype) is handled separately in
    # resolve_otp_shipping_importance() which is called by enrichment.py

    # Non-temporal types: pass through stored importance
    if email_type not in ["event", "deadline", "notification"]:
        return TemporalDecayResult(
            resolved_importance=stored_importance,
            decay_reason="non_temporal_type",
            was_modified=False,
        )

    # Missing temporal_start: can't apply decay
    if temporal_start is None:
        return TemporalDecayResult(
            resolved_importance=stored_importance,
            decay_reason="no_temporal_data",
            was_modified=False,
        )

    # Ensure timezone-aware
    if temporal_start.tzinfo is None:
        temporal_start = temporal_start.replace(tzinfo=UTC)
    if temporal_end and temporal_end.tzinfo is None:
        temporal_end = temporal_end.replace(tzinfo=UTC)

    # Rule 1: Expired → routine (grace period from config)
    # Use temporal_end if available, otherwise use temporal_start (for events without end time)
    grace_period = timedelta(hours=_TEMPORAL_CONFIG["grace_period_hours"])
    expiration_time = temporal_end if temporal_end else temporal_start
    if expiration_time < now - grace_period:
        return TemporalDecayResult(
            resolved_importance="routine",
            decay_reason="temporal_expired",
            decayed_at=now,
            was_modified=(stored_importance != "routine"),
        )

    # Rule 2: Active now → critical (active window from config)
    # Event starting within next hour OR already started but not ended
    active_window = timedelta(hours=_TEMPORAL_CONFIG["active_window_hours"])
    if temporal_start <= now + active_window and (
        not temporal_end or now <= temporal_end + active_window
    ):
        return TemporalDecayResult(
            resolved_importance="critical",
            decay_reason="temporal_active",
            was_modified=(stored_importance != "critical"),
        )

    # Rule 3: Coming up ≤upcoming_horizon → time_sensitive (or escalate)
    upcoming_horizon = timedelta(days=_TEMPORAL_CONFIG["upcoming_horizon_days"])
    if temporal_start <= now + upcoming_horizon:
        # Escalate routine to time_sensitive, preserve critical
        resolved = _escalate_importance(stored_importance, "time_sensitive")
        return TemporalDecayResult(
            resolved_importance=resolved,
            decay_reason="temporal_upcoming",
            was_modified=(resolved != stored_importance),
        )

    # Rule 4: Distant >7 days → routine (unless LLM overrode to critical)
    if stored_importance == "critical":
        # Trust LLM for critical even if distant (e.g., flight cancellation notice)
        return TemporalDecayResult(
            resolved_importance="critical",
            decay_reason="temporal_distant_but_critical",
            was_modified=False,
        )
    return TemporalDecayResult(
        resolved_importance="routine",
        decay_reason="temporal_distant",
        was_modified=(stored_importance != "routine"),
    )


def _escalate_importance(current: ImportanceLevel, target: ImportanceLevel) -> ImportanceLevel:
    """
    Escalate importance monotonically (never downgrade).

    Order: routine < time_sensitive < critical

    Side Effects: None (pure function)
    """
    order = {"routine": 0, "time_sensitive": 1, "critical": 2}
    return target if order[target] > order[current] else current


def resolve_otp_shipping_importance(
    entity: Any,
    stored_importance: ImportanceLevel,
    now: datetime,
) -> TemporalDecayResult | None:
    """
    Apply temporal decay for shipping notifications.

    NOTE: OTP temporal logic has been removed. OTPs are handled by:
    - Guardrails (force_critical for T0 importance)
    - Digest temporal decay (skip - OTPs never appear in digest)
    See: docs/features/T0_T1_IMPORTANCE_CLASSIFICATION.md

    Side Effects: None (pure function)

    Args:
        entity: Entity object (must have type="notification")
        stored_importance: Importance from Stage 1 classifier
        now: Current time (timezone-aware)

    Returns:
        TemporalDecayResult if shipping logic applies, None otherwise

    Shipping Logic:
        - ship_status == "out_for_delivery" → critical
        - ship_status == "delivered" and delivered_at < now - 24h → routine
        - ship_status == "processing" → preserve stored_importance
    """
    # Handle shipping temporal logic
    if hasattr(entity, "ship_status") and entity.ship_status:
        if entity.ship_status == "out_for_delivery":
            # Package arriving today → critical
            return TemporalDecayResult(
                resolved_importance="critical",
                decay_reason="shipping_out_for_delivery",
                was_modified=(stored_importance != "critical"),
            )
        if (
            entity.ship_status == "delivered"
            and hasattr(entity, "delivered_at")
            and entity.delivered_at
        ):
            try:
                delivered = entity.delivered_at
                if isinstance(delivered, str):
                    delivered = datetime.fromisoformat(delivered.replace("Z", "+00:00"))
                if delivered.tzinfo is None:
                    delivered = delivered.replace(tzinfo=UTC)

                if now - delivered > timedelta(hours=24):
                    # Delivered >24h ago → routine
                    return TemporalDecayResult(
                        resolved_importance="routine",
                        decay_reason="shipping_delivered_old",
                        was_modified=(stored_importance != "routine"),
                    )
            except (ValueError, AttributeError):
                pass
        # processing/in_transit → fall through, preserve stored importance

    return None  # No OTP/shipping logic applies


def should_show_in_digest(
    email_type: EntityType,
    resolved_importance: ImportanceLevel,  # noqa: ARG001
    temporal_end: datetime | None,
    now: datetime | None = None,
    temporal_start: datetime | None = None,
) -> bool:
    """
    Determine if email should appear in digest based on temporal state.

    Expired events (>1h past end) should be hidden or archived.

    Side Effects: None (pure function)

    Args:
        email_type: Type of email
        resolved_importance: After temporal decay
        temporal_end: Event end time
        now: Current time
        temporal_start: Event start time (used as fallback if end time missing)

    Returns:
        True if should appear in digest, False to hide/archive
    """
    if now is None:
        now = datetime.now(UTC)

    # Non-events always show
    if email_type not in ["event", "deadline"]:
        return True

    # Use temporal_end if available, otherwise use temporal_start (for events without end time)
    expiration_time = temporal_end if temporal_end else temporal_start

    # If no temporal data at all, show based on importance
    if expiration_time is None:
        return True

    # Ensure timezone-aware
    if expiration_time.tzinfo is None:
        expiration_time = expiration_time.replace(tzinfo=UTC)

    # Hide expired events (>1h past end/start)
    return not expiration_time < now - timedelta(hours=1)


def get_digest_section(resolved_importance: ImportanceLevel) -> str:
    """
    Map resolved importance to digest section.

    Side Effects: None (pure function)

    Returns:
        "TODAY", "COMING_UP", or "WORTH_KNOWING"
    """
    mapping = {"critical": "TODAY", "time_sensitive": "COMING_UP", "routine": "WORTH_KNOWING"}
    return mapping[resolved_importance]


# For backward compatibility with existing code
def deterministic_temporal_updownrank(
    email_type: EntityType,
    stored_importance: ImportanceLevel,
    temporal_start: datetime | None,
    temporal_end: datetime | None,
    now: datetime | None = None,
) -> tuple[ImportanceLevel, str]:
    """
    Legacy function name. Use resolve_temporal_importance() instead.

    Side Effects: None (pure function)

    Returns:
        (resolved_importance, decay_reason)
    """
    result = resolve_temporal_importance(
        email_type, stored_importance, temporal_start, temporal_end, now
    )
    return (result.resolved_importance, result.decay_reason)


# =============================================================================
# Section 2: Expired Event Filtering (from time_decay.py)
# =============================================================================


def is_expired_event(email: dict, now: datetime | None = None) -> bool:
    """
    Check if email is for an event that already happened.

    Side Effects: None (pure function)

    Args:
        email: Email dict with 'subject', 'snippet', 'date', 'temporal_start'
        now: Current datetime (defaults to datetime.now(), injectable for testing)

    Returns:
        True if email should be EXCLUDED from digest (event expired)
        False if email should be included (event still relevant or not an event)
    """
    if now is None:
        now = datetime.now()

    # Ensure now is timezone-naive for comparison
    if now.tzinfo:
        now = now.replace(tzinfo=None)

    subject = email.get("subject", "").lower()
    snippet = email.get("snippet", "").lower()
    email_date_str = email.get("date", "")

    # Pattern 0: Check temporal_start field (from CSV ground truth data)
    # ONLY apply to events - receipts with temporal_start shouldn't be filtered
    email_type = email.get("type", "")
    is_event_type = email_type in ["event", "calendar"]

    temporal_start = email.get("temporal_start", "")
    if temporal_start and is_event_type:
        try:
            event_time = date_parser.parse(temporal_start)
            # Make timezone-naive for comparison
            if event_time.tzinfo:
                event_time = event_time.replace(tzinfo=None)
            # Event expired if it ended more than 1 hour ago
            if event_time < now - timedelta(hours=1):
                return True  # Expired
        except Exception:
            pass  # Fall through to other patterns

    # Parse email send date
    email_date = None
    if email_date_str:
        try:
            email_date = date_parser.parse(email_date_str)
            # Make timezone-naive for comparison
            if email_date.tzinfo:
                email_date = email_date.replace(tzinfo=None)
        except Exception as e:
            # Can't parse date → safe default: keep email (not expired)
            logger.warning("Failed to parse email date '%s': %s", email_date_str, e)
            return False

    # Pattern 1: Calendar acceptance/decline for past events
    # Example: "Accepted: Victor <> Justin in town in NYC @ Tue Nov 18, 2025 (Justin)"
    # If sent on Oct 31 but event is Nov 18, this is NOT expired (keep it)
    # But if sent on Nov 19, it IS expired (filter it)
    if (
        "accepted:" in subject
        or "declined:" in subject
        or "you accepted" in snippet
        or "you declined" in snippet
    ):
        event_date = _extract_event_date_from_calendar(subject)
        if event_date and event_date < now - timedelta(hours=2):  # 2hr buffer for same-day events
            return True

    # Pattern 2: "Starts in X" reminder that already passed
    # Example: "Drawing Hive starts in 1 hour" sent yesterday
    # Calculate when event was supposed to start
    if "starts in" in subject or "don't forget" in subject or "starts in" in snippet:
        trigger_time = _calculate_event_start_time(subject + " " + snippet, email_date)
        if trigger_time and trigger_time < now:
            return True  # Event already started → expired

    # Pattern 3: Past event notifications
    # Example: "Notification: Event @ Wed Oct 29" when today is Nov 1
    if "notification:" in subject:
        event_date = _extract_event_date_from_notification(subject)
        if event_date and event_date < now - timedelta(hours=2):
            return True  # Event in past → expired

    # Pattern 4: General past date in subject (last resort)
    # Be conservative - only filter if very clearly in the past
    # Example: "Your Friday afternoon order" on Saturday → don't filter (might be recent)
    # Example: "Event on Oct 29" on Nov 1 → filter

    return False  # Default: include email (don't filter)


def filter_expired_events(emails: list[dict], now: datetime | None = None) -> list[dict]:
    """
    Filter out expired events from a list of emails.

    Side Effects: None (pure function - returns new filtered list)

    Args:
        emails: List of email dicts
        now: Current datetime (for testing)

    Returns:
        Filtered list with expired events removed
    """
    return [email for email in emails if not is_expired_event(email, now)]


def _extract_event_date_from_calendar(subject: str) -> datetime | None:
    """
    Extract event date from calendar invitation subject.

    Examples:
        "Accepted: Victor @ Tue Nov 18, 2025 (Justin)" → Nov 18, 2025
        "Notification: Event @ Wed Oct 29, 2025 7pm" → Oct 29, 2025
        "Notification: Event @ Fri Nov 1, 2025 10am" → Nov 1, 2025 10:00
    """
    # Pattern: @ Day Month DD, YYYY or @ Day Month DD
    # Example: @ Tue Nov 18, 2025 or @ Wed Oct 29, 2025 7pm
    match = re.search(
        r"@\s+(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+(\w+)\s+(\d+)(?:,?\s+(\d{4}))?(?:\s+(\d+)([ap]m))?",
        subject,
        re.IGNORECASE,
    )
    if match:
        month_str = match.group(1)
        day = int(match.group(2))
        year = int(match.group(3)) if match.group(3) else datetime.now().year
        hour_str = match.group(4)  # Hour (if present)
        am_pm = match.group(5)  # am/pm (if present)

        try:
            # Parse "Nov 18, 2025" → datetime
            date_str = f"{month_str} {day}, {year}"
            event_dt = date_parser.parse(date_str)

            # Add time if present (e.g., "10am")
            if hour_str and am_pm:
                hour = int(hour_str)
                if am_pm.lower() == "pm" and hour != 12:
                    hour += 12
                elif am_pm.lower() == "am" and hour == 12:
                    hour = 0
                event_dt = event_dt.replace(hour=hour)

            return event_dt
        except (ValueError, AttributeError, TypeError) as e:
            logger.debug("Could not parse temporal data from event: %s", e)

    return None


def _extract_event_date_from_notification(subject: str) -> datetime | None:
    """
    Extract event date from notification subject.

    Examples:
        "Notification: J & V Catch-up @ Fri Oct 31, 2025 2pm" → Oct 31, 2025 14:00
    """
    # Use same pattern as calendar
    return _extract_event_date_from_calendar(subject)


def _calculate_event_start_time(text: str, email_date: datetime | None) -> datetime | None:
    """
    Calculate when event starts based on "starts in X" text and email send time.

    Examples:
        "Drawing Hive starts in 1 hour" sent at 2025-10-30 22:00 → 2025-10-30 23:00
        "Event starts in 1 day" sent at 2025-10-30 12:00 → 2025-10-31 12:00
    """
    if not email_date:
        return None

    # Pattern: "starts in X hour(s)"
    match = re.search(r"starts in (\d+)\s*(hour|hr)s?", text, re.IGNORECASE)
    if match:
        hours = int(match.group(1))
        return email_date + timedelta(hours=hours)

    # Pattern: "starts in X day(s)"
    match = re.search(r"starts in (\d+)\s*days?", text, re.IGNORECASE)
    if match:
        days = int(match.group(1))
        return email_date + timedelta(days=days)

    # Pattern: "starts in X minute(s)"
    match = re.search(r"starts in (\d+)\s*(minute|min)s?", text, re.IGNORECASE)
    if match:
        minutes = int(match.group(1))
        return email_date + timedelta(minutes=minutes)

    return None
