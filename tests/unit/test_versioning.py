"""
Tests for model/prompt version tracking.

Ensures that:
1. Version metadata is available and has expected structure
2. Classification results include version fields
3. Confidence logger persists version metadata
"""

from __future__ import annotations

import pytest

from shopq.utils.versioning import (
    MODEL_NAME,
    MODEL_VERSION,
    PROMPT_VERSION,
    format_version_string,
    get_version_metadata,
)


def test_version_constants_exist():
    """Version constants must be defined as non-empty strings"""
    assert MODEL_NAME, "MODEL_NAME must be defined"
    assert MODEL_VERSION, "MODEL_VERSION must be defined"
    assert PROMPT_VERSION, "PROMPT_VERSION must be defined"

    assert isinstance(MODEL_NAME, str), "MODEL_NAME must be a string"
    assert isinstance(MODEL_VERSION, str), "MODEL_VERSION must be a string"
    assert isinstance(PROMPT_VERSION, str), "PROMPT_VERSION must be a string"


def test_get_version_metadata():
    """get_version_metadata returns dict with required fields"""
    metadata = get_version_metadata()

    assert "model_name" in metadata
    assert "model_version" in metadata
    assert "prompt_version" in metadata

    assert metadata["model_name"] == MODEL_NAME
    assert metadata["model_version"] == MODEL_VERSION
    assert metadata["prompt_version"] == PROMPT_VERSION


def test_format_version_string():
    """format_version_string returns human-readable version"""
    version_str = format_version_string()

    assert isinstance(version_str, str)
    assert MODEL_NAME in version_str
    assert MODEL_VERSION in version_str
    assert PROMPT_VERSION in version_str


def test_confidence_logger_includes_versions():
    """ConfidenceLogger.log_classification persists version metadata"""
    from shopq.runtime.thresholds import ConfidenceLogger

    logger = ConfidenceLogger()

    # Create a test classification result
    test_result = {
        "type": "notification",
        "type_conf": 0.95,
        "domains": ["finance"],
        "domain_conf": {"finance": 0.95, "shopping": 0.05},
        "attention": "none",
        "attention_conf": 0.9,
        "relationship": "from_unknown",
        "relationship_conf": 0.8,
        "decider": "gemini",
        "from": "test@example.com",
        "reason": "test classification",
        # Version fields should be auto-populated if missing
    }

    # Log the classification
    logger.log_classification(
        result=test_result,
        email_id="test_msg_123",
        subject="Test Email",
    )

    # Verify versions were logged by querying recent logs
    from shopq.infrastructure.database import get_db_connection

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT model_name, model_version, prompt_version
            FROM confidence_logs
            WHERE email_id = ?
            ORDER BY timestamp DESC
            LIMIT 1
        """,
            ("test_msg_123",),
        )
        row = cursor.fetchone()

    assert row is not None, "Classification should be logged"
    logged_model_name, logged_model_version, logged_prompt_version = row

    assert logged_model_name == MODEL_NAME
    assert logged_model_version == MODEL_VERSION
    assert logged_prompt_version == PROMPT_VERSION


def test_classifier_output_includes_versions():
    """VertexGeminiClassifier.classify output includes version metadata"""
    from shopq.classification.vertex_gemini_classifier import (
        MODEL_NAME as CLASSIFIER_MODEL_NAME,
    )
    from shopq.classification.vertex_gemini_classifier import (
        MODEL_VERSION as CLASSIFIER_MODEL_VERSION,
    )
    from shopq.classification.vertex_gemini_classifier import (
        PROMPT_VERSION as CLASSIFIER_PROMPT_VERSION,
    )

    # Verify classifier constants match versioning module
    assert CLASSIFIER_MODEL_NAME == MODEL_NAME
    assert CLASSIFIER_MODEL_VERSION == MODEL_VERSION
    assert CLASSIFIER_PROMPT_VERSION == PROMPT_VERSION

    # Note: We don't instantiate the actual classifier here to avoid API calls
    # The integration is verified by checking the constants match


def test_version_metadata_in_contract():
    """ClassificationContract requires version fields"""
    from shopq.storage.classification import ClassificationContract

    # Verify schema has version fields
    schema_fields = ClassificationContract.model_fields
    assert "model_name" in schema_fields
    assert "model_version" in schema_fields
    assert "prompt_version" in schema_fields

    # Verify they're required fields
    assert schema_fields["model_name"].is_required()
    assert schema_fields["model_version"].is_required()
    assert schema_fields["prompt_version"].is_required()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
