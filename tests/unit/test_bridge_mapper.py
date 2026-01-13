"""Tests for BridgeImportanceMapper (guardrails-only version).

The BridgeImportanceMapper now only applies guardrail overrides on top of
Gemini's importance output. Mapper rules have been deprecated.
"""

from mailq.classification.importance_mapping import BridgeImportanceMapper


def make_mapper():
    return BridgeImportanceMapper()


def test_guardrail_force_critical():
    """Security alerts should be force_critical via guardrails."""
    mapper = make_mapper()
    email = {
        "subject": "Security alert: data breach detected",
        "snippet": "We detected a data breach affecting your account.",
        "importance": "routine",  # Gemini might say routine, but guardrail overrides
        "type": "notification",
        "domains": ["finance"],
        "attention": "action_required",
    }
    decision = mapper.map_email(email)
    assert decision.importance == "critical"
    assert decision.guardrail == "force_critical"
    assert decision.source == "guardrail"


def test_mapper_rule_critical_otp():
    """OTPs should be force_critical per guardrails.yaml.

    OTPs have T0 importance=critical (they ARE urgent in the moment).
    The digest layer (T1) filters them out since they're too ephemeral
    for daily digests. See docs/features/T0_T1_IMPORTANCE_CLASSIFICATION.md
    """
    mapper = make_mapper()
    email = {
        "subject": "Your verification code is 123456",
        "snippet": "Use this OTP within 5 minutes.",
        "importance": "routine",  # Gemini might say routine, but guardrail overrides
        "type": "notification",
        "domains": ["professional"],
        "attention": "action_required",
    }
    decision = mapper.map_email(email)
    assert decision.importance == "critical"
    assert decision.guardrail == "force_critical"
    assert decision.source == "guardrail"


def test_no_guardrail_uses_gemini_importance():
    """When no guardrail matches, use Gemini's importance directly."""
    mapper = make_mapper()
    email = {
        "subject": "Weekly newsletter from Tech Blog",
        "snippet": "This week's updates...",
        "importance": "routine",  # Gemini importance
        "type": "newsletter",
        "domains": ["professional"],
        "attention": "none",
    }
    decision = mapper.map_email(email)
    assert decision.importance == "routine"
    assert decision.guardrail is None
    assert decision.source == "gemini"


def test_time_sensitive_from_gemini():
    """Gemini's time_sensitive importance should pass through."""
    mapper = make_mapper()
    email = {
        "subject": "Your package will arrive tomorrow",
        "snippet": "Delivery scheduled for Dec 1",
        "importance": "time_sensitive",  # Gemini importance
        "type": "notification",
        "domains": ["shopping"],
        "attention": "none",
    }
    decision = mapper.map_email(email)
    assert decision.importance == "time_sensitive"
    assert decision.guardrail is None
    assert decision.source == "gemini"


def test_critical_from_gemini():
    """Gemini's critical importance should pass through if no guardrail."""
    mapper = make_mapper()
    email = {
        "subject": "Urgent project deadline tomorrow",
        "snippet": "Please submit your work by 5pm.",
        "importance": "critical",  # Gemini importance
        "type": "event",
        "domains": ["professional"],
        "attention": "action_required",
    }
    decision = mapper.map_email(email)
    assert decision.importance == "critical"
    assert decision.guardrail is None
    assert decision.source == "gemini"


def test_missing_importance_defaults_to_routine():
    """If email has no importance field, default to routine."""
    mapper = make_mapper()
    email = {
        "subject": "Generic update",
        "snippet": "Nothing important here.",
        # No 'importance' field
        "type": "notification",
    }
    decision = mapper.map_email(email)
    assert decision.importance == "routine"
    assert decision.source == "gemini"


def test_force_non_critical_overrides_gemini():
    """Guardrail force_non_critical should override even critical Gemini importance."""
    mapper = make_mapper()
    email = {
        "subject": "Autopay scheduled for your bill",
        "snippet": "Your automatic payment is scheduled.",
        "importance": "critical",  # Gemini might say critical
        "type": "notification",
        "domains": ["finance"],
        "attention": "action_required",
    }
    decision = mapper.map_email(email)
    assert decision.importance == "routine"
    assert decision.guardrail == "force_non_critical"
    assert decision.source == "guardrail"
