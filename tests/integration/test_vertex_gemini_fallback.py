"""
Test that VertexGeminiClassifier fallback result matches ClassificationContract schema

This ensures that when LLM classification fails, the fallback result still
passes schema validation.
"""

import pytest

try:
    from shopq.classification.vertex_gemini_classifier import VertexGeminiClassifier
    from shopq.storage.classification import ClassificationContract, get_valid_email_types
except ImportError:
    pytest.skip("ShopQ modules not available", allow_module_level=True)


def test_fallback_result_matches_schema():
    """
    Test that _fallback_result() returns a dict that passes ClassificationContract validation.

    This is critical because fallback is used when:
    - LLM returns invalid JSON
    - LLM returns JSON missing required fields
    - Circuit breaker trips after repeated failures
    """
    classifier = VertexGeminiClassifier()

    # Get fallback result
    fallback = classifier._fallback_result(from_field="test@example.com")

    # Add message_id (normally set by caller)
    fallback["message_id"] = "test_message_123"

    # Validate against schema (this will raise ValidationError if invalid)
    contract = ClassificationContract.model_validate(fallback)

    # Verify all required fields are present
    assert contract.message_id == "test_message_123"
    assert contract.type == "uncategorized"  # Safe fallback type
    assert contract.importance == "routine"
    assert contract.confidence == 0.3
    assert contract.type_conf == 0.5
    assert contract.attention == "none"
    assert contract.relationship == "from_unknown"
    assert contract.decider == "gemini_fallback"
    assert "failed" in contract.reason.lower()

    print("\n✅ Fallback result passes schema validation")
    print(f"   importance: {contract.importance}")
    print(f"   type: {contract.type}")
    print(f"   confidence: {contract.confidence}")
    print(f"   decider: {contract.decider}")


def test_fallback_result_has_all_required_fields():
    """
    Verify fallback result has all fields required by ClassificationContract.

    This is a whitebox test that ensures we don't miss any required fields.
    """
    classifier = VertexGeminiClassifier()
    fallback = classifier._fallback_result(from_field="test@example.com")

    # Add message_id (normally set by caller)
    fallback["message_id"] = "test_msg"

    # Check all required fields from ClassificationContract
    # Note: domains/domain_conf removed from 4-label system
    required_fields = {
        "message_id": str,
        "type": str,
        "importance": str,
        "confidence": float,
        "type_conf": float,
        "attention": str,
        "attention_conf": float,
        "relationship": str,
        "relationship_conf": float,
        "decider": str,
        "reason": str,
        "model_name": str,
        "model_version": str,
        "prompt_version": str,
    }

    for field, expected_type in required_fields.items():
        assert field in fallback, f"Missing required field: {field}"
        assert isinstance(fallback[field], expected_type), (
            f"Field {field} has wrong type: {type(fallback[field])}, expected {expected_type}"
        )

    print(f"\n✅ All {len(required_fields)} required fields present and correct types")


def test_fallback_importance_is_routine():
    """
    Verify that fallback always uses 'routine' importance (safest default).

    When classification fails, we default to routine (lowest priority) to avoid
    false escalation to critical.
    """
    classifier = VertexGeminiClassifier()
    fallback = classifier._fallback_result(from_field="urgent@example.com")

    assert fallback["importance"] == "routine", "Fallback should always use 'routine' importance"
    assert fallback["confidence"] < 0.5, "Fallback should have low confidence"

    print("\n✅ Fallback correctly defaults to routine importance")


def test_fallback_type_is_valid():
    """
    Verify that fallback type is valid according to ClassificationContract schema.

    Uses get_valid_email_types() to get the current valid types dynamically.
    """
    classifier = VertexGeminiClassifier()
    fallback = classifier._fallback_result(from_field="test@example.com")

    # Get valid types from the source of truth
    valid_types = set(get_valid_email_types())
    assert fallback["type"] in valid_types, (
        f"Fallback type '{fallback['type']}' not in valid types: {valid_types}"
    )

    print(f"\n✅ Fallback type '{fallback['type']}' is valid")


def test_fallback_decider_indicates_failure():
    """
    Verify that fallback decider clearly indicates this is a fallback result.

    This helps with debugging and telemetry.
    """
    classifier = VertexGeminiClassifier()
    fallback = classifier._fallback_result(from_field="test@example.com")

    assert "fallback" in fallback["decider"].lower(), "Decider should indicate fallback"
    assert "fail" in fallback["reason"].lower(), "Reason should indicate failure"

    print("\n✅ Fallback clearly indicates failure:")
    print(f"   decider: {fallback['decider']}")
    print(f"   reason: {fallback['reason']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
