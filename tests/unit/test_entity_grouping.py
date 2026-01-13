from shopq.digest.support import canonical_subject, entity_key, stable_sort_entities


def test_canonical_subject_strips_html_and_punctuation():
    subject = "Meeting: 📅 Tomorrow at 10am!"
    assert canonical_subject(subject) == "meeting tomorrow at 10am"


def test_entity_key_includes_domain_and_type():
    key = entity_key("example.com", "monthly report", "notification")
    assert key == "example.com:monthly report:notification"


def test_stable_sort_preserves_layout():
    entities = [
        {
            "importance": "routine",
            "sender_domain": "example.com",
            "canonical_subject": "alpha",
            "email_type": "notification",
        },
        {
            "importance": "critical",
            "sender_domain": "bank.com",
            "canonical_subject": "beta",
            "email_type": "notification",
        },
        {
            "importance": "time_sensitive",
            "sender_domain": "example.com",
            "canonical_subject": "alpha",
            "email_type": "event",
        },
    ]
    sorted_entities = stable_sort_entities(entities)
    assert sorted_entities[0]["importance"] == "critical"
