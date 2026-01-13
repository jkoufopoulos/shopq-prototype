from pathlib import Path

from shopq.classification.importance_mapping.guardrails import GuardrailMatcher

FIXTURE_PATH = Path("tests/fixtures/guardrails_test.yaml")


def test_never_surface_overrides_other_guardrails():
    matcher = GuardrailMatcher(FIXTURE_PATH)
    email = {
        "subject": "ShopQ Digest / read receipt",
        "snippet": "Read receipt for ShopQ Digest item.",
        "type": "notification",
        "attention": "none",
    }
    result = matcher.evaluate(email)
    assert result is not None
    assert result.category == "never_surface"


def test_force_critical_overrides_non_critical():
    matcher = GuardrailMatcher(FIXTURE_PATH)
    email = {
        "subject": "Fraud alert: account compromised and autopay triggered",
        "snippet": "Fraud alert triggered for your account, verify immediately.",
        "type": "notification",
        "attention": "action_required",
    }
    result = matcher.evaluate(email)
    assert result is not None
    assert result.category == "force_critical"
    assert result.importance == "critical"


def test_force_non_critical_covers_autopay():
    matcher = GuardrailMatcher(FIXTURE_PATH)
    email = {
        "subject": "AutoPay scheduled for tomorrow",
        "snippet": "Your autopay will run as scheduled; no action needed.",
        "type": "notification",
        "attention": "none",
    }
    result = matcher.evaluate(email)
    assert result is not None
    assert result.category == "force_non_critical"
    assert result.importance == "routine"
