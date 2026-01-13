"""
Golden Dataset (gds-1.0) regression tests for TypeMapper.

Ensures type mapper correctly classifies the 56 event emails in gds-1.0,
particularly calendar invitations that were historically misclassified as notifications.

Dataset: tests/golden_set/gds-1.0.csv
- Total emails: 500
- Events: 56 (11.2%)
- Target: ≥90% of calendar invites should match type mapper rules
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from mailq.classification.type_mapper import TypeMapper
from mailq.utils.email import extract_email_address

# Path to golden dataset
GDS_PATH = Path(__file__).parent / "golden_set" / "gds-1.0.csv"


def load_gds_events() -> list[dict]:
    """
    Load all event emails from gds-1.0.csv.

    Returns:
        List of event email dicts with keys: message_id, from_email, subject, snippet, email_type
    """
    if not GDS_PATH.exists():
        pytest.skip(f"Golden dataset not found: {GDS_PATH}")

    events = []
    with open(GDS_PATH, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("email_type") == "event":
                events.append(
                    {
                        "message_id": row["message_id"],
                        "from_email": row["from_email"],
                        "subject": row["subject"],
                        "snippet": row["snippet"],
                        "email_type": row["email_type"],
                    }
                )

    return events


def load_gds_calendar_events() -> list[dict]:
    """
    Load calendar-specific event emails from gds-1.0.

    Returns only events from known calendar systems (Google, Outlook, Yahoo, etc.).
    """
    all_events = load_gds_events()

    calendar_keywords = [
        "calendar",
        "invite",
        "eventbrite",
        "event",
        "reservation",
    ]

    calendar_events = []
    for event in all_events:
        from_lower = event["from_email"].lower()
        if any(keyword in from_lower for keyword in calendar_keywords):
            calendar_events.append(event)

    return calendar_events


class TestGDSEventConsistency:
    """Test type mapper against gds-1.0 event emails."""

    def test_gds_has_56_events(self):
        """Verify gds-1.0 has exactly 56 events as documented."""
        events = load_gds_events()
        assert len(events) == 56, f"Expected 56 events, found {len(events)}"

    def test_calendar_events_match_type_mapper(self):
        """
        At least 90% of calendar invites should match type mapper rules.

        This is the primary acceptance criterion - calendar invitations
        should be deterministically classified as events, not notifications.
        """
        calendar_events = load_gds_calendar_events()

        if len(calendar_events) == 0:
            pytest.skip("No calendar events found in gds-1.0")

        mapper = TypeMapper()
        matches = 0
        failures = []

        for event in calendar_events:
            sender_email = extract_email_address(event["from_email"])
            result = mapper.get_deterministic_type(sender_email, event["subject"], event["snippet"])

            if result and result["type"] == "event":
                matches += 1
            else:
                failures.append(
                    {
                        "message_id": event["message_id"],
                        "from": event["from_email"],
                        "subject": event["subject"][:60],
                        "result": result["type"] if result else None,
                    }
                )

        match_rate = matches / len(calendar_events)

        # Report failures for debugging
        if failures:
            print(f"\n❌ Calendar events that didn't match ({len(failures)}):")
            for fail in failures[:5]:  # Show first 5
                print(f"  - {fail['from']}: {fail['subject']}")

        assert match_rate >= 0.90, (
            f"Expected ≥90% calendar match rate, got {match_rate:.1%} ({matches}/{len(calendar_events)})"
        )

    def test_all_events_typed_correctly_or_fallback(self):
        """
        All 56 events should either:
        1. Match type mapper as 'event', OR
        2. Return None (will fall back to LLM)

        Should NEVER return a different type (e.g., 'notification').
        """
        all_events = load_gds_events()
        mapper = TypeMapper()

        wrong_type_errors = []

        for event in all_events:
            sender_email = extract_email_address(event["from_email"])
            result = mapper.get_deterministic_type(sender_email, event["subject"], event["snippet"])

            if result and result["type"] != "event":
                wrong_type_errors.append(
                    {
                        "message_id": event["message_id"],
                        "from": event["from_email"],
                        "subject": event["subject"][:60],
                        "got_type": result["type"],
                        "expected": "event",
                    }
                )

        if wrong_type_errors:
            print(f"\n❌ Events misclassified as wrong type ({len(wrong_type_errors)}):")
            for error in wrong_type_errors:
                print(f"  - {error['from']}: {error['subject']} → {error['got_type']}")

        assert len(wrong_type_errors) == 0, (
            f"Type mapper should never return wrong type for events (found {len(wrong_type_errors)})"
        )

    def test_google_calendar_events_all_match(self):
        """
        All Google Calendar events should match type mapper.

        This is the primary use case we're solving - Google Calendar
        notifications were being misclassified as type=notification.
        """
        all_events = load_gds_events()

        google_events = [
            e
            for e in all_events
            if "google.com" in e["from_email"].lower() and "calendar" in e["from_email"].lower()
        ]

        if len(google_events) == 0:
            pytest.skip("No Google Calendar events in gds-1.0")

        mapper = TypeMapper()
        matches = 0
        failures = []

        for event in google_events:
            sender_email = extract_email_address(event["from_email"])
            result = mapper.get_deterministic_type(sender_email, event["subject"], event["snippet"])

            if result and result["type"] == "event":
                matches += 1
            else:
                failures.append(
                    {"message_id": event["message_id"], "subject": event["subject"][:60]}
                )

        if failures:
            print(f"\n❌ Google Calendar events that didn't match ({len(failures)}):")
            for fail in failures:
                print(f"  - {fail['subject']}")

        assert matches == len(google_events), (
            f"All Google Calendar events should match type mapper (got {matches}/{len(google_events)})"
        )

    def test_non_events_dont_match_as_events(self):
        """
        Emails that are NOT events should not match type mapper as events.

        This ensures high precision - we only match when confident.
        """
        if not GDS_PATH.exists():
            pytest.skip(f"Golden dataset not found: {GDS_PATH}")

        mapper = TypeMapper()
        false_positives = []

        with open(GDS_PATH, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Skip actual events
                if row.get("email_type") == "event":
                    continue

                # Test non-events
                sender_email = extract_email_address(row["from_email"])
                result = mapper.get_deterministic_type(sender_email, row["subject"], row["snippet"])

                # If type mapper matched, it should be event (or None)
                # Should NOT match as notification, receipt, etc.
                if result and result["type"] == "event":
                    # This is a false positive (non-event matched as event)
                    false_positives.append(
                        {
                            "message_id": row["message_id"],
                            "from": row["from_email"],
                            "subject": row["subject"][:60],
                            "actual_type": row.get("email_type"),
                        }
                    )

        if false_positives:
            print(f"\n⚠️  False positives: non-events matched as events ({len(false_positives)}):")
            for fp in false_positives[:5]:
                print(f"  - {fp['from']}: {fp['subject']} (actually {fp['actual_type']})")

        # Allow up to 1% false positive rate (very conservative)
        total_non_events = 500 - 56  # 444 non-events
        max_allowed_fps = int(total_non_events * 0.01)  # 1% = 4 emails

        assert len(false_positives) <= max_allowed_fps, (
            f"Too many false positives: {len(false_positives)} (max allowed: {max_allowed_fps})"
        )


class TestSpecificGDSCases:
    """Test specific known cases from gds-1.0."""

    def test_notification_subject_with_at_symbol(self):
        """
        Subject like 'Notification: Meeting @ Wed Nov 13' should match as event.

        This is a common Google Calendar format that was being misclassified.
        """
        mapper = TypeMapper()

        result = mapper.get_deterministic_type(
            sender_email="calendar-notification@google.com",
            subject="Notification: Team Sync @ Wed Nov 13, 2pm – 3pm (PST)",
            snippet="You have a calendar event",
        )

        assert result is not None
        assert result["type"] == "event"

    def test_updated_invitation_format(self):
        """'Updated invitation:' emails should match as event."""
        mapper = TypeMapper()

        result = mapper.get_deterministic_type(
            sender_email="noreply@calendar.google.com",
            subject="Updated invitation: Project Review",
            snippet="The details of this event have changed",
        )

        assert result is not None
        assert result["type"] == "event"

    def test_eventbrite_invitation(self):
        """Eventbrite event emails should match as event."""
        mapper = TypeMapper()

        result = mapper.get_deterministic_type(
            sender_email="events@eventbrite.com",
            subject="You're going to Tech Conference 2025",
            snippet="Your ticket for Tech Conference",
        )

        assert result is not None
        assert result["type"] == "event"


class TestMetrics:
    """Calculate and report type mapper performance metrics."""

    def test_report_type_mapper_coverage(self):
        """
        Report type mapper coverage across all gds-1.0 emails.

        This is not a pass/fail test, just metrics for monitoring.
        """
        if not GDS_PATH.exists():
            pytest.skip(f"Golden dataset not found: {GDS_PATH}")

        mapper = TypeMapper()
        total = 0
        matched = 0
        matched_as_event = 0

        with open(GDS_PATH, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                total += 1
                sender_email = extract_email_address(row["from_email"])
                result = mapper.get_deterministic_type(sender_email, row["subject"], row["snippet"])

                if result:
                    matched += 1
                    if result["type"] == "event":
                        matched_as_event += 1

        coverage_rate = matched / total if total > 0 else 0
        event_rate = matched_as_event / total if total > 0 else 0

        print("\n📊 Type Mapper Coverage on gds-1.0:")
        print(f"  Total emails: {total}")
        print(f"  Matched by type mapper: {matched} ({coverage_rate:.1%})")
        print(f"  Matched as event: {matched_as_event} ({event_rate:.1%})")

        # This is informational, not an assertion
        # MVP target: 10-15% coverage (conservative scope)
        assert True  # Always pass, just report metrics
