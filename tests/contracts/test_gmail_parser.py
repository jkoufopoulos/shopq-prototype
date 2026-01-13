from __future__ import annotations

import base64

import pytest

from shopq.gmail.parser import GmailParsingError, parse_message_strict


def _sample_message(body: str = "Hello", mime_type: str = "text/plain"):
    encoded = base64.urlsafe_b64encode(body.encode("utf-8")).decode("utf-8")
    return {
        "id": "17890abc",
        "threadId": "thread-1",
        "internalDate": "1700000000000",
        "payload": {
            "mimeType": mime_type,
            "body": {"data": encoded},
            "headers": [
                {"name": "Subject", "value": "Test"},
                {"name": "From", "value": "sender@example.com"},
                {"name": "To", "value": "user@example.com"},
            ],
        },
    }


def test_parse_message_strict_success_text_plain():
    parsed = parse_message_strict(_sample_message())
    assert parsed.base.message_id == "17890abc"
    assert parsed.body_text == "Hello"
    assert parsed.body_html is None


def test_parse_message_strict_supports_html_body():
    message = _sample_message("<p>Hello</p>", mime_type="text/html")
    parsed = parse_message_strict(message)
    assert parsed.body_text == ""
    assert parsed.body_html == "<p>Hello</p>"


@pytest.mark.parametrize("field", ["id", "threadId", "payload"])
def test_missing_top_level_fields_raise(field):
    message = _sample_message()
    message.pop(field)
    with pytest.raises(GmailParsingError):
        parse_message_strict(message)


def test_missing_required_headers_raise():
    message = _sample_message()
    message["payload"]["headers"] = []
    with pytest.raises(GmailParsingError, match="required address headers missing"):
        parse_message_strict(message)


def test_missing_body_raises():
    message = _sample_message()
    message["payload"]["body"] = {}
    message["payload"].pop("parts", None)
    with pytest.raises(GmailParsingError, match="message body missing"):
        parse_message_strict(message)
