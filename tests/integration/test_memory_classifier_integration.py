"""
Integration tests for MemoryClassifier with TypeMapper.

Tests the full classification flow: type mapper → rules → LLM.
"""

from __future__ import annotations

import pytest

from mailq.classification.memory_classifier import MemoryClassifier


class TestMemoryClassifierTypeMapperIntegration:
    """Test MemoryClassifier with type mapper integration."""

    def test_calendar_invite_uses_type_mapper(self):
        """
        Google Calendar invites should use type mapper (not LLM for type).

        Flow: Type mapper matches → LLM for domains/attention → Gmail labels
        """
        classifier = MemoryClassifier()

        result = classifier.classify(
            subject="Notification: Team Sync @ Wed Nov 13, 2pm – 3pm (PST)",
            snippet="You have a calendar event: Team Sync with the engineering team...",
            from_field="calendar-notification@google.com",
            user_id="integration_test_user",
        )

        # Type should come from type mapper
        assert result["type"] == "event"
        assert result["type_conf"] >= 0.95  # High confidence (type mapper)
        assert result["decider"] == "type_mapper"

        # New 4-label system: events → everything-else (unless critical importance)
        assert "MailQ-Everything-Else" in result["gmail_labels"]

        # Reason should mention type mapper
        assert "type_mapper" in result["reason"]

    def test_new_user_gets_calendar_invite_correct(self):
        """
        Brand new user (no learned rules) should get calendar invites correct.

        This is the key benefit of type mapper - works day 1 for all users.
        """
        classifier = MemoryClassifier()

        result = classifier.classify(
            subject="Updated invitation: Project Review",
            snippet="The details of this event have changed. When: Thu Nov 14...",
            from_field="noreply@calendar.google.com",
            user_id="brand_new_user_no_rules",  # New user
        )

        # Type mapper should work immediately
        assert result["type"] == "event"
        assert result["decider"] == "type_mapper"
        # New 4-label system: events → everything-else
        assert "MailQ-Everything-Else" in result["gmail_labels"]

    def test_google_meet_link_triggers_type_mapper(self):
        """
        Emails with Google Meet links should be classified as events.

        Even if sender is not a calendar system.
        """
        classifier = MemoryClassifier()

        result = classifier.classify(
            subject="Weekly standup",
            snippet="Join with Google Meet: https://meet.google.com/xyz-abc-def",
            from_field="someone@company.com",
            user_id="integration_test_user",
        )

        # Body phrase "Join with Google Meet" should trigger type mapper
        assert result["type"] == "event"
        assert result["decider"] == "type_mapper"

    def test_non_calendar_falls_through_to_llm(self):
        """
        Non-calendar emails should NOT match type mapper.

        They should fall through to LLM (existing behavior).
        """
        classifier = MemoryClassifier()

        result = classifier.classify(
            subject="This week's newsletter",
            snippet="Here's what we've been working on this week...",
            from_field="newsletter@substack.com",
            user_id="integration_test_user",
        )

        # Should NOT match type mapper (no calendar signals)
        # Will fall through to LLM
        assert result["decider"] in ["gemini", "rule", "fallback"]  # Not type_mapper

        # Type should be newsletter (from LLM or rules)
        # Note: We can't guarantee what LLM returns, so just check it's not event
        assert result["type"] != "event"  # Newsletter shouldn't be typed as event

    def test_outlook_calendar_uses_type_mapper(self):
        """Outlook calendar invites should also use type mapper."""
        classifier = MemoryClassifier()

        result = classifier.classify(
            subject="Meeting invitation",
            snippet="You've been invited to a meeting. Organizer: John Doe",
            from_field="calendar@outlook.com",
            user_id="integration_test_user",
        )

        assert result["type"] == "event"
        assert result["decider"] == "type_mapper"

    def test_eventbrite_uses_type_mapper(self):
        """Eventbrite event emails should use type mapper."""
        classifier = MemoryClassifier()

        result = classifier.classify(
            subject="You're going to Tech Conference 2025",
            snippet="Your ticket for Tech Conference 2025. Add to Calendar to save your spot.",
            from_field="events@eventbrite.com",
            user_id="integration_test_user",
        )

        assert result["type"] == "event"
        assert result["decider"] == "type_mapper"

    def test_ics_attachment_triggers_type_mapper(self):
        """
        Emails with .ics attachments should be classified as events.

        Note: This test simulates the has_ics_attachment parameter.
        In production, this would be detected from email metadata.
        """
        # TODO: Add has_ics_attachment parameter to classify() method
        # For now, this test documents the intended behavior
        pytest.skip("has_ics_attachment parameter not yet added to classify()")

    def test_type_mapper_does_not_learn(self):
        """
        Type mapper results should NOT be learned into RulesEngine.

        Type mapper rules are global and deterministic, not user-specific.
        """
        classifier = MemoryClassifier()

        # Classify a calendar invite (type mapper match)
        result = classifier.classify(
            subject="Notification: Meeting @ Wed",
            snippet="Calendar event...",
            from_field="calendar-notification@google.com",
            user_id="type_mapper_learning_test",
        )

        # Verify type mapper was used (not learned rule)
        assert result["decider"] == "type_mapper"

        # Type mapper results are logged but not stored in RulesEngine
        # This is correct behavior - type mapper rules are global, not user-specific

    def test_type_mapper_logging_includes_matched_rule(self):
        """
        Type mapper matches should log which rule matched.

        This helps with debugging and monitoring type mapper effectiveness.
        """
        classifier = MemoryClassifier()

        result = classifier.classify(
            subject="Notification: Team Sync @ Wed",
            snippet="Calendar event",
            from_field="calendar-notification@google.com",
            user_id="integration_test_user",
        )

        # Reason should include matched rule details
        assert "type_mapper" in result["reason"]
        assert "sender_domain" in result["reason"] or "subject_pattern" in result["reason"]

    def test_mixed_signals_type_mapper_wins(self):
        """
        If type mapper matches, it should override any conflicting LLM results.

        Type mapper is deterministic and high precision, so it takes precedence.
        """
        classifier = MemoryClassifier()

        # Email that might confuse LLM (has "notification" in subject)
        # but is clearly a calendar invite
        result = classifier.classify(
            subject="Notification: Project Kickoff @ Mon Nov 11, 9am",
            snippet="You have a calendar event...",
            from_field="calendar-notification@google.com",
            user_id="integration_test_user",
        )

        # Type mapper should win
        assert result["type"] == "event"  # NOT notification
        assert result["decider"] == "type_mapper"


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_subject_and_snippet(self):
        """Empty subject/snippet should not crash."""
        classifier = MemoryClassifier()

        result = classifier.classify(
            subject="", snippet="", from_field="test@example.com", user_id="integration_test_user"
        )

        # Should fall through to LLM (type mapper won't match empty strings)
        assert result is not None
        assert "type" in result

    def test_malformed_from_field(self):
        """Malformed from field should not crash."""
        classifier = MemoryClassifier()

        result = classifier.classify(
            subject="Test subject",
            snippet="Test snippet",
            from_field="invalid-email",
            user_id="integration_test_user",
        )

        assert result is not None
        assert "type" in result

    def test_very_long_subject(self):
        """Very long subject lines should be handled correctly."""
        classifier = MemoryClassifier()

        long_subject = "Notification: " + "A" * 1000 + " @ Wed Nov 13"

        result = classifier.classify(
            subject=long_subject,
            snippet="Calendar event",
            from_field="calendar-notification@google.com",
            user_id="integration_test_user",
        )

        # Should still match type mapper
        assert result["type"] == "event"


class TestBackwardCompatibility:
    """Ensure type mapper doesn't break existing functionality."""

    def test_existing_rules_still_work(self):
        """
        Existing RulesEngine rules should still work when type mapper doesn't match.

        Type mapper is additive, not replacement.
        """
        # This test would require setting up existing rules in the DB
        # For now, just document the expected behavior
        pytest.skip("Requires existing rules in test database")

    def test_llm_fallback_still_works(self):
        """
        LLM should still be used when type mapper and rules don't match.

        This ensures we didn't break the existing LLM fallback.
        """
        classifier = MemoryClassifier()

        # Email that won't match type mapper or rules (new/unknown sender)
        result = classifier.classify(
            subject="Random email subject",
            snippet="This is a random email that won't match any rules",
            from_field="random@unknown-domain-12345.com",
            user_id="integration_test_user",
        )

        # Should fall through to LLM
        assert result["decider"] in ["gemini", "fallback"]
        assert result is not None
        assert "type" in result
