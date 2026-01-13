"""Unit tests for JSON extraction and repair logic in VertexGeminiClassifier.

Tests the _extract_json method which handles malformed LLM JSON responses.
"""

import json

import pytest


class TestExtractJSON:
    """Tests for VertexGeminiClassifier._extract_json method."""

    @pytest.fixture
    def classifier(self):
        """Create classifier instance for testing _extract_json."""
        # Import here to avoid module-level import issues
        from shopq.classification.vertex_gemini_classifier import VertexGeminiClassifier

        return VertexGeminiClassifier(None)

    def test_extract_json_valid(self, classifier):
        """Should parse valid JSON without repair."""
        text = '{"type": "receipt", "type_conf": 0.95}'
        result = classifier._extract_json(text)
        assert result["type"] == "receipt"
        assert result["type_conf"] == 0.95

    def test_extract_json_markdown_code_block(self, classifier):
        """Should strip markdown code blocks."""
        text = '```json\n{"type": "receipt"}\n```'
        result = classifier._extract_json(text)
        assert result["type"] == "receipt"

    def test_extract_json_markdown_without_json_tag(self, classifier):
        """Should strip markdown code blocks without json tag."""
        text = '```\n{"type": "newsletter"}\n```'
        result = classifier._extract_json(text)
        assert result["type"] == "newsletter"

    def test_extract_json_with_surrounding_text(self, classifier):
        """Should extract JSON from text with surrounding garbage."""
        text = 'Here is the result: {"type": "receipt"} and some more text'
        result = classifier._extract_json(text)
        assert result["type"] == "receipt"

    def test_extract_json_missing_commas_between_strings(self, classifier):
        """Should repair missing commas between string fields."""
        text = """{
            "type": "receipt"
            "decider": "gemini"
        }"""
        result = classifier._extract_json(text)
        assert result["type"] == "receipt"
        assert result["decider"] == "gemini"

    def test_extract_json_missing_comma_after_number(self, classifier):
        """Should repair missing comma after number."""
        text = """{
            "type_conf": 0.95
            "type": "receipt"
        }"""
        result = classifier._extract_json(text)
        assert result["type"] == "receipt"
        assert result["type_conf"] == 0.95

    def test_extract_json_missing_comma_after_boolean(self, classifier):
        """Should repair missing comma after boolean."""
        text = """{
            "should_propose": true
            "type": "receipt"
        }"""
        result = classifier._extract_json(text)
        assert result["type"] == "receipt"
        assert result["should_propose"] is True

    def test_extract_json_trailing_comma_object(self, classifier):
        """Should remove trailing commas before }."""
        text = '{"type": "receipt", "type_conf": 0.95,}'
        result = classifier._extract_json(text)
        assert result["type"] == "receipt"
        assert result["type_conf"] == 0.95

    def test_extract_json_trailing_comma_array(self, classifier):
        """Should remove trailing commas before ]."""
        text = '{"domains": ["finance", "shopping",]}'
        result = classifier._extract_json(text)
        assert result["domains"] == ["finance", "shopping"]

    def test_extract_json_nested_objects(self, classifier):
        """Should handle nested JSON objects."""
        text = """{
            "type": "receipt",
            "domain_conf": {
                "finance": 0.95,
                "shopping": 0.05
            }
        }"""
        result = classifier._extract_json(text)
        assert result["type"] == "receipt"
        assert result["domain_conf"]["finance"] == 0.95
        assert result["domain_conf"]["shopping"] == 0.05

    def test_extract_json_nested_objects_missing_commas(self, classifier):
        """Should repair missing commas in nested objects."""
        text = """{
            "domain_conf": {
                "finance": 0.95
                "shopping": 0.05
            }
            "type": "receipt"
        }"""
        result = classifier._extract_json(text)
        assert result["domain_conf"]["finance"] == 0.95
        assert result["type"] == "receipt"

    def test_extract_json_repair_failure_raises(self, classifier):
        """Should raise JSONDecodeError if all repairs fail."""
        text = '{"type": invalid_value}'
        with pytest.raises(json.JSONDecodeError):
            classifier._extract_json(text)

    def test_extract_json_empty_text_raises(self, classifier):
        """Should raise JSONDecodeError for empty text."""
        with pytest.raises(json.JSONDecodeError):
            classifier._extract_json("")

    def test_extract_json_no_json_raises(self, classifier):
        """Should raise JSONDecodeError when no JSON object found."""
        text = "This is just plain text without any JSON"
        with pytest.raises(json.JSONDecodeError):
            classifier._extract_json(text)

    def test_extract_json_complex_classifier_response(self, classifier):
        """Should parse a realistic classifier response."""
        text = """```json
{
    "type": "receipt",
    "type_conf": 0.95,
    "domains": ["shopping"],
    "domain_conf": {
        "finance": 0.1,
        "professional": 0.0,
        "personal": 0.0,
        "shopping": 0.9,
        "unknown": 0.0
    },
    "attention": "none",
    "attention_conf": 0.8,
    "relationship": "from_business",
    "relationship_conf": 0.9,
    "decider": "gemini",
    "reason": "Order confirmation from Amazon",
    "propose_rule": {
        "should_propose": false,
        "pattern": "amazon.com",
        "kind": "domain",
        "support_count": 0
    }
}
```"""
        result = classifier._extract_json(text)
        assert result["type"] == "receipt"
        assert result["type_conf"] == 0.95
        assert result["domains"] == ["shopping"]
        assert result["domain_conf"]["shopping"] == 0.9
        assert result["decider"] == "gemini"
        assert result["propose_rule"]["should_propose"] is False
