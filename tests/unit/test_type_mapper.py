"""
Unit tests for TypeMapper - global deterministic type classification.

Tests cover:
- Domain matching (exact and wildcard)
- Subject pattern matching (regex)
- Body phrase matching
- ICS attachment detection
- Fallback behavior (no match)
"""

from __future__ import annotations

from mailq.classification.type_mapper import TypeMapper, get_type_mapper


class TestTypeMapper:
    """Test TypeMapper class functionality."""

    def test_init_loads_config(self):
        """TypeMapper should load rules from config on init."""
        mapper = TypeMapper()

        assert mapper.version == "1.0"
        assert "event" in mapper.rules
        assert isinstance(mapper.rules["event"], dict)

    def test_singleton_get_type_mapper(self):
        """get_type_mapper() should return same instance."""
        mapper1 = get_type_mapper()
        mapper2 = get_type_mapper()

        assert mapper1 is mapper2  # Same instance

    def test_google_calendar_notification_exact_match(self):
        """Google Calendar notifications should match as event."""
        mapper = TypeMapper()

        result = mapper.get_deterministic_type(
            sender_email="calendar-notification@google.com",
            subject="Notification: Team Sync @ Wed Nov 13, 2pm – 3pm (PST)",
            snippet="You have a calendar event: Team Sync...",
        )

        assert result is not None
        assert result["type"] == "event"
        assert result["confidence"] == 0.98
        assert "sender_domain" in result["matched_rule"]
        assert result["decider"] == "type_mapper"

    def test_google_calendar_subject_pattern_match(self):
        """Subject pattern 'Notification: X @ Day' should match as event."""
        mapper = TypeMapper()

        result = mapper.get_deterministic_type(
            sender_email="unknown@example.com",
            subject="Notification: Project Review @ Mon Nov 11, 3pm",
            snippet="Meeting details...",
        )

        assert result is not None
        assert result["type"] == "event"
        assert "subject_pattern" in result["matched_rule"]

    def test_updated_invitation_subject_match(self):
        """Subject 'Updated invitation:' should match as event."""
        mapper = TypeMapper()

        result = mapper.get_deterministic_type(
            sender_email="unknown@example.com",  # Use non-calendar sender to test subject pattern
            subject="Updated invitation: Quarterly Planning",
            snippet="The details of this event have changed...",
        )

        assert result is not None
        assert result["type"] == "event"
        assert "subject_pattern" in result["matched_rule"]

    def test_google_meet_body_phrase_match(self):
        """Body phrase 'Join with Google Meet' should match as event."""
        mapper = TypeMapper()

        result = mapper.get_deterministic_type(
            sender_email="someone@company.com",
            subject="Weekly standup",
            snippet="Join with Google Meet: https://meet.google.com/xyz",
        )

        assert result is not None
        assert result["type"] == "event"
        assert "body_phrase" in result["matched_rule"]
        assert "Join with Google Meet" in result["matched_rule"]

    def test_zoom_meeting_body_phrase_match(self):
        """Body phrase 'Join Zoom Meeting' should match as event."""
        mapper = TypeMapper()

        result = mapper.get_deterministic_type(
            sender_email="zoom@example.com",
            subject="Meeting invitation",
            snippet="Join Zoom Meeting: https://zoom.us/j/123456",
        )

        assert result is not None
        assert result["type"] == "event"
        assert "body_phrase" in result["matched_rule"]

    def test_add_to_calendar_body_phrase_match(self):
        """Body phrase 'Add to Calendar' should match as event."""
        mapper = TypeMapper()

        result = mapper.get_deterministic_type(
            sender_email="unknown@example.com",  # Use non-calendar sender to test body phrase
            subject="Tech Conference 2025",
            snippet="You're invited! Add to Calendar to save your spot.",
        )

        assert result is not None
        assert result["type"] == "event"
        assert "body_phrase" in result["matched_rule"]

    def test_ics_attachment_match(self):
        """ICS attachment should match as event."""
        mapper = TypeMapper()

        result = mapper.get_deterministic_type(
            sender_email="organizer@company.com",
            subject="Meeting invitation",
            snippet="Please see attached calendar invite",
            has_ics_attachment=True,
        )

        assert result is not None
        assert result["type"] == "event"
        assert "attachment" in result["matched_rule"]
        assert ".ics" in result["matched_rule"]

    def test_wildcard_domain_match(self):
        """Wildcard domain pattern should match."""
        mapper = TypeMapper()

        # Test that wildcard *@google.com would match various google.com addresses
        # Note: Our current config uses exact matches, but the code supports wildcards
        assert mapper._matches_domain("calendar-notification@google.com", "*@google.com")
        assert mapper._matches_domain("user@google.com", "*@google.com")
        assert not mapper._matches_domain("user@gmail.com", "*@google.com")

    def test_exact_domain_match(self):
        """Exact domain should match only exact address."""
        mapper = TypeMapper()

        assert mapper._matches_domain(
            "calendar-notification@google.com", "calendar-notification@google.com"
        )
        assert not mapper._matches_domain("user@google.com", "calendar-notification@google.com")

    def test_case_insensitive_matching(self):
        """Matching should be case-insensitive."""
        mapper = TypeMapper()

        result = mapper.get_deterministic_type(
            sender_email="Calendar-Notification@Google.COM",  # Mixed case
            subject="NOTIFICATION: Meeting @ Wed",  # Uppercase
            snippet="You Have A Calendar Event",
        )

        assert result is not None
        assert result["type"] == "event"

    def test_no_match_returns_none(self):
        """Emails that don't match any rule should return None."""
        mapper = TypeMapper()

        result = mapper.get_deterministic_type(
            sender_email="newsletter@substack.com",
            subject="This week's article",
            snippet="Here's what I've been thinking about...",
        )

        assert result is None  # No match, will fall back to LLM

    def test_amazon_email_no_match(self):
        """Amazon emails should NOT match (receipts not in MVP scope)."""
        mapper = TypeMapper()

        result = mapper.get_deterministic_type(
            sender_email="auto-confirm@amazon.com",
            subject="Order Confirmation",
            snippet="Thank you for your order #123-456",
        )

        assert result is None  # Receipts not in scope for MVP

    def test_generic_notification_no_match(self):
        """Generic notifications should NOT match (high precision)."""
        mapper = TypeMapper()

        result = mapper.get_deterministic_type(
            sender_email="notifications@github.com",
            subject="New pull request opened",
            snippet="User opened a pull request...",
        )

        assert result is None  # Generic notifications not in scope

    def test_multiple_rules_first_match_wins(self):
        """If multiple rules match, first match should win."""
        mapper = TypeMapper()

        # Email that matches both sender domain AND subject pattern
        result = mapper.get_deterministic_type(
            sender_email="calendar-notification@google.com",
            subject="Notification: Meeting @ Wed",
            snippet="Calendar event",
        )

        assert result is not None
        assert result["type"] == "event"
        # Should match sender domain first (checked before subject patterns)
        assert "sender_domain" in result["matched_rule"]

    def test_outlook_calendar_match(self):
        """Outlook calendar invites should match."""
        mapper = TypeMapper()

        result = mapper.get_deterministic_type(
            sender_email="calendar@outlook.com",
            subject="Meeting invitation",
            snippet="You've been invited to a meeting",
        )

        assert result is not None
        assert result["type"] == "event"

    def test_yahoo_calendar_match(self):
        """Yahoo calendar invites should match."""
        mapper = TypeMapper()

        result = mapper.get_deterministic_type(
            sender_email="calendar@yahoo.com",
            subject="Event reminder",
            snippet="Your event is coming up",
        )

        assert result is not None
        assert result["type"] == "event"

    def test_eventbrite_match(self):
        """Eventbrite event emails should match."""
        mapper = TypeMapper()

        result = mapper.get_deterministic_type(
            sender_email="events@eventbrite.com",
            subject="You're going to Tech Conference",
            snippet="Your ticket for Tech Conference...",
        )

        assert result is not None
        assert result["type"] == "event"

    def test_accepted_invitation_subject(self):
        """'Accepted:' subject prefix should match as event."""
        mapper = TypeMapper()

        result = mapper.get_deterministic_type(
            sender_email="unknown@example.com",  # Use non-calendar sender to test subject pattern
            subject="Accepted: Team Lunch @ Fri",
            snippet="User has accepted the invitation",
        )

        assert result is not None
        assert result["type"] == "event"
        assert "subject_pattern" in result["matched_rule"]

    def test_canceled_event_subject(self):
        """'Canceled:' subject prefix should match as event."""
        mapper = TypeMapper()

        result = mapper.get_deterministic_type(
            sender_email="calendar@outlook.com",
            subject="Canceled: Project Kickoff",
            snippet="This event has been canceled",
        )

        assert result is not None
        assert result["type"] == "event"

    def test_invalid_regex_pattern_graceful_fallback(self):
        """Invalid regex patterns should be skipped gracefully."""
        mapper = TypeMapper()

        # Temporarily add invalid regex (for testing error handling)
        # In production, this would be caught during config validation
        mapper.rules["event"]["subject_patterns"].append("[invalid(regex")

        # Should still work with other valid patterns
        result = mapper.get_deterministic_type(
            sender_email="calendar-notification@google.com", subject="Test", snippet="Test"
        )

        assert result is not None  # Should match on sender domain
        assert result["type"] == "event"

    def test_empty_strings_no_match(self):
        """Empty subject/snippet should not crash."""
        mapper = TypeMapper()

        result = mapper.get_deterministic_type(
            sender_email="test@example.com", subject="", snippet=""
        )

        assert result is None  # No match on empty strings

    def test_whitespace_handling(self):
        """Whitespace should be handled correctly."""
        mapper = TypeMapper()

        result = mapper.get_deterministic_type(
            sender_email="  calendar-notification@google.com  ",  # Leading/trailing space
            subject="  Notification: Meeting @ Wed  ",
            snippet="  Calendar event  ",
        )

        assert result is not None
        assert result["type"] == "event"


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_missing_config_file_graceful_fallback(self, tmp_path):
        """Missing config file should not crash, return empty rules."""
        fake_path = tmp_path / "nonexistent.yaml"

        mapper = TypeMapper(rules_path=fake_path)

        assert mapper.rules == {}
        assert mapper.version == "unknown"

        # Should return None for any email
        result = mapper.get_deterministic_type("test@example.com", "Test", "Test")
        assert result is None

    def test_corrupted_yaml_graceful_fallback(self, tmp_path):
        """Corrupted YAML should not crash."""
        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text("{ invalid: yaml: [}")

        mapper = TypeMapper(rules_path=bad_yaml)

        assert mapper.rules == {} or mapper.rules is None

    def test_empty_yaml_file(self, tmp_path):
        """Empty YAML file should load gracefully."""
        empty_yaml = tmp_path / "empty.yaml"
        empty_yaml.write_text("")

        mapper = TypeMapper(rules_path=empty_yaml)

        assert mapper.rules == {}
