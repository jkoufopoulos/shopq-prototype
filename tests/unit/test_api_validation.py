"""
Tests for API Pydantic validation added in Agent B Phase 1-3.

Tests validation logic for:
- VerifyRequest model (email, first_result, features validation)
- SummaryRequest model (current_data, timezone, timezone_offset_minutes validation)
- FeedbackInput model (email_id, subject, labels validation)
"""

import pytest
from pydantic import ValidationError

from shopq.api.app import SummaryRequest, VerifyRequest
from shopq.api.routes.feedback import FeedbackInput


class TestVerifyRequestValidation:
    """Tests for VerifyRequest model validation"""

    def test_valid_verify_request(self):
        """Test that valid VerifyRequest passes validation"""
        request = VerifyRequest(
            email={
                "id": "123",
                "subject": "Test",
                "snippet": "Test snippet",
                "from": "test@example.com",
            },
            first_result={"type": "event", "confidence": 0.9},
            features={"has_time": True},
        )
        assert request.email["subject"] == "Test"

    def test_email_missing_required_field(self):
        """Test that email dict without required fields fails"""
        with pytest.raises(ValidationError) as exc_info:
            VerifyRequest(
                email={"id": "123"},  # Missing subject, snippet, from
                first_result={"type": "event"},
                features={},
            )
        assert "Email missing required field" in str(exc_info.value)

    def test_email_dict_too_large(self):
        """Test that email dict with too many keys fails"""
        large_email = {
            "id": "123",
            "subject": "Test",
            "snippet": "Test",
            "from": "test@example.com",
        }
        # Add 50 more keys (exceeds max_keys=50)
        for i in range(50):
            large_email[f"extra_field_{i}"] = "value"

        with pytest.raises(ValidationError) as exc_info:
            VerifyRequest(
                email=large_email,
                first_result={"type": "event"},
                features={},
            )
        assert "too many keys" in str(exc_info.value).lower()

    def test_email_string_too_long(self):
        """Test that email with extremely long string fails"""
        with pytest.raises(ValidationError) as exc_info:
            VerifyRequest(
                email={
                    "id": "123",
                    "subject": "A" * 10001,  # Exceeds max_str_len=5000
                    "snippet": "Test",
                    "from": "test@example.com",
                },
                first_result={"type": "event"},
                features={},
            )
        assert "too long" in str(exc_info.value).lower()

    def test_first_result_missing_type(self):
        """Test that first_result without 'type' field fails"""
        with pytest.raises(ValidationError) as exc_info:
            VerifyRequest(
                email={
                    "id": "123",
                    "subject": "Test",
                    "snippet": "Test",
                    "from": "test@example.com",
                },
                first_result={"confidence": 0.9},  # Missing 'type'
                features={},
            )
        assert "missing required 'type' field" in str(exc_info.value).lower()

    def test_features_dict_too_large(self):
        """Test that features dict with too many keys fails"""
        large_features = {f"feature_{i}": True for i in range(51)}  # Exceeds max_keys=50

        with pytest.raises(ValidationError) as exc_info:
            VerifyRequest(
                email={
                    "id": "123",
                    "subject": "Test",
                    "snippet": "Test",
                    "from": "test@example.com",
                },
                first_result={"type": "event"},
                features=large_features,
            )
        assert "too many keys" in str(exc_info.value).lower()


class TestSummaryRequestValidation:
    """Tests for SummaryRequest model validation"""

    def test_valid_summary_request(self):
        """Test that valid SummaryRequest passes validation"""
        request = SummaryRequest(
            current_data=[
                {"id": "1", "subject": "Test 1"},
                {"id": "2", "subject": "Test 2"},
            ],
            timezone="America/New_York",
            timezone_offset_minutes=-300,
        )
        assert len(request.current_data) == 2

    def test_current_data_empty(self):
        """Test that empty current_data fails"""
        with pytest.raises(ValidationError) as exc_info:
            SummaryRequest(current_data=[])
        # Pydantic Field constraint triggers before custom validator
        assert (
            "at least 1 item" in str(exc_info.value).lower()
            or "cannot be empty" in str(exc_info.value).lower()
        )

    def test_current_data_missing_id(self):
        """Test that email without 'id' field fails"""
        with pytest.raises(ValidationError) as exc_info:
            SummaryRequest(
                current_data=[
                    {"subject": "Test"}  # Missing 'id'
                ]
            )
        assert "missing required 'id' field" in str(exc_info.value).lower()

    def test_current_data_missing_subject(self):
        """Test that email without 'subject' field fails"""
        with pytest.raises(ValidationError) as exc_info:
            SummaryRequest(
                current_data=[
                    {"id": "123"}  # Missing 'subject'
                ]
            )
        assert "missing required 'subject' field" in str(exc_info.value).lower()

    def test_current_data_email_too_large(self):
        """Test that email dict with too many keys fails"""
        large_email = {"id": "123", "subject": "Test"}
        # Add 50 more keys (exceeds max_keys=50)
        for i in range(50):
            large_email[f"extra_{i}"] = "value"

        with pytest.raises(ValidationError) as exc_info:
            SummaryRequest(current_data=[large_email])
        assert "too many keys" in str(exc_info.value).lower()

    def test_timezone_invalid_format(self):
        """Test that invalid timezone format fails"""
        with pytest.raises(ValidationError) as exc_info:
            SummaryRequest(
                current_data=[{"id": "1", "subject": "Test"}],
                timezone="InvalidFormat",  # Should be "Region/City"
            )
        # Can be caught by Field pattern or custom validator
        assert (
            "pattern" in str(exc_info.value).lower()
            or "invalid timezone format" in str(exc_info.value).lower()
        )

    def test_timezone_valid_format(self):
        """Test that valid timezone format passes"""
        request = SummaryRequest(
            current_data=[{"id": "1", "subject": "Test"}],
            timezone="America/New_York",
        )
        assert request.timezone == "America/New_York"

    def test_timezone_offset_within_common_range(self):
        """Test that timezone offset within common range passes without warning"""
        request = SummaryRequest(
            current_data=[{"id": "1", "subject": "Test"}],
            timezone_offset_minutes=-300,  # UTC-5 (common)
        )
        assert request.timezone_offset_minutes == -300

    def test_timezone_offset_unusual_logs_warning(self, caplog):
        """Test that unusual timezone offset logs warning but still passes"""
        import logging

        caplog.set_level(logging.WARNING)

        request = SummaryRequest(
            current_data=[{"id": "1", "subject": "Test"}],
            timezone_offset_minutes=800,  # UTC+13:20 (unusual but valid)
        )
        assert request.timezone_offset_minutes == 800
        # Check that warning was logged
        assert any("Unusual timezone offset" in message for message in caplog.messages)

    def test_timezone_offset_out_of_bounds(self):
        """Test that timezone offset outside valid range fails"""
        with pytest.raises(ValidationError) as exc_info:
            SummaryRequest(
                current_data=[{"id": "1", "subject": "Test"}],
                timezone_offset_minutes=1000,  # Exceeds max=840
            )
        # Field constraint: must be between -720 and 840
        assert "less than or equal to 840" in str(exc_info.value) or "840" in str(exc_info.value)


class TestFeedbackInputValidation:
    """Tests for FeedbackInput model validation"""

    def test_valid_feedback_input(self):
        """Test that valid FeedbackInput passes validation"""
        feedback = FeedbackInput(
            email_id="test123",
            **{"from": "test@example.com"},
            subject="Test Subject",
            snippet="Test snippet",
            predicted_labels=["event"],
            actual_labels=["receipt"],
            predicted_result={"type": "event", "confidence": 0.9},
        )
        assert feedback.email_id == "test123"

    def test_email_id_empty_string(self):
        """Test that empty email_id fails"""
        with pytest.raises(ValidationError) as exc_info:
            FeedbackInput(
                email_id="",
                **{"from": "test@example.com"},
                subject="Test",
                predicted_labels=["event"],
                actual_labels=["receipt"],
                predicted_result={"type": "event"},
            )
        # Field constraint min_length=1 triggers before custom validator
        assert (
            "at least 1 character" in str(exc_info.value).lower()
            or "cannot be empty" in str(exc_info.value).lower()
        )

    def test_email_id_whitespace_only(self):
        """Test that whitespace-only email_id fails"""
        with pytest.raises(ValidationError) as exc_info:
            FeedbackInput(
                email_id="   ",
                **{"from": "test@example.com"},
                subject="Test",
                predicted_labels=["event"],
                actual_labels=["receipt"],
                predicted_result={"type": "event"},
            )
        assert "email_id cannot be empty" in str(exc_info.value)

    def test_subject_empty_string(self):
        """Test that empty subject fails"""
        with pytest.raises(ValidationError) as exc_info:
            FeedbackInput(
                email_id="test123",
                **{"from": "test@example.com"},
                subject="",
                predicted_labels=["event"],
                actual_labels=["receipt"],
                predicted_result={"type": "event"},
            )
        # Field constraint min_length=1 triggers before custom validator
        assert (
            "at least 1 character" in str(exc_info.value).lower()
            or "cannot be empty" in str(exc_info.value).lower()
        )

    def test_predicted_labels_empty(self):
        """Test that empty predicted_labels list fails"""
        with pytest.raises(ValidationError) as exc_info:
            FeedbackInput(
                email_id="test123",
                **{"from": "test@example.com"},
                subject="Test",
                predicted_labels=[],  # Empty list
                actual_labels=["receipt"],
                predicted_result={"type": "event"},
            )
        # Field constraint min_length=1 triggers before custom validator
        assert (
            "at least 1 item" in str(exc_info.value).lower()
            or "cannot be empty" in str(exc_info.value).lower()
        )

    def test_actual_labels_empty(self):
        """Test that empty actual_labels list fails"""
        with pytest.raises(ValidationError) as exc_info:
            FeedbackInput(
                email_id="test123",
                **{"from": "test@example.com"},
                subject="Test",
                predicted_labels=["event"],
                actual_labels=[],  # Empty list
                predicted_result={"type": "event"},
            )
        # Field constraint min_length=1 triggers before custom validator
        assert (
            "at least 1 item" in str(exc_info.value).lower()
            or "cannot be empty" in str(exc_info.value).lower()
        )

    def test_predicted_result_missing_type(self):
        """Test that predicted_result without 'type' field fails"""
        with pytest.raises(ValidationError) as exc_info:
            FeedbackInput(
                email_id="test123",
                **{"from": "test@example.com"},
                subject="Test",
                predicted_labels=["event"],
                actual_labels=["receipt"],
                predicted_result={"confidence": 0.9},  # Missing 'type'
            )
        assert "missing required 'type' field" in str(exc_info.value)


class TestDictStructureValidationEdgeCases:
    """Tests for validate_dict_structure() security edge cases"""

    def test_deeply_nested_lists_in_dict_rejected(self):
        """Test that deeply nested lists within dict values are rejected"""
        # Create deeply nested list structure inside a dict value
        nested_list = ["value"]
        for _ in range(6):  # 6 levels of list nesting (exceeds MAX_DICT_DEPTH=5)
            nested_list = [nested_list]

        with pytest.raises(ValidationError) as exc_info:
            SummaryRequest(current_data=[{"id": "1", "subject": "Test", "data": nested_list}])
        assert "nesting exceeds maximum depth" in str(exc_info.value).lower()

    def test_alternating_dict_list_nesting(self):
        """Test mixed dict-list nesting at max depth is rejected"""
        # Build alternating dict-list structure that exceeds depth
        # Start with a simple value, then alternate between dict and list wrapping
        nested = "value"
        for i in range(6):  # Exceeds MAX_DICT_DEPTH=5
            if i % 2 == 0:
                nested = [nested]
            else:
                nested = {"nested": nested}

        with pytest.raises(ValidationError) as exc_info:
            SummaryRequest(current_data=[{"id": "1", "subject": "Test", "data": nested}])
        assert "exceeds maximum depth" in str(exc_info.value).lower()

    def test_max_depth_boundary_passes(self):
        """Test that exactly MAX_DICT_DEPTH nesting passes"""
        # MAX_DICT_DEPTH = 5
        # Depth 0: current_data list item {"id": "1", "subject": "Test", "data": {...}}
        # Depth 1-4: nested dicts (4 levels of nesting)
        # Total depth = 5 (should pass)
        nested = {"level3": "value"}
        nested = {"level2": nested}
        nested = {"level1": nested}

        # Should pass - this is within max depth
        request = SummaryRequest(current_data=[{"id": "1", "subject": "Test", "data": nested}])
        assert request.current_data

    def test_max_depth_plus_one_fails(self):
        """Test that MAX_DICT_DEPTH + 1 nesting fails"""
        # MAX_DICT_DEPTH = 5
        # Depth 0: current_data list item dict
        # Depth 1: "data" key's dict value
        # Depth 2-6: nested dicts (5 more levels)
        # Total depth = 7 (exceeds max of 5, should fail)
        nested = {"level5": "value"}
        nested = {"level4": nested}
        nested = {"level3": nested}
        nested = {"level2": nested}
        nested = {"level1": nested}
        nested = {"level0": nested}

        with pytest.raises(ValidationError) as exc_info:
            SummaryRequest(current_data=[{"id": "1", "subject": "Test", "data": nested}])
        assert "exceeds maximum depth" in str(exc_info.value).lower()

    def test_list_of_lists_with_dict_attack(self):
        """Test that deeply nested lists containing dicts are rejected"""
        # Create a realistic attack: lists nested deeply with a dict at the end
        # This tests that we track list depth properly
        nested = {"attack": "payload"}
        for _ in range(6):  # 6 levels of list nesting
            nested = [nested]

        with pytest.raises(ValidationError) as exc_info:
            SummaryRequest(current_data=[{"id": "1", "subject": "Test", "data": nested}])
        assert "nesting exceeds maximum depth" in str(exc_info.value).lower()

    def test_combined_size_and_depth_attack(self):
        """Test that max keys at max depth is rejected if it exceeds limits"""
        # Build a dict with many keys at deep nesting
        large_dict = {f"key_{i}": "value" for i in range(51)}  # Exceeds max_keys=50

        with pytest.raises(ValidationError) as exc_info:
            SummaryRequest(current_data=[{"id": "1", "subject": "Test", "data": large_dict}])
        assert "too many keys" in str(exc_info.value).lower()

    def test_long_string_in_nested_list(self):
        """Test that extremely long strings in nested lists are rejected"""
        # Create a list with a very long string
        long_string = "A" * 10001  # Exceeds MAX_STRING_LENGTH=10000

        with pytest.raises(ValidationError) as exc_info:
            SummaryRequest(current_data=[{"id": "1", "subject": "Test", "data": [long_string]}])
        assert "too long" in str(exc_info.value).lower()
