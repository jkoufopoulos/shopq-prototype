"""
T0 Section Assignment - Intrinsic Email Classification

This module assigns sections based ONLY on intrinsic email properties,
WITHOUT considering evaluation time. This is the "T0" classification -
what section should this email go to based on what it IS, not when we're
looking at it.

T0 → Temporal Decay → T1/T2
(intrinsic)  (time-based)  (final sections)

This separation enables:
- Testable intrinsic classification (independent of time)
- Modular temporal decay (separate concern)
- Clear ground truth annotations (T0 = properties, T1 = time-adjusted)

Selection Criteria (T0):
- CRITICAL: High-stakes, urgent by nature (not by time)
- TODAY: Events, deliveries, experiential purchases (regardless of when)
- COMING_UP: Deadlines, future events (intrinsic future signal)
- WORTH_KNOWING: Financial statements, action items, personal messages
- NOISE: Newsletters, promotions, receipts, routine notifications

Principles:
- P1: Single concept (intrinsic classification only)
- P2: No side effects (pure function)
- P3: Type-safe (all inputs/outputs typed)
- P4: No temporal dependencies (decoupled from evaluation time)
"""

from __future__ import annotations

from typing import Any

from shopq.observability.logging import get_logger

logger = get_logger(__name__)

# ============================================================================
# GENERALIZABLE SECTION MAPPING
# ============================================================================
# Map (email_type, importance) → section
# This is the authoritative mapping - no vendor-specific patterns needed

# Default section by email type (before importance/temporal adjustment)
# IMPORTANT: Only use EmailTypes from storage/classification.py:
# otp, newsletter, notification, receipt, event, promotion, message, uncategorized
TYPE_DEFAULT_SECTION: dict[str, str] = {
    "otp": "critical",  # One-time passwords always critical
    "event": "today",  # Events → today (temporal decay adjusts)
    "message": "worth_knowing",  # Personal messages worth knowing
    "notification": "noise",  # Generic notifications → noise (pattern/importance elevates)
    "receipt": "noise",  # Receipts → noise (purchase confirmations)
    "newsletter": "noise",  # Newsletters → noise
    "promotion": "noise",  # Promotions → noise
    "uncategorized": "noise",  # Unknown → noise (safe default)
}

# Importance-based section mapping
# The classifier assigns importance - we trust it for section placement
# NOTE: time_sensitive is handled separately in STEP 1b to allow event-specific logic
IMPORTANCE_TO_SECTION: dict[str, str] = {
    "critical": "critical",  # Immediate action needed
    # "time_sensitive" handled in STEP 1b (events go to "today", others to "coming_up")
    # "routine" falls through to type-based defaults
}

# Minimal pattern list for edge cases the classifier might miss
# These are safety nets, not the primary classification logic
ELEVATED_PATTERNS = [
    "action required",
    "action needed",
]


def assign_section_t0(
    email: dict[str, Any],
    temporal_ctx: dict[str, Any] | None,
) -> str:
    """
    Assign T0 section based on intrinsic email properties.

    T0 classification does NOT consider current time - only what the email IS.
    Priority order:
    1. Importance (critical/time_sensitive from classifier)
    2. Type + temporal context (events with dates)
    3. Type defaults (message, receipt, etc.)

    Args:
        email: Email dict with 'importance', 'type', 'subject', 'snippet', 'from'
        temporal_ctx: Temporal context (event_time, delivery_date, etc.)

    Returns:
        T0 section: "critical" | "today" | "coming_up" | "worth_knowing" | "noise"

    Side Effects: None (pure function)
    """
    importance = email.get("importance", "routine")
    email_type = email.get("type", "")
    subject = email.get("subject", "")
    subject_lower = subject.lower()

    # ========================================================================
    # STEP 1a: Critical importance → critical section
    # ========================================================================
    # The classifier assigns importance based on email content analysis.
    # critical = immediate action needed (security alerts, fraud, OTPs)
    if importance in IMPORTANCE_TO_SECTION:
        return IMPORTANCE_TO_SECTION[importance]

    # ========================================================================
    # STEP 1b: Time-sensitive handling (events vs non-events)
    # ========================================================================
    # Events that are time_sensitive should go to "today" and let temporal
    # decay adjust them to coming_up if they're in the future.
    # Non-event time_sensitive emails with explicit dates → coming_up
    # Non-event time_sensitive emails without dates → worth_knowing
    if importance == "time_sensitive":
        if email_type == "event":
            # Events → today (temporal decay adjusts based on actual event date)
            return "today"
        # Non-events: check if we have an extracted expiration/event date
        # If yes → coming_up (T1 decay can promote to today if <48h)
        # If no → worth_knowing (important FYI but can't prioritize temporally)
        has_extracted_date = temporal_ctx and (
            temporal_ctx.get("event_time")
            or temporal_ctx.get("expiration_date")
            or temporal_ctx.get("delivery_date")
        )
        if has_extracted_date:
            return "coming_up"
        # "renews soon", "expiring soon" without specific date → worth_knowing
        return "worth_knowing"

    # ========================================================================
    # STEP 2: Events with temporal context
    # ========================================================================
    # Events are special - they have dates and the T1 decay stage adjusts them
    if email_type == "event" and temporal_ctx and temporal_ctx.get("event_time"):
        # Invitations → coming_up (future planning)
        if "invitation" in subject_lower:
            return "coming_up"
        # Default events → today (T1 decay adjusts based on actual date)
        return "today"

    # ========================================================================
    # STEP 2b: Google Calendar notification guardrail
    # ========================================================================
    # Catch Google Calendar notifications that might have been misclassified
    # Format: "Notification: EVENT @ DATE TIME (TIMEZONE) (EMAIL)"
    # These should ALWAYS go to today regardless of type/importance
    if subject_lower.startswith("notification:") and " @ " in subject_lower:
        # Calendar notification format detected
        return "today"

    # ========================================================================
    # STEP 3: Minimal pattern safety net
    # ========================================================================
    # Only catch explicit "action required" that classifier might have missed
    if any(pattern in subject_lower for pattern in ELEVATED_PATTERNS):
        return "worth_knowing"

    # ========================================================================
    # STEP 4: Type-based defaults
    # ========================================================================
    if email_type in TYPE_DEFAULT_SECTION:
        return TYPE_DEFAULT_SECTION[email_type]

    # ========================================================================
    # STEP 5: Default to noise
    # ========================================================================
    # If no clear signal, assume noise (safe default)
    return "noise"
