"""

from __future__ import annotations

Tests for time-decay filter (expired events)

Test cases based on user-labeled ground truth data (99 emails).
"""

from datetime import datetime

import pytest

from shopq.classification.temporal import filter_expired_events, is_expired_event


class TestExpiredEventDetection:
    """Test detection of expired/past events"""

    def test_calendar_acceptance_past_event(self):
        """
        User feedback: "Accepted: Victor @ Tue Nov 18" sent Oct 31 but event hasn't happened yet
        Should NOT filter (event is in future)
        """
        email = {
            "subject": "Accepted: Victor <> Justin in town in NYC @ Tue Nov 18, 2025 (Justin)",
            "snippet": "Victor Udoewa has accepted this invitation.",
            "date": "Fri, 31 Oct 2025 18:55:01 +0000",
        }

        # Test on Nov 1 (email sent Oct 31, event is Nov 18)
        now = datetime(2025, 11, 1, 12, 0, 0)
        assert not is_expired_event(email, now)  # Event is future → keep

        # Test on Nov 19 (after event happened)
        now = datetime(2025, 11, 19, 12, 0, 0)
        assert is_expired_event(email, now)  # Event passed → filter

    def test_starts_in_reminder_expired(self):
        """
        User marked "Drawing Hive starts in 1 hour" as NO (past event)
        """
        email = {
            "subject": "Don't forget: Drawing Hive starts in 1 hour",
            "snippet": 'Hi Justin K, We\'re kicking off "Drawing Hive" in 1 hour!',
            "date": "Thu, 30 Oct 2025 22:01:15 +0000 (UTC)",  # Oct 30 at 10pm
        }

        # Test on Oct 31 (event was Oct 30 at 11pm → already happened)
        now = datetime(2025, 10, 31, 12, 0, 0)
        assert is_expired_event(email, now)  # Event passed → filter

    def test_starts_in_reminder_future(self):
        """Event reminder for future event should NOT be filtered"""
        email = {
            "subject": "Don't forget: Drawing Hive starts in 1 hour",
            "snippet": 'Hi Justin K, We\'re kicking off "Drawing Hive" in 1 hour!',
            "date": "Thu, 30 Oct 2025 22:01:15 +0000 (UTC)",  # Oct 30 at 10pm
        }

        # Test same day, before event (Oct 30 at 9pm)
        now = datetime(2025, 10, 30, 21, 0, 0)
        assert not is_expired_event(email, now)  # Event is future → keep

    def test_event_notification_past(self):
        """
        Calendar notification for event that already happened
        """
        email = {
            "subject": (
                "Notification: J & V Catch-up @ Fri Oct 31, 2025 2pm - 2:25pm (EDT) (Justin)"
            ),
            "snippet": "You have been invited...",
            "date": "Fri, 31 Oct 2025 17:49:45 +0000",
        }

        # Test on Nov 1 (event was Oct 31 → passed)
        now = datetime(2025, 11, 1, 10, 0, 0)
        assert is_expired_event(email, now)  # Event passed → filter

    def test_event_notification_future(self):
        """Calendar notification for future event should NOT be filtered"""
        email = {
            "subject": (
                "Updated invitation: J & V Catch-up @ Fri Nov 7, 2025 2:05pm - 2:30pm (EST)"
            ),
            "snippet": "You have been invited...",
            "date": "Fri, 31 Oct 2025 08:26:54 +0000",
        }

        # Test on Nov 1 (event is Nov 7 → future)
        now = datetime(2025, 11, 1, 12, 0, 0)
        assert not is_expired_event(email, now)  # Event is future → keep

    def test_taskrabbit_past_event(self):
        """TaskRabbit booking for past date"""
        email = {
            "subject": "Your upcoming General Mounting task",
            "snippet": (
                "Your General Mounting task is booked Friday, October 31 Arriving at 9:00am EDT"
            ),
            "date": "Fri, 31 Oct 2025 02:07:12 +0000 (UTC)",
        }

        # Test on Nov 1 (task was Oct 31 → passed)
        now = datetime(2025, 11, 1, 12, 0, 0)
        # Note: This is tricky - we need to extract "October 31" from snippet
        # For now, this won't be filtered (snippet parsing not implemented)
        # But that's OK - main goal is calendar acceptances
        assert not is_expired_event(email, now)  # Not filtering yet (no snippet parsing)

    def test_non_event_email(self):
        """Non-event emails should NOT be filtered"""
        email = {
            "subject": "Your Con Edison bill is ready",
            "snippet": "Your Con Edison Bill is ready 11/01/2025 Amount to be deducted $186.56",
            "date": "Sat, 01 Nov 2025 13:06:32 +0000 (UTC)",
        }

        now = datetime(2025, 11, 1, 14, 0, 0)
        assert not is_expired_event(email, now)  # Not an event → keep


class TestFilterExpiredEvents:
    """Test batch filtering of emails"""

    def test_filter_removes_past_events(self):
        """Filter should remove past events, keep future events and non-events"""
        emails = [
            # Past event (should be filtered)
            {
                "subject": "Accepted: Event @ Tue Oct 29, 2025",
                "date": "Tue, 29 Oct 2025 10:00:00 +0000",
            },
            # Future event (should keep)
            {
                "subject": "Notification: Event @ Fri Nov 7, 2025",
                "date": "Fri, 31 Oct 2025 10:00:00 +0000",
            },
            # Non-event (should keep)
            {"subject": "Your bill is ready", "snippet": "Bill amount: $100"},
        ]

        now = datetime(2025, 11, 1, 12, 0, 0)
        filtered = filter_expired_events(emails, now)

        assert len(filtered) == 2  # Filtered 1 past event
        assert "Nov 7" in filtered[0]["subject"]  # Future event kept
        assert "bill" in filtered[1]["subject"]  # Non-event kept


class TestEdgeCases:
    """Test edge cases and boundary conditions"""

    def test_same_day_event_with_buffer(self):
        """Events happening today (within 2hr buffer) should NOT be filtered"""
        email = {
            "subject": "Notification: Event @ Fri Nov 1, 2025 10am",
            "date": "Fri, 01 Nov 2025 09:00:00 +0000",
        }

        # Test at 11am (event was 10am, but within 2hr buffer)
        now = datetime(2025, 11, 1, 11, 0, 0)
        assert not is_expired_event(email, now)  # Within buffer → keep

    def test_malformed_date(self):
        """Emails with unparseable dates should NOT be filtered (safe default)"""
        email = {"subject": "Accepted: Event @ ???", "date": "invalid date"}

        now = datetime(2025, 11, 1, 12, 0, 0)
        assert not is_expired_event(email, now)  # Can't parse → keep (safe)

    def test_missing_fields(self):
        """Emails missing subject/date should NOT be filtered"""
        email = {}

        now = datetime(2025, 11, 1, 12, 0, 0)
        assert not is_expired_event(email, now)  # Missing data → keep (safe)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
