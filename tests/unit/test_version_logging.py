"""
Tests to verify model/prompt version fields are logged in 100% of classifications.

This ensures we have complete auditability for rollbacks and debugging.
"""

from __future__ import annotations

import pytest

from shopq.utils.versioning import MODEL_NAME, MODEL_VERSION, PROMPT_VERSION, get_version_metadata


def test_versioning_constants_exist():
    """Verify versioning constants are defined."""
    assert MODEL_NAME is not None
    assert MODEL_VERSION is not None
    assert PROMPT_VERSION is not None
    assert len(MODEL_NAME) > 0
    assert len(MODEL_VERSION) > 0
    assert len(PROMPT_VERSION) > 0


def test_get_version_metadata_structure():
    """Verify version metadata returns correct structure."""
    metadata = get_version_metadata()

    assert isinstance(metadata, dict)
    assert "model_name" in metadata
    assert "model_version" in metadata
    assert "prompt_version" in metadata

    assert metadata["model_name"] == MODEL_NAME
    assert metadata["model_version"] == MODEL_VERSION
    assert metadata["prompt_version"] == PROMPT_VERSION


@pytest.mark.skipif(True, reason="Requires GOOGLE_API_KEY - integration test, not unit test")
def test_llm_classifier_includes_version_fields():
    """Verify VertexGeminiClassifier.classify() includes version fields."""
    from shopq.classification.vertex_gemini_classifier import VertexGeminiClassifier

    classifier = VertexGeminiClassifier()

    # Classify a simple email
    result = classifier.classify(
        subject="Test email",
        snippet="This is a test",
        from_field="test@example.com",
    )

    # Verify version fields are present
    assert "model_name" in result, "model_name must be in classification result"
    assert "model_version" in result, "model_version must be in classification result"
    assert "prompt_version" in result, "prompt_version must be in classification result"

    # Verify values match constants
    assert result["model_name"] == MODEL_NAME
    assert result["model_version"] == MODEL_VERSION
    assert result["prompt_version"] == PROMPT_VERSION


def test_fallback_result_includes_version_fields():
    """Verify fallback results include version fields."""
    from shopq.classification.vertex_gemini_classifier import (
        MODEL_NAME,
        MODEL_VERSION,
        PROMPT_VERSION,
        VertexGeminiClassifier,
    )

    classifier = VertexGeminiClassifier()

    # Get fallback result (doesn't require API call)
    fallback = classifier._fallback_result("test@example.com")

    # Verify version fields are present
    assert "model_name" in fallback, "Fallback must include model_name"
    assert "model_version" in fallback, "Fallback must include model_version"
    assert "prompt_version" in fallback, "Fallback must include prompt_version"

    # Verify values match constants
    assert fallback["model_name"] == MODEL_NAME
    assert fallback["model_version"] == MODEL_VERSION
    assert fallback["prompt_version"] == PROMPT_VERSION


def test_version_fields_in_classification_contract():
    """Verify ClassificationContract schema includes version fields."""
    from shopq.storage.classification import ClassificationContract

    # Check if version fields are in the model
    schema = ClassificationContract.model_json_schema()
    properties = schema.get("properties", {})

    assert "model_name" in properties, "ClassificationContract must have model_name field"
    assert "model_version" in properties, "ClassificationContract must have model_version field"
    assert "prompt_version" in properties, "ClassificationContract must have prompt_version field"


def test_vertex_classifier_uses_central_versioning():
    """Verify VertexGeminiClassifier imports from central versioning module."""
    # Check that constants are imported from versioning module
    # (not defined locally in vertex_gemini_classifier.py)
    import shopq.classification.vertex_gemini_classifier as classifier_module
    import shopq.utils.versioning as versioning_module

    # If imported correctly, they should be the same object
    assert classifier_module.MODEL_NAME is versioning_module.MODEL_NAME, (
        "VertexGeminiClassifier should import MODEL_NAME from shopq.utils.versioning"
    )
    assert classifier_module.MODEL_VERSION is versioning_module.MODEL_VERSION, (
        "VertexGeminiClassifier should import MODEL_VERSION from shopq.utils.versioning"
    )
    assert classifier_module.PROMPT_VERSION is versioning_module.PROMPT_VERSION, (
        "VertexGeminiClassifier should import PROMPT_VERSION from shopq.utils.versioning"
    )
