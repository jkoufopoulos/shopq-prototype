from __future__ import annotations

import pytest
from pydantic import ValidationError

from shopq.storage.models import (
    ClassifiedEmail,
    Digest,
    DigestItem,
    ParsedEmail,
    RawEmail,
)


def _raw_email(**overrides) -> RawEmail:
    data = {
        "message_id": "msg-1",
        "thread_id": "thr-1",
        "received_ts": "2025-11-02T12:00:00Z",
        "subject": "Subject",
        "from_address": "sender@example.com",
        "to_address": "user@example.com",
        "body": "Hello",
    }
    data.update(overrides)
    return RawEmail.model_validate(data)


def _parsed_email(**overrides) -> ParsedEmail:
    data = {
        "base": _raw_email(),
        "body_text": "Hello",
        "body_html": "<p>Hello</p>",
    }
    data.update(overrides)
    return ParsedEmail.model_validate(data)


def _classified_email(**overrides) -> ClassifiedEmail:
    data = {
        "parsed": _parsed_email(),
        "category": "notification",
        "attention": "none",
        "domains": ["finance"],
        "confidence": 0.9,
    }
    data.update(overrides)
    return ClassifiedEmail.model_validate(data)


def test_digest_validation_happy_path():
    classified = _classified_email()
    item = DigestItem.model_validate(
        {
            "source": classified,
            "priority": 0.7,
            "title": "Important update",
            "snippet": "Read details",
            "gmail_thread_link": "https://mail.google.com/mail/u/0/?fs=1&view=pt&search=all&th=thr-1",
        }
    )
    digest = Digest.model_validate(
        {
            "items": [item],
            "generated_ts": "2025-11-02T13:00:00Z",
            "idempotency_key": "key",
        }
    )
    assert digest.items[0].priority == 0.7


@pytest.mark.parametrize("missing_field", ["message_id", "thread_id", "received_ts"])
def test_raw_email_missing_required_fields(missing_field):
    data = {
        "message_id": "msg-1",
        "thread_id": "thr-1",
        "received_ts": "2025-11-02T12:00:00Z",
        "from_address": "sender@example.com",
        "to_address": "user@example.com",
        "body": "Hello",
    }
    data.pop(missing_field)
    with pytest.raises(ValidationError):
        RawEmail.model_validate(data)


def test_classified_email_invalid_category():
    with pytest.raises(ValidationError, match="unsupported category"):
        _classified_email(category="unknown")


def test_digest_item_requires_gmail_link():
    classified = _classified_email()
    with pytest.raises(ValidationError, match="must be a Gmail URL"):
        DigestItem.model_validate(
            {
                "source": classified,
                "priority": 0.5,
                "title": "Update",
                "snippet": "snippet",
                "gmail_thread_link": "https://example.com/thread",
            }
        )
