"""
Digest Temporal Processing

Consolidates time-based email processing:
- Temporal context extraction (event times, delivery dates, purchase dates)
- Temporal decay (time-based section adjustment)

Phase 2 Architecture Cleanup - Issue #59
"""

from __future__ import annotations

import email.utils
import re
from datetime import UTC, datetime, timedelta, tzinfo
from datetime import timezone as dt_timezone
from typing import Any
from zoneinfo import ZoneInfo

from mailq.observability.logging import get_logger

logger = get_logger(__name__)

__all__ = [
    "extract_temporal_context",
    "apply_temporal_decay",
    "apply_temporal_decay_batch",
]


# Timezone Utilities
def _abbrev_to_timezone(abbrev: str) -> ZoneInfo | dt_timezone:
    """
    Convert timezone abbreviation to ZoneInfo.

    Maps common US timezone abbreviations to their IANA timezone identifiers.
    Falls back to UTC for unknown abbreviations.

    Args:
        abbrev: Timezone abbreviation (e.g., "EST", "PST", "EDT")

    Returns:
        ZoneInfo for the timezone, or UTC if unknown

    Side Effects: None (pure function)
    """
    # Map abbreviations to IANA timezone names
    # Note: EST/EDT both map to America/New_York which handles DST automatically
    mapping: dict[str, str] = {
        "EST": "America/New_York",
        "EDT": "America/New_York",
        "CST": "America/Chicago",
        "CDT": "America/Chicago",
        "MST": "America/Denver",
        "MDT": "America/Denver",
        "PST": "America/Los_Angeles",
        "PDT": "America/Los_Angeles",
        # Additional common timezones
        "GMT": "UTC",
        "UTC": "UTC",
    }

    iana_name = mapping.get(abbrev.upper())
    if iana_name:
        if iana_name == "UTC":
            return UTC
        return ZoneInfo(iana_name)
    return UTC


# Temporal Context Extraction
def extract_temporal_context(
    email: dict[str, Any],
    now: datetime,
) -> dict[str, Any] | None:
    """
    Extract temporal context from email.

    Args:
        email: Email dict with 'subject', 'snippet', 'date', and optionally 'type' fields
        now: Current time for relative date calculations (used for timezone inference)

    Returns:
        {
            "event_time": datetime | None,
            "event_end_time": datetime | None,
            "delivery_date": datetime | None,
            "purchase_date": datetime | None,
            "expiration_date": datetime | None,
        }
        Returns None if no temporal context found.

    Side Effects: None (pure extraction)

    Examples:
        >>> email = {"subject": "Invitation: Dinner @ Fri Nov 21, 2025 6:30pm"}
        >>> ctx = extract_temporal_context(email, datetime(2025, 11, 10))
        >>> ctx["event_time"]
        datetime(2025, 11, 21, 18, 30)
    """
    subject = email.get("subject", "")
    snippet = email.get("snippet", "")
    received_date_str = email.get("date", "") or email.get("receivedAt", "")
    email_type = email.get("type", "")

    # Parse received date for relative date calculations
    received_date_parsed = _parse_received_date(received_date_str)

    context: dict[str, Any] = {}

    # Get user's timezone from now datetime (for calendar events without explicit timezone)
    user_tz = now.tzinfo if now.tzinfo else UTC

    # 1. Google Calendar format: "@ Mon Nov 9, 2025 7pm - 8pm"
    calendar_ctx = _extract_google_calendar_time(subject, default_tz=user_tz)
    if calendar_ctx:
        context.update(calendar_ctx)

    # 2. Delivery notifications
    if _is_delivery_notification(subject):
        delivery_date = _extract_delivery_date(subject, snippet, received_date_str, now)
        if delivery_date:
            context["delivery_date"] = delivery_date

    # 3. Purchase receipts (Uber Eats, restaurants, etc.)
    # SKIP for event-type emails - "confirmation" in subject should NOT trigger
    # purchase receipt logic for events (e.g., "Class Confirmation" is an event, not a purchase)
    if email_type != "event" and _is_purchase_receipt(subject):
        purchase_date = _extract_purchase_date(subject, snippet, received_date_str, now)
        if purchase_date:
            context["purchase_date"] = purchase_date

    # 4. Generic date extraction (fallback only)
    # Only use generic extraction if Google Calendar parsing didn't find event_time
    if not context.get("event_time"):
        generic_dates = _extract_dates_generic(
            subject + " " + snippet, now, received_date=received_date_parsed
        )
        if generic_dates:
            context["event_time"] = generic_dates[0]

    return context if context else None


# Google Calendar Extraction
def _extract_google_calendar_time(
    subject: str, default_tz: dt_timezone | ZoneInfo | tzinfo | None = None
) -> dict[str, Any] | None:
    """
    Extract event time from Google Calendar notification format.

    Patterns:
        - "Invitation: Title @ Mon Nov 9, 2025 7pm - 8pm"
        - "Notification: Title @ Sun Nov 2, 2025 6:30pm - 9:30pm (EST)"
        - "Updated invitation: Title @ Fri Nov 21, 2025 6:30pm - 7:30pm"
        - "Notification: Title @ Sun Dec 07 @ 10:00am" (no year, double @)

    Args:
        subject: Email subject line
        default_tz: Default timezone for events without explicit timezone suffix.
                   If None, defaults to UTC.

    Returns:
        {"event_time": datetime, "event_end_time": datetime} or None
    """
    # Pattern 1: @ Day Mon D, YYYY H:MMpm (with year)
    pattern_with_year = r"@ (\w{3} \w{3} \d{1,2}, \d{4}) (\d{1,2}(?::\d{2})?[ap]m)"
    match = re.search(pattern_with_year, subject, re.IGNORECASE)

    # Pattern 2: @ Day Mon D @ H:MMpm (without year, double @)
    # Used by Google Calendar for current-year events
    pattern_no_year = r"@ (\w{3} \w{3} \d{1,2}) @ (\d{1,2}(?::\d{2})?[ap]m)"
    match_no_year = re.search(pattern_no_year, subject, re.IGNORECASE)

    # Use whichever pattern matched
    has_year = True
    if match:
        pass  # Pattern 1 matched
    elif match_no_year:
        match = match_no_year
        has_year = False
    else:
        return None

    date_str, time_str = match.groups()

    # If no year in date_str, append current year
    if not has_year:
        current_year = datetime.now().year
        # Convert "Sun Dec 07" to "Sun Dec 07, 2025"
        date_str = f"{date_str}, {current_year}"

    # Extract timezone suffix if present: "(EST)", "(PST)", etc.
    tz_pattern = r"\(([A-Z]{2,4})\)\s*$"
    tz_match = re.search(tz_pattern, subject)
    tz_abbrev = tz_match.group(1) if tz_match else None

    try:
        # Parse start time with timezone
        event_time = _parse_google_calendar_datetime(
            date_str, time_str, tz_abbrev, default_tz=default_tz
        )

        result = {"event_time": event_time}

        # Try to find end time: "- 8pm" or "- 8:30pm"
        end_pattern = r"- (\d{1,2}(?::\d{2})?[ap]m)"
        end_match = re.search(end_pattern, subject[match.end() :], re.IGNORECASE)

        if end_match:
            end_time_str = end_match.group(1)
            event_end_time = _parse_google_calendar_datetime(
                date_str, end_time_str, tz_abbrev, default_tz=default_tz
            )
            result["event_end_time"] = event_end_time

        return result

    except Exception as e:
        logger.warning(f"Failed to parse Google Calendar time: {e}")
        return None


def _parse_google_calendar_datetime(
    date_str: str,
    time_str: str,
    tz_abbrev: str | None = None,
    default_tz: dt_timezone | ZoneInfo | tzinfo | None = None,
) -> datetime:
    """
    Parse Google Calendar date and time strings.

    Args:
        date_str: "Mon Nov 9, 2025"
        time_str: "7pm" or "6:30pm"
        tz_abbrev: Optional timezone abbreviation (e.g., "EST", "PST")
        default_tz: Default timezone when no abbreviation is present.
                   Typically the user's timezone. If None, defaults to UTC.

    Returns:
        Timezone-aware datetime in UTC (for consistent comparisons).
        If tz_abbrev is provided, the time is interpreted in that timezone
        and then converted to UTC. Otherwise, uses default_tz.
    """

    # Parse time
    time_str_lower = time_str.lower()
    if ":" in time_str_lower:
        # "6:30pm"
        hour_min, meridiem = time_str_lower[:-2], time_str_lower[-2:]
        hour, minute = map(int, hour_min.split(":"))
    else:
        # "7pm"
        hour = int(time_str_lower[:-2])
        minute = 0
        meridiem = time_str_lower[-2:]

    # Convert to 24-hour
    if meridiem == "pm" and hour != 12:
        hour += 12
    elif meridiem == "am" and hour == 12:
        hour = 0

    # Parse date: "Mon Nov 9, 2025"
    # Format: %a %b %d, %Y
    dt = datetime.strptime(date_str, "%a %b %d, %Y")

    # Get timezone: explicit abbreviation > default_tz > UTC
    tz: dt_timezone | ZoneInfo | tzinfo
    if tz_abbrev:
        tz = _abbrev_to_timezone(tz_abbrev)
    elif default_tz:
        tz = default_tz
    else:
        tz = UTC

    # Create datetime in source timezone
    local_dt = dt.replace(hour=hour, minute=minute, second=0, microsecond=0, tzinfo=tz)

    # Convert to UTC for consistent storage and comparison
    return local_dt.astimezone(UTC)


# Delivery Notification Extraction
def _is_delivery_notification(subject: str) -> bool:
    """Check if email is a delivery notification"""
    delivery_keywords = [
        "delivered",
        "delivery",
        "arriving",
        "out for delivery",
        "package",
        "shipment",
    ]
    subject_lower = subject.lower()
    return any(keyword in subject_lower for keyword in delivery_keywords)


def _extract_delivery_date(
    subject: str,
    _snippet: str,  # Reserved for future pattern extraction
    received_date: str,
    now: datetime,
) -> datetime | None:
    """
    Extract delivery date from subject/snippet.

    Strategy:
    1. If "delivered" in subject → use received_date (delivery happened)
    2. If "arriving today" → use today
    3. If "arriving tomorrow" → use tomorrow
    4. Otherwise → use received_date as fallback
    """
    subject_lower = subject.lower()

    # Already delivered → use received date
    if "delivered" in subject_lower or "has been delivered" in subject_lower:
        return _parse_received_date(received_date) or now

    # Arriving today
    if "arriving today" in subject_lower or "delivery today" in subject_lower:
        # Keep timezone from now
        return now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Arriving tomorrow
    if "arriving tomorrow" in subject_lower:
        tomorrow = now + timedelta(days=1)
        # Keep timezone from now
        return tomorrow.replace(hour=0, minute=0, second=0, microsecond=0)

    # Fallback: use received date
    return _parse_received_date(received_date) or now


# Purchase Receipt Extraction
def _is_purchase_receipt(subject: str) -> bool:
    """Check if email is a purchase receipt"""
    receipt_keywords = [
        "receipt",
        "order",
        "payment",
        "confirmation",
        "invoice",
    ]
    subject_lower = subject.lower()
    return any(keyword in subject_lower for keyword in receipt_keywords)


def _extract_purchase_date(
    subject: str,
    _snippet: str,  # Reserved for future pattern extraction
    received_date: str,
    now: datetime,
) -> datetime | None:
    """
    Extract purchase date from subject/snippet.

    Strategy:
    1. Look for day-of-week in subject ("Your Saturday order")
    2. Find most recent occurrence of that day
    3. Fallback to received_date
    """
    # Try to extract day from subject
    day_match = _extract_day_of_week(subject)

    if day_match:
        # Find most recent occurrence of that day
        target_day = day_match
        purchase_date = _find_recent_day(target_day, now)
        if purchase_date:
            return purchase_date

    # Fallback: use received date
    return _parse_received_date(received_date) or now


def _extract_day_of_week(text: str) -> str | None:
    """
    Extract day of week from text.

    Examples:
        "Your Saturday order" → "Saturday"
        "Friday evening order" → "Friday"
    """
    days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    text_lower = text.lower()

    for day in days:
        if day in text_lower:
            return day.capitalize()

    return None


def _find_recent_day(target_day: str, now: datetime) -> datetime | None:
    """
    Find most recent occurrence of target day (today or earlier).

    Args:
        target_day: "Monday", "Tuesday", etc.
        now: Current datetime

    Returns:
        Datetime of most recent target_day (or today if today is target_day)
    """
    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

    try:
        target_weekday = day_names.index(target_day)
    except ValueError:
        return None

    current_weekday = now.weekday()

    # Calculate days to go back
    if current_weekday >= target_weekday:
        days_back = current_weekday - target_weekday
    else:
        days_back = 7 - (target_weekday - current_weekday)

    result = now - timedelta(days=days_back)
    # Keep timezone from now
    return result.replace(hour=0, minute=0, second=0, microsecond=0)


def _find_next_day(target_day: str, reference_date: datetime) -> datetime | None:
    """
    Find the next occurrence of target day (today or later).

    Used for "This Saturday", "This Sunday" patterns.

    Args:
        target_day: "Monday", "Tuesday", etc.
        reference_date: Date to start searching from

    Returns:
        Datetime of next target_day (timezone-aware), or None if invalid day
    """
    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

    try:
        target_weekday = day_names.index(target_day)
    except ValueError:
        return None

    current_weekday = reference_date.weekday()

    # Calculate days forward
    if target_weekday >= current_weekday:
        days_forward = target_weekday - current_weekday
    else:
        days_forward = 7 - (current_weekday - target_weekday)

    result = reference_date + timedelta(days=days_forward)
    # Ensure timezone-aware
    if result.tzinfo is None:
        result = result.replace(tzinfo=UTC)
    return result.replace(hour=12, minute=0, second=0, microsecond=0)  # Default to noon


# Generic Date Extraction
def _extract_dates_generic(
    text: str,
    now: datetime,
    received_date: datetime | None = None,
) -> list[datetime]:
    """
    Extract dates from text using generic patterns.

    This is a fallback for emails that don't match specific patterns.

    Supported patterns:
        - "Nov 9, 2025" or "November 9, 2025"
        - "Nov 7th 2025" or "November 7th, 2025" (ordinal dates)
        - "Friday, Nov 7th 2025" (weekday prefix)
        - "Today at 2:00PM" or "Today at 2pm"
        - "Tomorrow at 3:00PM"
        - "This Saturday" / "This Sunday" etc. (relative to received_date)

    Args:
        text: Text to search for date patterns
        now: Current evaluation time (for "Today"/"Tomorrow" patterns)
        received_date: When email was received (for "This [Day]" patterns)

    Returns:
        List of timezone-aware datetime objects found in text (may be empty)

    Side Effects: None (pure function - builds and returns list)
    """
    dates = []

    # Pattern 0: "This Saturday" / "This [Day]" - relative to received date
    # Use received_date if available, else now
    reference_date = received_date if received_date else now
    this_day_pattern = r"[Tt]his\s+(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)"
    for match in re.finditer(this_day_pattern, text, re.IGNORECASE):
        target_day = match.group(1).capitalize()
        # Find the next occurrence of that day from reference_date
        next_day = _find_next_day(target_day, reference_date)
        if next_day:
            dates.append(next_day)

    # Pattern 1: "Today at 2:00PM" or "Today at 2pm"
    today_pattern = r"[Tt]oday\s+at\s+(\d{1,2})(?::(\d{2}))?\s*([AaPp][Mm])"
    for match in re.finditer(today_pattern, text):
        hour = int(match.group(1))
        minute = int(match.group(2)) if match.group(2) else 0
        meridiem = match.group(3).lower()

        if meridiem == "pm" and hour != 12:
            hour += 12
        elif meridiem == "am" and hour == 12:
            hour = 0

        dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        dates.append(dt)

    # Pattern 2: "Tomorrow at 3:00PM" or "Tomorrow at 3pm"
    tomorrow_pattern = r"[Tt]omorrow\s+at\s+(\d{1,2})(?::(\d{2}))?\s*([AaPp][Mm])"
    for match in re.finditer(tomorrow_pattern, text):
        hour = int(match.group(1))
        minute = int(match.group(2)) if match.group(2) else 0
        meridiem = match.group(3).lower()

        if meridiem == "pm" and hour != 12:
            hour += 12
        elif meridiem == "am" and hour == 12:
            hour = 0

        tomorrow = now + timedelta(days=1)
        dt = tomorrow.replace(hour=hour, minute=minute, second=0, microsecond=0)
        dates.append(dt)

    # Pattern 3: Ordinal dates with optional time
    # "Nov 7th 2025 at 2:00PM", "Friday, Nov 7th 2025", "November 7th, 2025"
    # Captures: month, day, ordinal suffix, year, optional time
    ordinal_pattern = (
        r"(?:\w+,?\s+)?"  # Optional weekday like "Friday, " or "Friday "
        r"(\w+)\s+"  # Month (Nov or November)
        r"(\d{1,2})(?:st|nd|rd|th)"  # Day with ordinal (7th, 1st, 2nd, 3rd)
        r",?\s+"  # Optional comma and space
        r"(\d{4})"  # Year
        r"(?:\s+at\s+(\d{1,2})(?::(\d{2}))?\s*([AaPp][Mm]))?"  # Optional time
    )
    for match in re.finditer(ordinal_pattern, text, re.IGNORECASE):
        try:
            month_str = match.group(1)
            day_str = match.group(2)
            year_str = match.group(3)
            hour_str = match.group(4)
            minute_str = match.group(5)
            meridiem = match.group(6)

            # Try full month name first, then abbreviated
            try:
                dt = datetime.strptime(f"{month_str} {day_str} {year_str}", "%B %d %Y")
            except ValueError:
                dt = datetime.strptime(f"{month_str} {day_str} {year_str}", "%b %d %Y")

            # Add time if present
            if hour_str and meridiem:
                hour = int(hour_str)
                minute = int(minute_str) if minute_str else 0
                meridiem_lower = meridiem.lower()

                if meridiem_lower == "pm" and hour != 12:
                    hour += 12
                elif meridiem_lower == "am" and hour == 12:
                    hour = 0

                dt = dt.replace(hour=hour, minute=minute)

            dates.append(dt.replace(tzinfo=UTC))
        except ValueError:
            continue

    # Pattern 4: Standard format - "Nov 9, 2025" or "November 9, 2025"
    month_day_year = r"(\w+)\s+(\d{1,2}),\s+(\d{4})"
    for match in re.finditer(month_day_year, text):
        try:
            month_str, day_str, year_str = match.groups()
            try:
                dt = datetime.strptime(f"{month_str} {day_str} {year_str}", "%B %d %Y")
            except ValueError:
                dt = datetime.strptime(f"{month_str} {day_str} {year_str}", "%b %d %Y")
            dates.append(dt.replace(tzinfo=UTC))
        except ValueError:
            continue

    # Pattern 5: Short numeric format - "11/6" or "11/06" (assume current year from reference_date)
    # Common in subject lines like "Webinar 11/6"
    short_date_pattern = r"\b(\d{1,2})/(\d{1,2})\b"
    for match in re.finditer(short_date_pattern, text):
        try:
            month = int(match.group(1))
            day = int(match.group(2))
            if 1 <= month <= 12 and 1 <= day <= 31:
                # Use year from reference_date (or now if not available)
                ref = received_date if received_date else now
                year = ref.year
                # If the date is in the past relative to reference, assume next year
                dt = datetime(year, month, day, 12, 0, 0, tzinfo=UTC)
                if dt < ref.replace(tzinfo=UTC) - timedelta(days=30):  # More than 30 days ago
                    dt = datetime(year + 1, month, day, 12, 0, 0, tzinfo=UTC)
                dates.append(dt)
        except ValueError:
            continue

    return dates


# Utility Functions
def _parse_received_date(date_str: str) -> datetime | None:
    """
    Parse RFC 2822 date string from email headers.

    Args:
        date_str: "Thu, 6 Nov 2025 21:59:50 +0000"

    Returns:
        Timezone-aware datetime or None if parsing fails
    """
    if not date_str:
        return None

    try:
        date_tuple = email.utils.parsedate_tz(date_str)
        if date_tuple:
            timestamp = email.utils.mktime_tz(date_tuple)
            return datetime.fromtimestamp(timestamp)
    except Exception as e:
        logger.warning(f"Failed to parse received_date '{date_str}': {e}")

    return None


# =============================================================================
# TEMPORAL DECAY
# =============================================================================
# Applies time-based section adjustments to emails:
# - Events past their time → skip
# - Deliveries past their time → noise
# - Future events → coming_up
# - Same day events → today


def apply_temporal_decay(
    t0_section: str,
    email: dict[str, Any],
    temporal_ctx: dict[str, Any] | None,
    now: datetime,
    _user_timezone: str = "UTC",  # Reserved for future timezone-aware display
) -> str:
    """
    Apply temporal decay to T0 section based on current time.

    Args:
        t0_section: Intrinsic section from T0 classification
        email: Email dict (for logging/debugging)
        temporal_ctx: Temporal context with event_time, delivery_date, etc.
        now: Current evaluation time (timezone-aware)
        user_timezone: User's timezone for display (not used in logic)

    Returns:
        T1 section: "critical" | "today" | "coming_up" | "worth_knowing" | "noise" | "skip"

    Side Effects:
    - DEBUG/INFO logs when decay is applied

    Examples:
        >>> # Event from 2 days ago (T0=today, but expired)
        >>> temporal_ctx = {"event_time": datetime(2025, 11, 8, 18, 0, tzinfo=timezone.utc)}
        >>> now = datetime(2025, 11, 10, 18, 20, tzinfo=timezone.utc)
        >>> apply_temporal_decay("today", email, temporal_ctx, now)
        "skip"  # Event expired, grace period passed

        >>> # Event tomorrow (T0=today, still relevant)
        >>> temporal_ctx = {"event_time": datetime(2025, 11, 11, 18, 0, tzinfo=timezone.utc)}
        >>> now = datetime(2025, 11, 10, 18, 20, tzinfo=timezone.utc)
        >>> apply_temporal_decay("today", email, temporal_ctx, now)
        "today"  # Event within 24 hours

        >>> # Event in 5 days (T0=today, but future)
        >>> temporal_ctx = {"event_time": datetime(2025, 11, 15, 18, 0, tzinfo=timezone.utc)}
        >>> now = datetime(2025, 11, 10, 18, 20, tzinfo=timezone.utc)
        >>> apply_temporal_decay("today", email, temporal_ctx, now)
        "coming_up"  # Event 1-7 days out
    """
    # Ensure now is timezone-aware
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)

    # OTPs - Always skip (too ephemeral for digest)
    if email.get("type") == "otp":
        logger.debug(
            f"Email {email.get('id', 'unknown')}: T0={t0_section} → T1=skip "
            "(OTP - too ephemeral for digest)"
        )
        return "skip"

    # CRITICAL - Age-based decay for non-OTP critical emails
    # OTPs already handled above (always skip)
    # Other critical emails (security alerts, fraud) decay to worth_knowing after 24h
    if t0_section == "critical":
        internal_date = email.get("internalDate")
        if internal_date:
            try:
                # Gmail internalDate is milliseconds since epoch
                email_timestamp = int(internal_date) / 1000
                email_dt = datetime.fromtimestamp(email_timestamp, tz=UTC)
                hours_old = (now - email_dt).total_seconds() / 3600
                if hours_old > 24:
                    logger.debug(
                        f"Email {email.get('id', 'unknown')}: T0=critical → T1=worth_knowing "
                        f"(security alert {hours_old:.1f}h old, >24h decay)"
                    )
                    return "worth_knowing"
            except (ValueError, TypeError):
                pass  # If parsing fails, keep as critical
        return "critical"

    # NOISE - No temporal decay
    if t0_section == "noise":
        return "noise"

    # No temporal context → no decay (return as-is)
    if not temporal_ctx:
        return t0_section

    # Extract relevant times first (needed for notification check below)
    event_time = temporal_ctx.get("event_time")

    # Messages and receipts should NOT decay based on dates mentioned in their content
    # EXCEPTION: Notifications with explicit event_time (e.g., Google Calendar) should still decay
    email_type = email.get("type", "")
    if email_type in ["message", "newsletter", "receipt"]:
        return t0_section
    if email_type == "notification" and not event_time:
        # Skip decay for generic notifications without calendar event times
        return t0_section
    delivery_date = temporal_ctx.get("delivery_date")
    purchase_date = temporal_ctx.get("purchase_date")

    # Determine primary temporal signal (priority: event > delivery > purchase)
    primary_time = event_time or delivery_date or purchase_date

    if not primary_time:
        return t0_section

    # Ensure primary_time is timezone-aware
    if primary_time.tzinfo is None:
        primary_time = primary_time.replace(tzinfo=UTC)

    # Calculate time difference
    time_diff = primary_time - now
    hours_until = time_diff.total_seconds() / 3600

    # Determine content type from email
    subject = email.get("subject", "").lower()

    # Receipts and confirmations decay to NOISE (not worth_knowing)
    is_receipt = email_type in ["receipt", "confirmation"] or any(
        word in subject for word in ["receipt", "order with", "thanks for", "payment confirm"]
    )

    if is_receipt:
        if t0_section == "noise":
            return "noise"
        if hours_until < 0:
            logger.debug(
                f"Email {email.get('id', 'unknown')}: T0={t0_section} → T1=noise "
                f"(receipt from {abs(hours_until):.1f}h ago)"
            )
            return "noise"

    # Rule 1: Expired events → SKIP (1-hour grace period)
    if event_time and hours_until < -1:
        logger.debug(
            f"Email {email.get('id', 'unknown')}: T0={t0_section} → T1=skip "
            f"(event expired {abs(hours_until):.1f}h ago)"
        )
        return "skip"

    # Rule 2: Expired deliveries → NOISE (>24h ago)
    if delivery_date and hours_until < -24:
        logger.debug(
            f"Email {email.get('id', 'unknown')}: T0={t0_section} → T1=noise "
            f"(delivery from {abs(hours_until / 24):.1f} days ago)"
        )
        return "noise"

    # Rule 3: Expired purchases → NOISE
    if purchase_date and hours_until < 0:
        logger.debug(
            f"Email {email.get('id', 'unknown')}: T0={t0_section} → T1=noise "
            f"(purchase from {abs(hours_until):.1f}h ago)"
        )
        return "noise"

    # Rule 4: Same CALENDAR day → TODAY
    event_date = primary_time.date()
    today_date = now.date()

    if event_date == today_date:
        logger.debug(
            f"Email {email.get('id', 'unknown')}: T0={t0_section} → T1=today "
            f"(same calendar day, in {hours_until:.1f}h)"
        )
        return "today"

    # Rule 5: 1-7 days out → COMING_UP
    calendar_days_until = (event_date - today_date).days
    if 1 <= calendar_days_until <= 7:
        logger.debug(
            f"Email {email.get('id', 'unknown')}: T0={t0_section} → T1=coming_up "
            f"(in {calendar_days_until} calendar days)"
        )
        return "coming_up"

    # Rule 6: >7 days out → COMING_UP (stay visible but not urgent)
    if calendar_days_until > 7:
        logger.debug(
            f"Email {email.get('id', 'unknown')}: T0={t0_section} → T1=coming_up "
            f"(in {calendar_days_until} calendar days, future event)"
        )
        return "coming_up"

    # Fallback
    logger.warning(
        f"Email {email.get('id', 'unknown')}: Unexpected temporal state "
        f"(T0={t0_section}, hours_until={hours_until:.1f}). Returning T0 as-is."
    )
    return t0_section


def apply_temporal_decay_batch(
    section_assignments_t0: dict[str, str],
    emails: list[dict[str, Any]],
    temporal_contexts: dict[str, dict[str, Any]],
    now: datetime,
    user_timezone: str = "UTC",  # noqa: ARG001 - Reserved for future timezone-aware display
) -> dict[str, str]:
    """
    Apply temporal decay to a batch of T0 section assignments.

    Args:
        section_assignments_t0: Map of email_id → T0 section
        emails: List of email dicts
        temporal_contexts: Map of email_id → temporal context
        now: Current evaluation time (timezone-aware)
        user_timezone: User's timezone for display

    Returns:
        Map of email_id → T1 section (after temporal decay)

    Side Effects:
    - DEBUG/WARNING logs during processing
    """
    emails_by_id = {email["id"]: email for email in emails}
    section_assignments_t1 = {}

    for email_id, t0_section in section_assignments_t0.items():
        email = emails_by_id.get(email_id)
        if not email:
            logger.warning(f"Email {email_id} not found in emails list. Skipping.")
            continue

        temporal_ctx = temporal_contexts.get(email_id)
        t1_section = apply_temporal_decay(
            t0_section=t0_section,
            email=email,
            temporal_ctx=temporal_ctx,
            now=now,
        )
        section_assignments_t1[email_id] = t1_section

    return section_assignments_t1
