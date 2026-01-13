"""
Tests for Phase 4: Deterministic Temporal Decay

Ensures expired events don't appear as time_sensitive,
and imminent events escalate to critical automatically.

Based on gds-1.0 schema (tests/golden_set/GDS_SCHEMA_v1.0.md)
"""

from datetime import UTC, datetime, timedelta

import pytest

from mailq.classification.temporal import (
    deterministic_temporal_updownrank,
    get_digest_section,
    resolve_temporal_importance,
    should_show_in_digest,
)


@pytest.fixture
def now():
    """Fixed 'now' for deterministic tests."""
    return datetime(2025, 11, 9, 12, 0, 0, tzinfo=UTC)


class TestExpiredEvents:
    """Rule 1: Expired events (>1h past end) → routine"""

    def test_expired_event_downgraded_to_routine(self, now):
        """Event ended 2h ago should be routine regardless of stored importance."""
        result = resolve_temporal_importance(
            email_type="event",
            stored_importance="time_sensitive",
            temporal_start=now - timedelta(hours=3),
            temporal_end=now - timedelta(hours=2),  # Ended 2h ago
            now=now,
        )
        assert result.resolved_importance == "routine"
        assert result.decay_reason == "temporal_expired"
        assert result.was_modified is True

    def test_expired_deadline_downgraded(self, now):
        """Deadline passed 2h ago should be routine."""
        result = resolve_temporal_importance(
            email_type="deadline",
            stored_importance="critical",
            temporal_start=now - timedelta(hours=2),  # Due 2h ago
            temporal_end=None,  # Deadlines don't have end
            now=now,
        )
        # Deadlines expire based on temporal_start (due date) + grace_period
        # A deadline 2h past due should be routine (expired)
        assert result.resolved_importance == "routine"
        assert result.decay_reason == "temporal_expired"
        assert result.was_modified == True

    def test_within_grace_period_still_active(self, now):
        """Event ended 30 min ago (within 1h grace) should still be active."""
        result = resolve_temporal_importance(
            email_type="event",
            stored_importance="routine",
            temporal_start=now - timedelta(hours=1, minutes=30),
            temporal_end=now - timedelta(minutes=30),  # Ended 30 min ago
            now=now,
        )
        # Within grace period, so active rule applies
        assert result.resolved_importance == "critical"
        assert result.decay_reason == "temporal_active"

    def test_expired_not_shown_in_digest(self, now):
        """Expired events should be hidden from digest."""
        should_show = should_show_in_digest(
            email_type="event",
            resolved_importance="routine",
            temporal_end=now - timedelta(hours=2),
            now=now,
        )
        assert should_show is False


class TestActiveEvents:
    """Rule 2: Active events (±1h window) → critical"""

    def test_event_starting_in_30_minutes_critical(self, now):
        """Event starting in 30 min should escalate to critical."""
        result = resolve_temporal_importance(
            email_type="event",
            stored_importance="routine",
            temporal_start=now + timedelta(minutes=30),
            temporal_end=now + timedelta(hours=1, minutes=30),
            now=now,
        )
        assert result.resolved_importance == "critical"
        assert result.decay_reason == "temporal_active"
        assert result.was_modified is True

    def test_event_starting_now_critical(self, now):
        """Event starting right now should be critical."""
        result = resolve_temporal_importance(
            email_type="event",
            stored_importance="routine",
            temporal_start=now,
            temporal_end=now + timedelta(hours=1),
            now=now,
        )
        assert result.resolved_importance == "critical"
        assert result.decay_reason == "temporal_active"

    def test_deadline_due_in_30_minutes_critical(self, now):
        """Deadline due in 30 min should be critical."""
        result = resolve_temporal_importance(
            email_type="deadline",
            stored_importance="time_sensitive",
            temporal_start=now + timedelta(minutes=30),
            temporal_end=None,
            now=now,
        )
        assert result.resolved_importance == "critical"
        assert result.decay_reason == "temporal_active"

    def test_event_in_progress_critical(self, now):
        """Event that started 30 min ago and ends in 30 min should be critical."""
        result = resolve_temporal_importance(
            email_type="event",
            stored_importance="routine",
            temporal_start=now - timedelta(minutes=30),
            temporal_end=now + timedelta(minutes=30),
            now=now,
        )
        assert result.resolved_importance == "critical"
        assert result.decay_reason == "temporal_active"


class TestUpcomingEvents:
    """Rule 3: Upcoming ≤7 days → time_sensitive"""

    def test_event_tomorrow_time_sensitive(self, now):
        """Event tomorrow should be time_sensitive."""
        result = resolve_temporal_importance(
            email_type="event",
            stored_importance="routine",
            temporal_start=now + timedelta(days=1),
            temporal_end=now + timedelta(days=1, hours=1),
            now=now,
        )
        assert result.resolved_importance == "time_sensitive"
        assert result.decay_reason == "temporal_upcoming"
        assert result.was_modified is True

    def test_event_in_3_days_time_sensitive(self, now):
        """Event in 3 days should be time_sensitive."""
        result = resolve_temporal_importance(
            email_type="event",
            stored_importance="routine",
            temporal_start=now + timedelta(days=3),
            temporal_end=now + timedelta(days=3, hours=2),
            now=now,
        )
        assert result.resolved_importance == "time_sensitive"
        assert result.decay_reason == "temporal_upcoming"

    def test_event_in_7_days_time_sensitive(self, now):
        """Event in exactly 7 days should be time_sensitive (boundary)."""
        result = resolve_temporal_importance(
            email_type="event",
            stored_importance="routine",
            temporal_start=now + timedelta(days=7),
            temporal_end=now + timedelta(days=7, hours=1),
            now=now,
        )
        assert result.resolved_importance == "time_sensitive"
        assert result.decay_reason == "temporal_upcoming"

    def test_upcoming_preserves_critical(self, now):
        """Upcoming event that LLM marked critical should stay critical."""
        result = resolve_temporal_importance(
            email_type="event",
            stored_importance="critical",
            temporal_start=now + timedelta(days=3),
            temporal_end=now + timedelta(days=3, hours=1),
            now=now,
        )
        assert result.resolved_importance == "critical"  # Escalate preserves critical
        assert result.was_modified is False


class TestDistantEvents:
    """Rule 4: Distant >7 days → routine (unless critical)"""

    def test_event_in_10_days_routine(self, now):
        """Event in 10 days should be routine."""
        result = resolve_temporal_importance(
            email_type="event",
            stored_importance="time_sensitive",
            temporal_start=now + timedelta(days=10),
            temporal_end=now + timedelta(days=10, hours=1),
            now=now,
        )
        assert result.resolved_importance == "routine"
        assert result.decay_reason == "temporal_distant"
        assert result.was_modified is True

    def test_distant_critical_preserved(self, now):
        """Distant event marked critical by LLM should stay critical."""
        result = resolve_temporal_importance(
            email_type="event",
            stored_importance="critical",
            temporal_start=now + timedelta(days=30),
            temporal_end=now + timedelta(days=30, hours=2),
            now=now,
        )
        assert result.resolved_importance == "critical"
        assert result.decay_reason == "temporal_distant_but_critical"
        assert result.was_modified is False


class TestNonTemporalTypes:
    """Non-event/deadline types should pass through unchanged."""

    def test_notification_unchanged(self, now):
        """Notifications without OTP/shipping fields use standard temporal decay."""
        # Notifications now support temporal decay (for OTP/shipping)
        # Without OTP/shipping entity fields, they follow standard temporal rules
        result = resolve_temporal_importance(
            email_type="notification",
            stored_importance="critical",
            temporal_start=None,  # No temporal fields
            temporal_end=None,
            now=now,
        )
        assert result.resolved_importance == "critical"
        assert result.decay_reason == "no_temporal_data"
        assert result.was_modified is False

    def test_receipt_unchanged(self, now):
        """Receipts don't use temporal decay."""
        result = resolve_temporal_importance(
            email_type="receipt",
            stored_importance="routine",
            temporal_start=None,
            temporal_end=None,
            now=now,
        )
        assert result.resolved_importance == "routine"
        assert result.decay_reason == "non_temporal_type"

    def test_promo_unchanged(self, now):
        """Promos don't use temporal decay."""
        result = resolve_temporal_importance(
            email_type="promo",
            stored_importance="routine",
            temporal_start=None,
            temporal_end=None,
            now=now,
        )
        assert result.resolved_importance == "routine"


class TestMissingTemporalData:
    """Events without temporal data should pass through unchanged."""

    def test_event_without_temporal_start(self, now):
        """Event without temporal_start can't apply decay."""
        result = resolve_temporal_importance(
            email_type="event",
            stored_importance="time_sensitive",
            temporal_start=None,
            temporal_end=None,
            now=now,
        )
        assert result.resolved_importance == "time_sensitive"
        assert result.decay_reason == "no_temporal_data"
        assert result.was_modified is False


class TestDigestMapping:
    """Test digest section mapping."""

    def test_critical_maps_to_today(self):
        """Critical importance → TODAY section."""
        section = get_digest_section("critical")
        assert section == "TODAY"

    def test_time_sensitive_maps_to_coming_up(self):
        """Time-sensitive importance → COMING_UP section."""
        section = get_digest_section("time_sensitive")
        assert section == "COMING_UP"

    def test_routine_maps_to_worth_knowing(self):
        """Routine importance → WORTH_KNOWING section."""
        section = get_digest_section("routine")
        assert section == "WORTH_KNOWING"


class TestDigestVisibility:
    """Test should_show_in_digest logic."""

    def test_non_events_always_show(self, now):
        """Non-events always show regardless of temporal state."""
        assert should_show_in_digest("notification", "routine", None, now) is True
        assert should_show_in_digest("receipt", "routine", None, now) is True

    def test_expired_event_hidden(self, now):
        """Expired event should be hidden."""
        assert should_show_in_digest("event", "routine", now - timedelta(hours=2), now) is False

    def test_upcoming_event_shown(self, now):
        """Upcoming event should be shown."""
        assert (
            should_show_in_digest("event", "time_sensitive", now + timedelta(days=1), now) is True
        )

    def test_event_without_end_shown(self, now):
        """Event without end time should be shown."""
        assert should_show_in_digest("event", "time_sensitive", None, now) is True


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_timezone_naive_converted_to_utc(self, now):
        """Timezone-naive datetimes should be treated as UTC."""
        naive_start = datetime(2025, 11, 10, 12, 0, 0)  # Tomorrow, no tzinfo
        result = resolve_temporal_importance(
            email_type="event",
            stored_importance="routine",
            temporal_start=naive_start,
            temporal_end=naive_start + timedelta(hours=1),
            now=now,
        )
        # Should be treated as tomorrow → time_sensitive
        assert result.resolved_importance == "time_sensitive"

    def test_backward_compatibility_function(self, now):
        """Legacy function name should work."""
        importance, reason = deterministic_temporal_updownrank(
            email_type="event",
            stored_importance="routine",
            temporal_start=now + timedelta(minutes=30),
            temporal_end=now + timedelta(hours=1, minutes=30),
            now=now,
        )
        assert importance == "critical"
        assert reason == "temporal_active"


class TestRegressionSuite:
    """Regression tests from gds-1.0 schema."""

    def test_lunch_ended_1h_ago_hidden(self, now):
        """Example: Lunch ended 1h ago → hidden from digest."""
        temporal_end = now - timedelta(hours=1, minutes=1)
        result = resolve_temporal_importance(
            email_type="event",
            stored_importance="time_sensitive",
            temporal_start=now - timedelta(hours=2),
            temporal_end=temporal_end,
            now=now,
        )
        assert result.resolved_importance == "routine"
        assert (
            should_show_in_digest("event", result.resolved_importance, temporal_end, now) is False
        )

    def test_dinner_tomorrow_coming_up(self, now):
        """Example: Dinner tomorrow at 7pm → Coming Up section."""
        result = resolve_temporal_importance(
            email_type="event",
            stored_importance="routine",
            temporal_start=now + timedelta(days=1, hours=7),
            temporal_end=now + timedelta(days=1, hours=9),
            now=now,
        )
        assert result.resolved_importance == "time_sensitive"
        assert get_digest_section(result.resolved_importance) == "COMING_UP"

    def test_meeting_in_30_min_today(self, now):
        """Example: Meeting in 30 min → NOW section (critical)."""
        result = resolve_temporal_importance(
            email_type="event",
            stored_importance="routine",
            temporal_start=now + timedelta(minutes=30),
            temporal_end=now + timedelta(hours=1),
            now=now,
        )
        assert result.resolved_importance == "critical"
        assert get_digest_section(result.resolved_importance) == "TODAY"

    def test_bill_due_friday_coming_up(self, now):
        """Example: Bill due Friday (3 days) → Coming Up section."""
        result = resolve_temporal_importance(
            email_type="deadline",
            stored_importance="routine",
            temporal_start=now + timedelta(days=3),
            temporal_end=None,
            now=now,
        )
        assert result.resolved_importance == "time_sensitive"
        assert get_digest_section(result.resolved_importance) == "COMING_UP"

    def test_invoice_passed_2h_ago_archived(self, now):
        """Example: Invoice due noon (passed 2h ago) → archived."""
        temporal_end = now - timedelta(hours=2)
        result = resolve_temporal_importance(
            email_type="deadline",
            stored_importance="critical",
            temporal_start=temporal_end,
            temporal_end=temporal_end,
            now=now,
        )
        assert result.resolved_importance == "routine"
        assert (
            should_show_in_digest("deadline", result.resolved_importance, temporal_end, now)
            is False
        )

    def test_flight_in_2_weeks_worth_knowing(self, now):
        """Example: Flight in 2 weeks → Worth Knowing section."""
        result = resolve_temporal_importance(
            email_type="event",
            stored_importance="time_sensitive",
            temporal_start=now + timedelta(days=14),
            temporal_end=now + timedelta(days=14, hours=2),
            now=now,
        )
        assert result.resolved_importance == "routine"
        assert get_digest_section(result.resolved_importance) == "WORTH_KNOWING"
