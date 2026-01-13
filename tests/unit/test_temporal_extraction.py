"""
Unit tests for temporal context extraction and decay

Tests extraction of temporal information from emails without requiring
entity patterns, and temporal decay rules.
"""

from datetime import UTC, datetime

from shopq.digest.temporal import apply_temporal_decay, extract_temporal_context


def test_extract_google_calendar_event():
    """Extract event time from Google Calendar format with timezone conversion.

    Subject says "6:30pm - 7:30pm (EST)" which is EST (UTC-5 in November).
    After conversion to UTC:
    - 6:30pm EST = 11:30pm UTC (23:30)
    - 7:30pm EST = 12:30am UTC next day (00:30)
    """
    email = {
        "id": "123",
        "subject": "Invitation: Dinner Justin <> Adam @ Fri Nov 21, 2025 6:30pm - 7:30pm (EST)",
        "snippet": "Join with Google Meet...",
        "date": "Thu, 20 Nov 2025 10:00:00 +0000",
    }

    now = datetime(2025, 11, 10, 10, 0, 0, tzinfo=UTC)
    context = extract_temporal_context(email, now)

    assert context is not None
    assert "event_time" in context
    assert context["event_time"].year == 2025
    assert context["event_time"].month == 11
    assert context["event_time"].day == 21
    assert context["event_time"].hour == 23  # 6:30 PM EST = 11:30 PM UTC
    assert context["event_time"].minute == 30

    assert "event_end_time" in context
    # 7:30pm EST = 12:30am UTC next day (Nov 22)
    assert context["event_end_time"].day == 22
    assert context["event_end_time"].hour == 0  # 7:30 PM EST = 12:30 AM UTC
    assert context["event_end_time"].minute == 30


def test_extract_google_calendar_notification():
    """Extract event time from Google Calendar notification with timezone conversion.

    Subject says "1pm - 1:30pm (EST)" which is EST (UTC-5 in November).
    After conversion to UTC:
    - 1pm EST = 6pm UTC (18:00)
    """
    email = {
        "id": "456",
        "subject": "Notification: Call with mom @ Sun Nov 9, 2025 1pm - 1:30pm (EST)",
        "snippet": "You have an upcoming event...",
        "date": "Sun, 09 Nov 2025 12:00:00 +0000",
    }

    now = datetime(2025, 11, 9, 10, 0, 0, tzinfo=UTC)
    context = extract_temporal_context(email, now)

    assert context is not None
    assert context["event_time"].hour == 18  # 1 PM EST = 6 PM UTC
    assert context["event_time"].minute == 0


def test_extract_delivery_notification_delivered():
    """Extract delivery date from 'Delivered' subject"""
    email = {
        "id": "789",
        "subject": 'Delivered: "Slippers"',
        "snippet": "Your Amazon order has been delivered",
        "date": "Thu, 6 Nov 2025 21:59:50 +0000",
    }

    now = datetime(2025, 11, 7, 10, 0, 0, tzinfo=UTC)
    context = extract_temporal_context(email, now)

    assert context is not None
    assert "delivery_date" in context
    # Should use received_date since it says "delivered"
    assert context["delivery_date"].day == 6


def test_extract_delivery_notification_arriving_today():
    """Extract delivery date from 'arriving today' subject"""
    email = {
        "id": "101",
        "subject": "Your package is arriving today",
        "snippet": "Expected delivery by 8 PM",
        "date": "Thu, 10 Nov 2025 08:00:00 +0000",
    }

    now = datetime(2025, 11, 10, 10, 0, 0, tzinfo=UTC)
    context = extract_temporal_context(email, now)

    assert context is not None
    assert "delivery_date" in context
    assert context["delivery_date"].day == 10  # Today


def test_extract_purchase_date_with_day():
    """Extract purchase date from subject with day-of-week"""
    email = {
        "id": "202",
        "subject": "Your Saturday evening order with Uber Eats",
        "snippet": "Thanks for being an Uber One member",
        "date": "Sun, 02 Nov 2025 11:07:58 +0000",
    }

    # Now is Sunday Nov 2, so "Saturday" is yesterday (Nov 1)
    now = datetime(2025, 11, 2, 11, 0, 0, tzinfo=UTC)
    context = extract_temporal_context(email, now)

    assert context is not None
    assert "purchase_date" in context
    # Saturday before Sunday Nov 2 is Nov 1
    assert context["purchase_date"].day == 1
    assert context["purchase_date"].month == 11


def test_extract_purchase_date_friday():
    """Extract purchase date for Friday order"""
    email = {
        "id": "303",
        "subject": "[Personal] Your Friday evening order with Uber Eats",
        "snippet": "Total $16.08",
        "date": "Sat, 08 Nov 2025 16:36:32 +0000",
    }

    # Now is Saturday Nov 8, so "Friday" is yesterday (Nov 7)
    now = datetime(2025, 11, 8, 16, 0, 0, tzinfo=UTC)
    context = extract_temporal_context(email, now)

    assert context is not None
    assert "purchase_date" in context
    assert context["purchase_date"].day == 7  # Friday before Saturday


def test_no_temporal_context_for_newsletter():
    """Newsletter with no temporal markers returns None"""
    email = {
        "id": "404",
        "subject": "Lovable Update - Shopify integration, agent context",
        "snippet": "Here's everything that happened with Lovable...",
        "date": "Thu, 06 Nov 2025 01:42:37 +0000",
    }

    now = datetime(2025, 11, 10, 10, 0, 0, tzinfo=UTC)
    context = extract_temporal_context(email, now)

    # No temporal context should be found
    # (will return None or empty dict depending on implementation)
    assert context is None or context == {}


def test_extract_event_with_noon():
    """Extract event time with 12pm (noon)"""
    email = {
        "id": "505",
        "subject": "Lunch meeting @ Wed Nov 12, 2025 12pm - 1pm",
        "snippet": "See you at the cafe",
        "date": "Tue, 11 Nov 2025 10:00:00 +0000",
    }

    now = datetime(2025, 11, 11, 10, 0, 0, tzinfo=UTC)
    context = extract_temporal_context(email, now)

    assert context is not None
    assert context["event_time"].hour == 12  # Noon
    assert context["event_end_time"].hour == 13  # 1 PM


def test_extract_event_with_midnight():
    """Extract event time with 12am (midnight)"""
    email = {
        "id": "606",
        "subject": "Event @ Fri Nov 14, 2025 12am - 1am",
        "snippet": "Midnight event",
        "date": "Thu, 13 Nov 2025 10:00:00 +0000",
    }

    now = datetime(2025, 11, 13, 10, 0, 0, tzinfo=UTC)
    context = extract_temporal_context(email, now)

    assert context is not None
    assert context["event_time"].hour == 0  # Midnight
    assert context["event_end_time"].hour == 1  # 1 AM


def test_fallback_to_received_date_for_receipt():
    """Receipt without day-of-week should use received_date"""
    email = {
        "id": "707",
        "subject": "Your order confirmation #12345",
        "snippet": "Thank you for your order",
        "date": "Thu, 06 Nov 2025 15:00:00 +0000",
    }

    now = datetime(2025, 11, 10, 10, 0, 0, tzinfo=UTC)
    context = extract_temporal_context(email, now)

    assert context is not None
    assert "purchase_date" in context
    # Should use received_date as fallback
    assert context["purchase_date"].day == 6


# =============================================================================
# Issue #79: Natural date format tests
# =============================================================================


def test_extract_ordinal_date_with_time():
    """Extract date from 'Friday, Nov 7th 2025 at 2:00PM' format"""
    email = {
        "id": "808",
        "subject": "Your appointment with Midtown Dental Design is Friday, Nov 7th 2025 at 2:00PM",
        "snippet": "",
        "date": "Wed, 05 Nov 2025 10:00:00 +0000",
    }

    now = datetime(2025, 11, 9, 10, 0, 0, tzinfo=UTC)
    context = extract_temporal_context(email, now)

    assert context is not None
    assert "event_time" in context
    assert context["event_time"].year == 2025
    assert context["event_time"].month == 11
    assert context["event_time"].day == 7
    assert context["event_time"].hour == 14  # 2 PM
    assert context["event_time"].minute == 0


def test_extract_today_with_time():
    """Extract date from 'Today at 2:00PM' format"""
    email = {
        "id": "909",
        "subject": "Your appointment with Midtown Dental Design is Today at 2:00PM",
        "snippet": "",
        "date": "Sun, 09 Nov 2025 08:00:00 +0000",
    }

    now = datetime(2025, 11, 9, 10, 0, 0, tzinfo=UTC)
    context = extract_temporal_context(email, now)

    assert context is not None
    assert "event_time" in context
    assert context["event_time"].day == 9  # Today
    assert context["event_time"].hour == 14  # 2 PM


def test_extract_tomorrow_with_date():
    """Extract date from 'Tomorrow November 6th, 2025' format"""
    email = {
        "id": "1010",
        "subject": "Reminder: Braun Men's Aesthetic Event Tomorrow November 6th, 2025",
        "snippet": "",
        "date": "Wed, 05 Nov 2025 10:00:00 +0000",
    }

    now = datetime(2025, 11, 5, 10, 0, 0, tzinfo=UTC)
    context = extract_temporal_context(email, now)

    assert context is not None
    assert "event_time" in context
    # Should extract Nov 6th from the explicit date
    assert context["event_time"].month == 11
    assert context["event_time"].day == 6


def test_extract_ordinal_date_without_time():
    """Extract date from 'Nov 7th 2025' without time"""
    email = {
        "id": "1111",
        "subject": "Event scheduled for Nov 7th 2025",
        "snippet": "",
        "date": "Mon, 03 Nov 2025 10:00:00 +0000",
    }

    now = datetime(2025, 11, 5, 10, 0, 0, tzinfo=UTC)
    context = extract_temporal_context(email, now)

    assert context is not None
    assert "event_time" in context
    assert context["event_time"].day == 7
    assert context["event_time"].hour == 0  # No time specified, defaults to midnight


def test_event_confirmation_extracts_event_time_not_purchase_date():
    """Event confirmations with 'Confirmation' in subject should extract event_time, not purchase_date.

    Regression test for bug where "Confirmation" triggered purchase receipt detection,
    causing the temporal extractor to set purchase_date (today) instead of extracting
    the actual event date from the content.

    The fix checks email['type'] - if it's 'event', skip purchase receipt detection.
    """
    email = {
        "id": "river-road-123",
        "type": "event",  # LLM classified this as an event
        "subject": "River Road Drop-in Class Confirmation",
        "snippet": "Hi Justin, Thanks for signing up! This is a confirmation for your class: "
        "Adult Drop In @ Dec 3, 2025 07:00 PM - 08:00 PM (EST)",
        "date": "Thu, 05 Dec 2025 10:00:00 -0500",
    }

    # Today is Dec 5th, event was Dec 3rd
    now = datetime(2025, 12, 5, 15, 0, 0, tzinfo=UTC)
    context = extract_temporal_context(email, now)

    assert context is not None
    # Should extract event_time (Dec 3rd), NOT purchase_date
    assert "event_time" in context, "Should extract event_time for event type"
    assert context["event_time"].month == 12
    assert context["event_time"].day == 3  # Dec 3rd from snippet
    assert "purchase_date" not in context, "Should NOT set purchase_date for event type"


def test_past_event_confirmation_decays_to_skip():
    """Past event confirmations should decay to 'skip' so they don't appear in digest.

    Tests the full flow: extraction + decay for a past event.
    """
    email = {
        "id": "river-road-123",
        "type": "event",
        "subject": "River Road Drop-in Class Confirmation",
        "snippet": "Hi Justin, Thanks for signing up! This is a confirmation for your class: "
        "Adult Drop In @ Dec 3, 2025 07:00 PM - 08:00 PM (EST)",
        "date": "Thu, 05 Dec 2025 10:00:00 -0500",
    }

    # Today is Dec 5th, event was Dec 3rd (2 days ago)
    now = datetime(2025, 12, 5, 15, 0, 0, tzinfo=UTC)
    context = extract_temporal_context(email, now)

    # Apply decay - T0 might be "today" based on importance
    result = apply_temporal_decay(
        t0_section="today",
        email=email,
        temporal_ctx=context,
        now=now,
    )

    assert result == "skip", "Past event should decay to 'skip'"


# =============================================================================
# Temporal Decay Tests
# =============================================================================


def test_otp_always_skipped_from_digest():
    """OTPs should always return 'skip' regardless of T0 section.

    OTPs have T0=critical (they ARE urgent in the moment), but by digest
    generation time they're expired and useless. They should trigger
    real-time notifications, not appear in daily digests.

    See: docs/features/T0_T1_IMPORTANCE_CLASSIFICATION.md
    """
    email = {
        "id": "otp_123",
        "type": "otp",
        "subject": "Your verification code is 123456",
        "snippet": "Use this code to sign in",
    }

    now = datetime(2025, 11, 10, 10, 0, 0, tzinfo=UTC)

    # Even with T0=critical, OTPs should be skipped
    result = apply_temporal_decay(
        t0_section="critical",
        email=email,
        temporal_ctx=None,
        now=now,
    )

    assert result == "skip", "OTPs should always be skipped from digest"


def test_otp_skipped_even_with_temporal_context():
    """OTPs should be skipped even if they have temporal context."""
    email = {
        "id": "otp_456",
        "type": "otp",
        "subject": "Your login code: 789012",
        "snippet": "Code expires in 10 minutes",
    }

    now = datetime(2025, 11, 10, 10, 0, 0, tzinfo=UTC)

    # OTP with temporal context should still be skipped
    result = apply_temporal_decay(
        t0_section="critical",
        email=email,
        temporal_ctx={"expiration_date": now},
        now=now,
    )

    assert result == "skip", "OTPs should be skipped regardless of temporal context"


def test_non_otp_critical_not_skipped():
    """Non-OTP critical emails (fraud, security) should stay critical."""
    email = {
        "id": "fraud_123",
        "type": "notification",
        "subject": "Fraud alert: Unusual activity detected",
        "snippet": "We noticed suspicious activity on your account",
    }

    now = datetime(2025, 11, 10, 10, 0, 0, tzinfo=UTC)

    result = apply_temporal_decay(
        t0_section="critical",
        email=email,
        temporal_ctx=None,
        now=now,
    )

    assert result == "critical", "Non-OTP critical emails should stay critical"
