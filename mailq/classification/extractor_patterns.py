"""
Pattern constants and helpers for entity extraction.

Extracted from extractor.py to reduce file size.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from mailq.observability.logging import get_logger

logger = get_logger(__name__)

# Flight patterns
FLIGHT_PATTERNS = {
    "flight_number": r"[Ff]light\s+([A-Z]{2,3}?\s*\d{1,4})",
    "airline": r"(United|Delta|American|Southwest|Alaska|JetBlue|Spirit|Frontier)",
    "airport_code": r"\(([A-Z]{3})\)",
    "time": r"(\d{1,2}:\d{2}\s*[AP]M)",
    "confirmation": r"confirmation\s*(?:code|number)?[:\s]+([A-Z0-9]{6,})",
}

# Event patterns
EVENT_PATTERNS = {
    "starts_soon": r"(?:starts?|begins?|coming up)\s+(?:in\s+)?(\d+\s+days?|tomorrow|today)",
    "event_time": r"(?:at|@)\s+(\d{1,2}(?::\d{2})?\s*[AP]M)",
    # "2:00 PM - 3:00 PM"
    "event_time_range": r"(\d{1,2}(?::\d{2})?\s*[AP]M)\s*(?:-|to|–)\s*(\d{1,2}(?::\d{2})?\s*[AP]M)",
    "dont_forget": r"don'?t\s+forget:?\s+(.+?)(?:\s+starts?|$)",
    "location_in": r"\bin\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",  # "in Boston", "in New York"
    "location_at": r"\bat\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)?)",
    # "at Kellari Taverna", "at Madison Square Garden"
}

# Deadline patterns
DEADLINE_PATTERNS = {
    "bill_due": r"(bill|payment|invoice)\s+(?:is\s+)?due\s+(\w+)",
    "amount": r"\$(\d+(?:,\d{3})*(?:\.\d{2})?)",
    "due_date": r"due\s+(?:on\s+)?(\w+\s+\d+|\w+|tomorrow|today)",
}

# Reminder patterns
REMINDER_PATTERNS = {
    "schedule": r"(?:time to|schedule|book)\s+(?:a\s+)?(.+?)(?:\.|$)",
    "renew": r"(?:renew|renewal)\s+(?:your\s+)?(.+?)(?:\.|$)",
}

# Promo patterns
PROMO_PATTERNS = {
    "discount": r"(\d+%)\s+off",
    "ends": r"(?:ends?|expires?)\s+(\w+)",
    "sale": r"(sale|deal|offer)",
}


def email_timestamp(email: dict) -> datetime:
    """Parse email timestamp into aware datetime (UTC fallback)."""
    raw_ts = email.get("timestamp") or email.get("date") or email.get("received_date")

    if isinstance(raw_ts, int | float):
        # Gmail internalDate is milliseconds since epoch
        try:
            return datetime.fromtimestamp(raw_ts / 1000.0, tz=UTC)
        except (ValueError, OSError, OverflowError) as e:
            logger.warning("Failed to parse timestamp %s: %s", raw_ts, e)

    if isinstance(raw_ts, str) and raw_ts:
        # Try integer string
        try:
            numeric = float(raw_ts)
            return datetime.fromtimestamp(numeric / 1000.0, tz=UTC)
        except (ValueError, TypeError, OSError, OverflowError) as e:
            logger.warning("Failed to parse timestamp string %s: %s", raw_ts, e)

        # Try ISO formatted string
        try:
            parsed = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return parsed
        except ValueError:
            pass

    # Fallback to current UTC time to avoid breaking pipeline
    return datetime.now(UTC)


def get_email_importance(email: dict) -> str:
    """Get importance from email's Gemini classification (single source of truth).

    Args:
        email: Email dict with 'importance' field from Gemini classification

    Returns:
        Importance level: 'critical', 'time_sensitive', or 'routine'
    """
    importance = email.get("importance", "routine")
    # Validate it's a known importance level
    if importance not in ("critical", "time_sensitive", "routine"):
        return "routine"
    return importance


def parse_notification_timestamp(email: dict) -> datetime:
    """Parse timestamp from email for notification extraction.

    Handles various formats: epoch ms, stringified epoch, ISO, datetime objects.
    """
    timestamp_value = email.get("timestamp")
    if not timestamp_value:
        return datetime.now()

    if isinstance(timestamp_value, int | float):
        # Gmail internalDate: milliseconds since epoch
        try:
            return datetime.fromtimestamp(timestamp_value / 1000.0)
        except (ValueError, OSError):
            return datetime.now()

    if isinstance(timestamp_value, str):
        try:
            # Try parsing as int first (stringified milliseconds)
            timestamp_ms = int(timestamp_value)
            return datetime.fromtimestamp(timestamp_ms / 1000.0)
        except ValueError:
            # Not an int, try ISO format or other date formats
            try:
                from dateutil import parser

                return parser.parse(timestamp_value)
            except (ValueError, TypeError, OverflowError):
                return datetime.now()

    if isinstance(timestamp_value, datetime):
        return timestamp_value

    return datetime.now()


def extract_otp_expiry(text_lower: str, email_timestamp: datetime) -> datetime | None:
    """Extract OTP expiry time from text.

    Pattern: "expires in 5 minutes", "valid for 10 minutes"
    """
    if not any(
        word in text_lower for word in ["otp", "verification code", "security code", "one-time"]
    ):
        return None

    expiry_match = re.search(r"(?:expires?|valid)\s+(?:in\s+)?(\d+)\s+(minute|hour)s?", text_lower)
    if not expiry_match:
        return None

    try:
        duration = int(expiry_match.group(1))
        unit = expiry_match.group(2)
        from datetime import timedelta

        if unit == "minute":
            return email_timestamp + timedelta(minutes=duration)
        return email_timestamp + timedelta(hours=duration)
    except (ValueError, AttributeError):
        return None


def extract_shipping_info(
    text_lower: str, text: str, email_timestamp: datetime
) -> tuple[str | None, datetime | None, str | None]:
    """Extract shipping status, delivery time, and tracking number.

    Returns:
        Tuple of (ship_status, delivered_at, tracking_number)
    """
    ship_status = None
    delivered_at = None
    tracking_number = None

    # Extract shipping status
    if any(word in text_lower for word in ["out for delivery", "arriving today", "deliver today"]):
        ship_status = "out_for_delivery"
    elif "delivered" in text_lower:
        ship_status = "delivered"
        delivered_at = email_timestamp
    elif any(word in text_lower for word in ["shipped", "on the way", "in transit"]):
        ship_status = "in_transit"
    elif "processing" in text_lower:
        ship_status = "processing"

    # Extract tracking number (common patterns)
    tracking_match = re.search(
        r"(?:tracking|track)\s*(?:number|#)?\s*[:\-]?\s*([A-Z0-9]{10,30})",
        text,
        re.IGNORECASE,
    )
    if tracking_match:
        tracking_number = tracking_match.group(1)

    return ship_status, delivered_at, tracking_number


def categorize_notification(text_lower: str, email_type: str | None) -> str | None:
    """Determine notification category from email content.

    Returns category string or None if not a notification.
    """
    if any(word in text_lower for word in ["fraud", "suspicious", "unauthorized", "flagged"]):
        return "fraud_alert"
    if any(
        word in text_lower
        for word in [
            "delivered",
            "delivery",
            "package",
            "shipped",
            "arriving",
            "on the way",
            "order",
            "shipment",
        ]
    ):
        return "delivery"
    if any(word in text_lower for word in ["bill", "payment", "due"]):
        return "bill"
    if any(
        word in text_lower
        for word in [
            "opportunity",
            "job",
            "hiring",
            "position",
            "manager",
            "engineer",
            "apply",
        ]
    ):
        return "job_opportunity"
    if any(word in text_lower for word in ["claim", "insurance", "medical", "policy"]):
        return "claim"
    if any(word in text_lower for word in ["rental", "reservation", "booking", "extend", "return"]):
        return "reservation"
    if email_type == "notification":
        return "general"
    return None


# HIGH FIX: Import fallback to prevent pipeline breakage if structured logging fails
try:
    from mailq.observability.structured import EventType  # noqa: F401
    from mailq.observability.structured import get_logger as get_structured_logger

    s_logger = get_structured_logger()  # Structured logger for extraction events
except (ImportError, AttributeError) as e:
    # Fallback: NoOp logger if structured logging unavailable
    logger.warning("Structured logging unavailable: %s", e)

    class NoOpLogger:
        def log_event(self, *args: Any, **kwargs: Any) -> None:
            pass

    s_logger = NoOpLogger()  # type: ignore[assignment]


def validate_entity_metadata(entity: Any, email: dict) -> Any:
    """
    Validate that entity has required metadata for linking.

    PRIORITY 6 FIX: Warn about missing metadata to help debug linking issues.

    Side Effects:
    - MUTATES entity in-place (sets source_thread_id, source_email_id, source_subject)
    - Logs warnings and errors to structured logger for missing metadata
    - May log EXTRACT_INCONSISTENT events for telemetry
    """
    # Check for thread_id (most important for linking)
    if not entity.source_thread_id:
        logger.warning("Metadata warning: Entity missing thread_id")
        logger.warning("   Subject: %s", entity.source_subject[:60])
        logger.warning("   Type: %s", entity.type)

        # Try to recover from email
        recovered_thread_id = email.get("thread_id") or email.get("id")
        if recovered_thread_id:
            entity.source_thread_id = recovered_thread_id
            logger.info("   Recovered thread_id: %s", recovered_thread_id[:20])
        else:
            logger.error("   Could not recover thread_id - using subject search")
            # STRUCTURED LOG: Metadata inconsistency
            s_logger.log_event(
                EventType.EXTRACT_INCONSISTENT,
                email_id=entity.source_email_id,
                issue="missing_thread_id",
                recovery="failed",
                subject=entity.source_subject,
            )

    # Check for email_id
    if not entity.source_email_id:
        logger.warning("Metadata warning: Entity missing source_email_id")
        logger.warning("   Subject: %s", entity.source_subject[:60])

        recovered_email_id = email.get("id")
        if recovered_email_id:
            entity.source_email_id = recovered_email_id
            logger.info("   Recovered email_id")

    # Check for subject
    if not entity.source_subject or len(entity.source_subject) < 5:
        logger.warning("Metadata warning: Entity missing or short subject")
        logger.warning("   Current: '%s'", entity.source_subject)

        recovered_subject = email.get("subject")
        if recovered_subject:
            entity.source_subject = recovered_subject
            logger.info("   Recovered subject: %s", recovered_subject[:60])

    return entity
