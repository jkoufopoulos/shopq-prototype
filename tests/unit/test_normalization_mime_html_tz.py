from shopq.digest.support import normalize_email_payload, normalize_text


def test_normalize_html_and_base64():
    payload = {
        "messageId": "msg-1",
        "threadId": "thread-1",
        "subject": "Security alert",
        "snippet": "PGh0bWw+PHRpdGxlPkhlbGxvPC90aXRsZT4=",
        "body": "<p>Click <a href='https://example.com'>here</a></p>",
        "from": "alerts@bank.com",
        "classification": {
            "type": "notification",
            "attention": "action_required",
            "domains": ["finance"],
            "domain_conf": {"finance": 0.95},
            "relationship": "from_unknown",
            "relationship_conf": 0.6,
            "decider": "gemini",
        },
        "emailTimestamp": "2025-11-08T12:00:00Z",
    }

    normalized = normalize_email_payload(payload)
    assert "Hello" in normalized.normalized_snippet
    assert normalized.sender_etld == "bank.com"
    assert normalized.canonical_subject == "security alert"
    assert normalized.timezone is None or normalized.timezone == ""


def test_normalize_text_strips_html_entities():
    text = "<b>Hello</b> &amp; <i>world</i>"
    normalized = normalize_text(text)
    assert normalized == "Hello & world"
