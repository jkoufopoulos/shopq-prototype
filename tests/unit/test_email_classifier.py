"""
Unit tests for EmailClassifier orchestrator.

Tests the classification cascade and learning methods.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from shopq.classification.classifier import EmailClassifier, get_classifier
from shopq.observability.confidence import LEARNING_MIN_CONFIDENCE, USER_CORRECTION_CONFIDENCE
from shopq.storage.models import ClassifiedEmail, ParsedEmail, RawEmail


@pytest.fixture
def sample_email() -> ParsedEmail:
    """Create a sample parsed email for testing."""
    base = RawEmail(
        message_id="test-msg-001",
        thread_id="test-thread-001",
        received_ts=datetime.now().isoformat(),
        subject="Order confirmed - Thank you for your purchase",
        from_address="orders@amazon.com",
        to_address="user@test.com",
        body="Your order #12345 is confirmed. Receipt attached.",
    )
    return ParsedEmail(base=base, body_text=base.body, body_html=None)


@pytest.fixture
def otp_email() -> ParsedEmail:
    """Create a sample OTP email for testing."""
    base = RawEmail(
        message_id="test-otp-001",
        thread_id="test-otp-thread-001",
        received_ts=datetime.now().isoformat(),
        subject="Your verification code is 123456",
        from_address="noreply@bank.com",
        to_address="user@test.com",
        body="Your one-time verification code is 123456. Do not share this.",
    )
    return ParsedEmail(base=base, body_text=base.body, body_html=None)


@pytest.fixture
def calendar_email() -> ParsedEmail:
    """Create a sample calendar invite email for testing."""
    base = RawEmail(
        message_id="test-cal-001",
        thread_id="test-cal-thread-001",
        received_ts=datetime.now().isoformat(),
        subject="Invitation: Team Meeting @ Mon Dec 9",
        from_address="calendar-notification@google.com",
        to_address="user@test.com",
        body="You have been invited to Team Meeting. Join with Google Meet.",
    )
    return ParsedEmail(base=base, body_text=base.body, body_html=None)


class TestEmailClassifier:
    """Test EmailClassifier classify() cascade."""

    def test_classify_returns_classified_email(self, sample_email: ParsedEmail):
        """Test that classify returns a valid ClassifiedEmail."""
        classifier = EmailClassifier()

        # Use rules only (no LLM) for deterministic test
        result = classifier.classify(sample_email, use_rules=False, use_llm=False)

        assert isinstance(result, ClassifiedEmail)
        assert result.category in [
            "notification",
            "receipt",
            "promotion",
            "event",
            "newsletter",
            "message",
            "otp",
            "other",
        ]
        assert 0.0 <= result.confidence <= 1.0
        assert result.decider in ["type_mapper", "rule", "gemini", "fallback"]
        assert result.reason is not None

    def test_classify_fallback_for_receipt(self, sample_email: ParsedEmail):
        """Test fallback classification for receipt-like emails."""
        classifier = EmailClassifier()

        # With LLM disabled and no rules, should use fallback
        result = classifier.classify(sample_email, use_rules=False, use_llm=False)

        assert result.decider == "fallback"
        assert result.category == "receipt"  # "order" and "shipped" keywords

    def test_classify_fallback_for_otp(self, otp_email: ParsedEmail):
        """Test fallback classification for OTP emails."""
        classifier = EmailClassifier()

        result = classifier.classify(otp_email, use_rules=False, use_llm=False)

        assert result.decider == "fallback"
        assert result.category == "otp"  # "verification code" keyword

    def test_type_mapper_for_calendar(self, calendar_email: ParsedEmail):
        """Test TypeMapper detects calendar invites."""
        classifier = EmailClassifier()

        # TypeMapper should catch calendar-notification@google.com
        result = classifier.classify(calendar_email, use_rules=False, use_llm=False)

        assert result.decider == "type_mapper"
        assert result.category == "event"
        assert result.confidence >= 0.95

    def test_gmail_labels_property(self, sample_email: ParsedEmail):
        """Test that gmail_labels computed property works."""
        classifier = EmailClassifier()

        result = classifier.classify(sample_email, use_rules=False, use_llm=False)

        # Should have at least one label
        assert len(result.gmail_labels) >= 1
        # All labels should start with ShopQ-
        assert all(label.startswith("ShopQ-") for label in result.gmail_labels)


class TestClassifyAndLearn:
    """Test EmailClassifier.classify_and_learn() method."""

    def test_learns_from_high_confidence_gemini(self, sample_email: ParsedEmail):
        """Test that high-confidence Gemini classifications trigger learning."""
        classifier = EmailClassifier()
        mock_rules = MagicMock()
        classifier.rules = mock_rules

        # Mock LLM to return high-confidence result
        with patch.object(classifier.llm, "classify") as mock_llm:
            mock_llm.return_value = {
                "type": "receipt",
                "type_conf": 0.95,
                "attention": "none",
                "attention_conf": 0.9,
                "domains": ["shopping"],
                "domain_conf": {"shopping": 0.95},
                "importance": "routine",
                "decider": "gemini",
                "reason": "LLM classification",
            }

            classifier.classify_and_learn(sample_email)

            # Should have called learn_from_classification
            assert mock_rules.learn_from_classification.called
            call_args = mock_rules.learn_from_classification.call_args
            assert call_args.kwargs["confidence"] == 0.95
            assert "ShopQ-" in call_args.kwargs["category"]

    def test_does_not_learn_from_low_confidence(self, sample_email: ParsedEmail):
        """Test that low-confidence classifications don't trigger learning."""
        classifier = EmailClassifier()
        mock_rules = MagicMock()
        classifier.rules = mock_rules

        # Mock LLM to return low-confidence result
        with patch.object(classifier.llm, "classify") as mock_llm:
            mock_llm.return_value = {
                "type": "receipt",
                "type_conf": 0.5,  # Below LEARNING_MIN_CONFIDENCE
                "attention": "none",
                "attention_conf": 0.5,
                "domains": [],
                "domain_conf": {},
                "importance": "routine",
                "decider": "gemini",
                "reason": "LLM classification",
            }

            classifier.classify_and_learn(sample_email)

            # Should NOT have called learn_from_classification
            assert not mock_rules.learn_from_classification.called

    def test_does_not_learn_from_type_mapper(self, calendar_email: ParsedEmail):
        """Test that TypeMapper classifications don't trigger learning."""
        classifier = EmailClassifier()
        mock_rules = MagicMock()
        classifier.rules = mock_rules

        result = classifier.classify_and_learn(calendar_email)

        # TypeMapper match (calendar domain) - should not learn
        assert result.decider == "type_mapper"
        assert not mock_rules.learn_from_classification.called


class TestLearnFromCorrection:
    """Test EmailClassifier.learn_from_correction() method."""

    def test_learns_from_user_correction(self, sample_email: ParsedEmail):
        """Test that user corrections trigger learning with high confidence."""
        classifier = EmailClassifier()
        mock_rules = MagicMock()
        classifier.rules = mock_rules

        corrected_labels = ["ShopQ-Receipts", "ShopQ-Shopping"]
        classifier.learn_from_correction(sample_email, corrected_labels)

        # Should have called learn_from_classification with user correction confidence
        assert mock_rules.learn_from_classification.called
        call_args = mock_rules.learn_from_classification.call_args
        assert call_args.kwargs["confidence"] == USER_CORRECTION_CONFIDENCE
        assert call_args.kwargs["category"] == "ShopQ-Receipts"  # First label

    def test_skips_empty_corrections(self, sample_email: ParsedEmail):
        """Test that empty corrections are skipped."""
        classifier = EmailClassifier()
        mock_rules = MagicMock()
        classifier.rules = mock_rules

        classifier.learn_from_correction(sample_email, [])

        # Should NOT have called learn_from_classification
        assert not mock_rules.learn_from_classification.called


class TestGetClassifier:
    """Test the get_classifier() singleton function."""

    def test_returns_same_instance(self):
        """Test that get_classifier returns the same instance."""
        # Reset singleton for test
        import shopq.classification.classifier as module

        module._classifier_instance = None

        classifier1 = get_classifier()
        classifier2 = get_classifier()

        assert classifier1 is classifier2

    def test_returns_email_classifier(self):
        """Test that get_classifier returns an EmailClassifier."""
        classifier = get_classifier()
        assert isinstance(classifier, EmailClassifier)


class TestConfidenceThresholds:
    """Test that confidence thresholds are correctly applied."""

    def test_learning_threshold_value(self):
        """Test that LEARNING_MIN_CONFIDENCE is set correctly."""
        assert LEARNING_MIN_CONFIDENCE == 0.70

    def test_user_correction_confidence_value(self):
        """Test that USER_CORRECTION_CONFIDENCE is set correctly."""
        assert USER_CORRECTION_CONFIDENCE == 0.95
