"""

from __future__ import annotations

Regression tests for API bridge idempotency stability.
"""

from shopq.gmail.api_bridge import api_email_to_parsed
from shopq.infrastructure.idempotency import email_key


class _MockEmail:
    def __init__(self, subject: str, snippet: str, sender: str):
        self.subject = subject
        self.snippet = snippet
        self.sender = sender


def test_api_bridge_produces_stable_idempotency_key():
    email = _MockEmail(
        subject="Quarterly results available",
        snippet="Hi team, the Q3 numbers are attached.",
        sender="finance@example.com",
    )

    parsed_first = api_email_to_parsed(email)
    parsed_second = api_email_to_parsed(email)

    assert parsed_first.base.message_id == parsed_second.base.message_id
    assert parsed_first.base.received_ts == parsed_second.base.received_ts

    key_first = email_key(
        parsed_first.base.message_id,
        parsed_first.base.received_ts,
        parsed_first.base.body,
    )
    key_second = email_key(
        parsed_second.base.message_id,
        parsed_second.base.received_ts,
        parsed_second.base.body,
    )

    assert key_first == key_second


def test_api_bridge_idempotency_changes_when_email_changes():
    original = _MockEmail(
        subject="Security alert",
        snippet="Unusual sign-in detected.",
        sender="security@example.com",
    )
    updated = _MockEmail(
        subject="Security alert",
        snippet="Unusual sign-in detected from new device.",
        sender="security@example.com",
    )

    parsed_original = api_email_to_parsed(original)
    parsed_updated = api_email_to_parsed(updated)

    key_original = email_key(
        parsed_original.base.message_id,
        parsed_original.base.received_ts,
        parsed_original.base.body,
    )
    key_updated = email_key(
        parsed_updated.base.message_id,
        parsed_updated.base.received_ts,
        parsed_updated.base.body,
    )

    assert key_original != key_updated
