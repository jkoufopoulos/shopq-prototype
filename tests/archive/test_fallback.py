"""

from __future__ import annotations

Tests for LLM safety: schema validation, caching, and rules-only fallback.

These tests verify that digest correctness NEVER depends on LLM:
1. Invalid LLM output → fallback to rules
2. LLM API failure → fallback to rules
3. LLM disabled → use rules only
4. Schema mismatch → increment counter, fallback to rules
5. Cache hits → avoid redundant LLM calls
"""

import os

import pytest

# Enable LLM for tests
os.environ["MAILQ_USE_LLM"] = "true"

from mailq.llm.client import (
    LLMSchemaError,
    classify_email_llm,
    clear_llm_cache,
)
from mailq.observability.telemetry import _COUNTERS, counter
from mailq.storage.classify import LLMClassification, batch_classify_emails, classify_email
from mailq.storage.models import ParsedEmail, RawEmail


@pytest.fixture(autouse=True)
def reset_state():
    """Reset counters and cache before each test."""
    _COUNTERS.clear()
    clear_llm_cache()
    yield
    _COUNTERS.clear()
    clear_llm_cache()


def _make_test_email(subject: str = "Test Email", body: str = "Test body") -> ParsedEmail:
    """Helper to create test email."""
    return ParsedEmail(
        base=RawEmail(
            message_id="test-msg-001",
            thread_id="test-thread-001",
            received_ts="1699000000000",
            subject=subject,
            from_address="sender@example.com",
            to_address="user@example.com",
            body=body,
        ),
        body_text=body,
    )


def test_llm_disabled_uses_rules_fallback():
    """
    Test: When LLM is disabled, classification falls back to rules.

    Acceptance: Digest remains correct without LLM.
    """
    email = _make_test_email(subject="Order Receipt #12345", body="Your order total: $50")

    # Classify with LLM disabled (no llm_call_fn provided)
    classified = classify_email(email, use_llm=False)

    # Should succeed with rules-based classification
    assert classified.category == "receipt"  # Rules detect "receipt" in subject
    assert classified.confidence > 0.0
    assert counter("classification.rules_fallback", 0) >= 1
    print(f"✅ Rules fallback: category={classified.category}, confidence={classified.confidence}")


def test_invalid_llm_json_triggers_fallback():
    """
    Test: Invalid JSON from LLM → fallback to rules.

    Acceptance: schema_validation_failures counter increments.
    """
    email = _make_test_email()

    def invalid_json_llm(_prompt: str) -> str:
        """Mock LLM that returns invalid JSON."""
        return "This is not JSON at all!"

    # Classify with invalid JSON LLM
    classified = classify_email(email, use_llm=True, llm_call_fn=invalid_json_llm)

    # Should fallback to rules
    assert classified.category in ["notification", "receipt", "event", "promotion", "message"]
    assert counter("llm.schema_validation_failures", 0) >= 1
    assert counter("classification.llm_schema_error", 0) >= 1
    assert counter("classification.rules_fallback", 0) >= 1
    print(f"✅ Invalid JSON handled: fell back to category={classified.category}")


def test_schema_mismatch_llm_triggers_fallback():
    """
    Test: LLM returns JSON but schema doesn't match → fallback to rules.

    Acceptance: schema_validation_failures counter increments.
    """
    email = _make_test_email()

    def schema_mismatch_llm(_prompt: str) -> dict:
        """Mock LLM that returns wrong schema."""
        return {
            "category": "invalid_category",  # Not in allowed set
            "attention": "none",
            "confidence": 0.95,
        }

    classified = classify_email(email, use_llm=True, llm_call_fn=schema_mismatch_llm)

    # Should fallback to rules
    assert classified.category in ["notification", "receipt", "event", "promotion", "message"]
    assert counter("llm.schema_validation_failures", 0) >= 1
    assert counter("classification.llm_schema_error", 0) >= 1
    assert counter("classification.rules_fallback", 0) >= 1
    print(f"✅ Schema mismatch handled: fell back to category={classified.category}")


def test_llm_api_error_triggers_fallback():
    """
    Test: LLM API call fails → fallback to rules.

    Acceptance: Digest remains correct despite LLM failure.
    """
    email = _make_test_email()

    def failing_llm(_prompt: str):
        """Mock LLM that raises an error."""
        raise RuntimeError("LLM API is down!")

    classified = classify_email(email, use_llm=True, llm_call_fn=failing_llm)

    # Should fallback to rules
    assert classified.category in ["notification", "receipt", "event", "promotion", "message"]
    assert counter("llm.call_error", 0) >= 1
    assert counter("classification.llm_error", 0) >= 1
    assert counter("classification.rules_fallback", 0) >= 1
    print(f"✅ LLM error handled: fell back to category={classified.category}")


def test_valid_llm_output_cached():
    """
    Test: Valid LLM output is cached and reused.

    Acceptance: Second call hits cache, no redundant LLM calls.
    """
    email = _make_test_email()

    call_count = {"count": 0}

    def valid_llm(_prompt: str) -> dict:
        """Mock LLM that returns valid classification."""
        call_count["count"] += 1
        return {
            "category": "receipt",
            "attention": "none",
            "domains": ["finance"],
            "confidence": 0.95,
        }

    # First call: should hit LLM
    classified1 = classify_email(email, use_llm=True, llm_call_fn=valid_llm)
    assert classified1.category == "receipt"
    assert call_count["count"] == 1
    assert counter("llm.cache_miss", 0) >= 1

    # Second call: should hit cache
    classified2 = classify_email(email, use_llm=True, llm_call_fn=valid_llm)
    assert classified2.category == "receipt"
    assert call_count["count"] == 1  # LLM not called again
    assert counter("llm.cache_hit", 0) >= 1

    print(
        f"✅ Caching works: LLM called {call_count['count']} time(s), cache hits={counter('llm.cache_hit', 0)}"
    )


def test_rules_classify_receipts():
    """Test: Rules correctly classify receipt emails."""
    email = _make_test_email(
        subject="Payment Receipt - Order #12345",
        body="Thank you for your payment of $99.99",
    )

    classified = classify_email(email, use_llm=False)

    assert classified.category == "receipt"
    assert "finance" in classified.domains
    assert classified.confidence > 0.7
    print(f"✅ Rules detect receipt: category={classified.category}, domains={classified.domains}")


def test_rules_classify_events():
    """Test: Rules correctly classify event emails."""
    email = _make_test_email(
        subject="Meeting Invitation: Q4 Planning", body="You're invited to attend..."
    )

    classified = classify_email(email, use_llm=False)

    assert classified.category == "event"
    assert classified.confidence > 0.7
    print(f"✅ Rules detect event: category={classified.category}")


def test_rules_classify_promotions():
    """Test: Rules correctly classify promotional emails."""
    email = _make_test_email(subject="50% OFF Sale This Weekend!", body="Get 50% off all items...")

    classified = classify_email(email, use_llm=False)

    assert classified.category == "promotion"
    assert "shopping" in classified.domains
    assert classified.confidence > 0.7
    print(
        f"✅ Rules detect promotion: category={classified.category}, domains={classified.domains}"
    )


def test_rules_detect_action_required():
    """Test: Rules detect action_required attention level."""
    email = _make_test_email(
        subject="ACTION REQUIRED: Verify Your Account", body="Please verify immediately..."
    )

    classified = classify_email(email, use_llm=False)

    assert classified.attention == "action_required"
    print(f"✅ Rules detect action required: attention={classified.attention}")


def test_batch_classification_never_fails():
    """
    Test: Batch classification always succeeds even with mixed LLM failures.

    Acceptance: Returns same number of results as inputs, all valid.
    """
    emails = [_make_test_email(subject=f"Test Email #{i}", body=f"Body {i}") for i in range(10)]

    failure_count = {"count": 0}

    def flaky_llm(_prompt: str):
        """Mock LLM that fails randomly."""
        failure_count["count"] += 1
        if failure_count["count"] % 3 == 0:
            raise RuntimeError("LLM API timeout!")
        if failure_count["count"] % 5 == 0:
            return "invalid JSON"
        return {
            "category": "notification",
            "attention": "none",
            "domains": [],
            "confidence": 0.9,
        }

    # Classify batch with flaky LLM
    classified = batch_classify_emails(emails, use_llm=True, llm_call_fn=flaky_llm)

    # All emails should be classified (no exceptions)
    assert len(classified) == 10
    for result in classified:
        assert result.category in ["notification", "receipt", "event", "promotion", "message"]
        assert result.attention in ["action_required", "none"]

    print(
        f"✅ Batch classification: 10/10 succeeded despite {failure_count['count']} LLM calls with failures"
    )


def test_llm_cache_key_deterministic():
    """Test: Same email + prompt always produces same cache key."""
    email = _make_test_email()

    call_count = {"count": 0}

    def counting_llm(_prompt: str) -> dict:
        call_count["count"] += 1
        return {
            "category": "notification",
            "attention": "none",
            "domains": [],
            "confidence": 0.85,
        }

    # Call 5 times with same email
    for _ in range(5):
        classify_email(email, use_llm=True, llm_call_fn=counting_llm)

    # LLM should only be called once (rest hit cache)
    assert call_count["count"] == 1
    assert counter("llm.cache_hit", 0) >= 4

    print(f"✅ Cache determinism: LLM called 1 time, cache hits={counter('llm.cache_hit', 0)}")


def test_schema_validation_in_llm_adapter():
    """Test: LLM adapter validates schema before returning."""
    from mailq.llm.client import _compute_cache_key

    email_key = "test-email-key-001"
    prompt = "Test prompt"
    _compute_cache_key(prompt, email_key)

    # Test with valid schema
    def valid_llm(_p):
        return {"category": "receipt", "attention": "none", "confidence": 0.9, "domains": []}

    result = classify_email_llm(
        prompt=prompt,
        email_key=email_key,
        expected_schema=LLMClassification,
        llm_call_fn=valid_llm,
    )

    assert result is not None
    assert result["category"] == "receipt"
    assert counter("llm.schema_validation_success", 0) >= 1

    # Test with invalid schema
    clear_llm_cache()  # Clear to avoid cache hit

    def invalid_llm(_p):
        return {"wrong_field": "value"}

    with pytest.raises(LLMSchemaError):
        classify_email_llm(
            prompt="different prompt",  # Different to avoid cache
            email_key=email_key,
            expected_schema=LLMClassification,
            llm_call_fn=invalid_llm,
        )

    assert counter("llm.schema_validation_failures", 0) >= 1
    print(
        f"✅ Schema validation: success={counter('llm.schema_validation_success', 0)}, failures={counter('llm.schema_validation_failures', 0)}"
    )
