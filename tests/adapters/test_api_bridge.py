"""

from __future__ import annotations

Tests for API Bridge Adapter

Validates conversion between API models and domain models.
"""

from datetime import datetime

from mailq.gmail.api_bridge import (
    api_email_to_parsed,
    batch_api_to_parsed,
    batch_classified_to_api_results,
    classified_to_api_result,
)
from mailq.storage.models import ClassifiedEmail, ParsedEmail, RawEmail


class MockEmailInput:
    """Mock API EmailInput for testing"""

    def __init__(self, subject: str, snippet: str, sender: str):
        self.subject = subject
        self.snippet = snippet
        self.sender = sender


def test_api_email_to_parsed_basic():
    """Test converting API email to parsed email"""
    api_email = MockEmailInput(
        subject="Test Email", snippet="This is a test", sender="test@example.com"
    )

    parsed = api_email_to_parsed(api_email, email_id="test-123")

    assert parsed.base.message_id == "test-123"
    assert parsed.base.thread_id == "test-123"  # Same as message_id for API emails
    assert parsed.base.subject == "Test Email"
    assert parsed.base.from_address == "test@example.com"
    assert parsed.base.body == "This is a test"
    assert parsed.body_text == "This is a test"
    assert parsed.body_html is None


def test_api_email_to_parsed_generates_id():
    """Test that email_id is generated if not provided"""
    api_email = MockEmailInput(subject="Test", snippet="Content", sender="sender@test.com")

    parsed = api_email_to_parsed(api_email)

    # Should generate deterministic ID
    assert parsed.base.message_id is not None
    assert len(parsed.base.message_id) == 16  # SHA256 first 16 chars

    # Same input should produce same ID
    parsed2 = api_email_to_parsed(api_email)
    assert parsed.base.message_id == parsed2.base.message_id


def test_classified_to_api_result_receipt():
    """Test converting classified receipt to API result"""
    # Create mock classified email with decider and reason (as EmailClassifier would)
    base = RawEmail(
        message_id="msg-1",
        thread_id="thread-1",
        received_ts=datetime.now().isoformat(),
        subject="Your order has shipped",
        from_address="amazon@amazon.com",
        to_address="user@test.com",
        body="Order #123 shipped",
    )
    parsed = ParsedEmail(base=base, body_text=base.body, body_html=None)
    classified = ClassifiedEmail(
        parsed=parsed,
        category="receipt",
        attention="none",
        confidence=0.95,
        decider="gemini",  # From EmailClassifier cascade
        reason="LLM classification",  # Explanation of classification source
    )

    result = classified_to_api_result(classified)

    assert result["id"] == "msg-1"
    assert result["from"] == "amazon@amazon.com"
    assert result["type"] == "receipt"
    assert result["type_conf"] == 0.95
    assert result["attention"] == "none"
    # New 4-label system: receipts get MailQ-Receipts (no domain labels)
    assert result["labels"] == ["MailQ-Receipts"]
    assert result["decider"] == "gemini"  # Now uses actual decider from cascade
    assert result["reason"] == "LLM classification"


def test_classified_to_api_result_action_required():
    """Test message type maps to MailQ-Messages (attention ignored for labels)"""
    base = RawEmail(
        message_id="msg-2",
        thread_id="thread-2",
        received_ts=datetime.now().isoformat(),
        subject="Action required",
        from_address="urgent@test.com",
        to_address="user@test.com",
        body="Please respond",
    )
    parsed = ParsedEmail(base=base, body_text=base.body, body_html=None)
    classified = ClassifiedEmail(
        parsed=parsed,
        category="message",
        attention="action_required",
        confidence=0.88,
        decider="type_mapper",
        reason="TypeMapper: action_required_pattern",
    )

    result = classified_to_api_result(classified)

    # New 4-label system: messages get MailQ-Messages (attention_required doesn't add separate label)
    # client_label is based on type + importance, not attention
    assert result["labels"] == ["MailQ-Messages"]
    assert result["attention"] == "action_required"


def test_classified_to_api_result_notification_maps_to_everything_else():
    """Test notifications map to MailQ-Everything-Else"""
    base = RawEmail(
        message_id="msg-3",
        thread_id="thread-3",
        received_ts=datetime.now().isoformat(),
        subject="Your package arrived",
        from_address="notify@ups.com",
        to_address="user@test.com",
        body="Package delivered",
    )
    parsed = ParsedEmail(base=base, body_text=base.body, body_html=None)
    classified = ClassifiedEmail(
        parsed=parsed,
        category="notification",
        attention="none",
        confidence=0.92,
        decider="fallback",
        reason="Keyword-based fallback",
    )

    result = classified_to_api_result(classified)

    # New 4-label system: notifications → everything-else (no domain labels)
    assert result["labels"] == ["MailQ-Everything-Else"]
    assert result["type"] == "notification"


def test_batch_api_to_parsed():
    """Test batch conversion of API emails"""
    api_emails = [
        MockEmailInput("Email 1", "Content 1", "sender1@test.com"),
        MockEmailInput("Email 2", "Content 2", "sender2@test.com"),
        MockEmailInput("Email 3", "Content 3", "sender3@test.com"),
    ]

    parsed_emails = batch_api_to_parsed(api_emails)

    assert len(parsed_emails) == 3
    assert all(isinstance(p, ParsedEmail) for p in parsed_emails)
    assert parsed_emails[0].base.subject == "Email 1"
    assert parsed_emails[1].base.subject == "Email 2"
    assert parsed_emails[2].base.subject == "Email 3"

    # Check IDs are sequential
    assert parsed_emails[0].base.message_id == "api-email-0000"
    assert parsed_emails[1].base.message_id == "api-email-0001"
    assert parsed_emails[2].base.message_id == "api-email-0002"


def test_batch_classified_to_api_results():
    """Test batch conversion of classified emails"""
    # Create mock classified emails with decider/reason (as EmailClassifier would)
    classified_emails = []
    for i in range(3):
        base = RawEmail(
            message_id=f"msg-{i}",
            thread_id=f"thread-{i}",
            received_ts=datetime.now().isoformat(),
            subject=f"Email {i}",
            from_address=f"sender{i}@test.com",
            to_address="user@test.com",
            body=f"Content {i}",
        )
        parsed = ParsedEmail(base=base, body_text=base.body, body_html=None)
        classified = ClassifiedEmail(
            parsed=parsed,
            category="notification",
            attention="none",
            confidence=0.9,
            decider="gemini",
            reason="LLM classification",
        )
        classified_emails.append(classified)

    results = batch_classified_to_api_results(classified_emails)

    assert len(results) == 3
    assert all(isinstance(r, dict) for r in results)
    assert results[0]["from"] == "sender0@test.com"
    assert results[1]["from"] == "sender1@test.com"
    assert results[2]["from"] == "sender2@test.com"
    # Now uses actual decider from EmailClassifier cascade
    assert all(r["decider"] == "gemini" for r in results)


def test_api_bridge_round_trip():
    """Test full round-trip: API → Domain → API"""
    # Start with API email
    api_email = MockEmailInput(
        subject="Your receipt from Starbucks",
        snippet="Thank you for your purchase of $5.75",
        sender="receipts@starbucks.com",
    )

    # Convert to domain
    parsed = api_email_to_parsed(api_email, email_id="test-receipt")

    # Simulate classification (would normally go through EmailClassifier cascade)
    classified = ClassifiedEmail(
        parsed=parsed,
        category="receipt",
        attention="none",
        confidence=0.98,
        decider="type_mapper",
        reason="TypeMapper: starbucks.com",
    )

    # Convert back to API result
    result = classified_to_api_result(classified)

    # Verify round-trip maintains data
    assert result["from"] == api_email.sender
    assert result["type"] == "receipt"
    assert result["type_conf"] == 0.98
    # New 4-label system: receipts → MailQ-Receipts only (no domain labels)
    assert result["labels"] == ["MailQ-Receipts"]
    assert result["decider"] == "type_mapper"
