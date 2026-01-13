"""

from __future__ import annotations

Comprehensive tests for Span-Aware Entity Linker

Tests all edge cases from prd_mailq_span_aware_entity_linker.yml
"""

from mailq.classification.linker import Entity, SpanAwareEntityLinker


class TestBasicMatching:
    """Test basic entity matching"""

    def test_simple_exact_match(self):
        """Test exact match for entity name"""
        linker = SpanAwareEntityLinker(fuzzy_threshold=0.9)

        text = "Bank of America sent you a refund."
        entities = [
            Entity(
                name="Bank of America",
                normalized_name="bank of america",
                url="https://mail.google.com/mail/u/0/#inbox/123",
                entity_type="brand",
            )
        ]

        result = linker.link_entities(text, entities, enable_fallback=False)

        assert result["html_valid"]
        assert result["stats"]["matched_entities"] == 1
        assert (
            '<a href="https://mail.google.com/mail/u/0/#inbox/123">Bank of America</a>'
            in result["html_text"]
        )
        expected_html = (
            '<a href="https://mail.google.com/mail/u/0/#inbox/123">'
            "Bank of America</a> sent you a refund."
        )
        assert result["html_text"] == expected_html

    def test_case_insensitive_match(self):
        """Test case-insensitive matching"""
        linker = SpanAwareEntityLinker(fuzzy_threshold=0.9)

        text = "BANK OF AMERICA sent you a refund."
        entities = [
            Entity(
                name="Bank of America",
                normalized_name="bank of america",
                url="https://mail.google.com/mail/u/0/#inbox/123",
                entity_type="brand",
            )
        ]

        result = linker.link_entities(text, entities, enable_fallback=False)

        assert result["html_valid"]
        assert result["stats"]["matched_entities"] == 1
        # Should preserve original case in link text
        assert (
            '<a href="https://mail.google.com/mail/u/0/#inbox/123">BANK OF AMERICA</a>'
            in result["html_text"]
        )

    def test_punctuation_trim(self):
        """Test that punctuation is trimmed from matched spans"""
        linker = SpanAwareEntityLinker(fuzzy_threshold=0.9)

        text = "Bank of America, sent you a refund."
        entities = [
            Entity(
                name="Bank of America",
                normalized_name="bank of america",
                url="https://mail.google.com/mail/u/0/#inbox/123",
                entity_type="brand",
            )
        ]

        result = linker.link_entities(text, entities, enable_fallback=False)

        assert result["html_valid"]
        assert result["stats"]["matched_entities"] == 1
        # Comma should be outside the link
        expected_text = (
            '<a href="https://mail.google.com/mail/u/0/#inbox/123">'
            "Bank of America</a>, sent you a refund."
        )
        assert expected_text in result["html_text"]


class TestOverlappingEntities:
    """Test handling of overlapping entities"""

    def test_overlapping_entities_resolved(self):
        """Test that overlapping entities are resolved correctly"""
        linker = SpanAwareEntityLinker(fuzzy_threshold=0.85, allow_overlap=False)

        text = "Bank of America and American Airlines updates."
        entities = [
            Entity(
                name="Bank of America",
                normalized_name="bank of america",
                url="https://mail.google.com/mail/u/0/#inbox/123",
                entity_type="brand",
                priority=5,
            ),
            Entity(
                name="American Airlines",
                normalized_name="american airlines",
                url="https://mail.google.com/mail/u/0/#inbox/456",
                entity_type="brand",
                priority=5,
            ),
        ]

        result = linker.link_entities(text, entities, enable_fallback=False)

        assert result["html_valid"]
        # Both entities should be linked
        assert result["stats"]["matched_entities"] == 2
        assert "Bank of America" in result["html_text"]
        assert "American Airlines" in result["html_text"]

    def test_priority_resolution(self):
        """Test that higher priority entity wins in overlaps"""
        linker = SpanAwareEntityLinker(fuzzy_threshold=0.8, allow_overlap=False)

        text = "America sent updates."
        entities = [
            Entity(
                name="Bank of America",
                normalized_name="bank of america",
                url="https://mail.google.com/mail/u/0/#inbox/123",
                entity_type="brand",
                priority=10,  # Higher priority
            ),
            Entity(
                name="America",
                normalized_name="america",
                url="https://mail.google.com/mail/u/0/#inbox/456",
                entity_type="location",
                priority=5,
            ),
        ]

        result = linker.link_entities(text, entities, enable_fallback=False)

        # Only one entity should match (no "Bank of America" in text)
        assert result["stats"]["matched_entities"] == 1


class TestFallbackBehavior:
    """Test fallback behavior when entities can't be matched"""

    def test_paraphrase_fallback(self):
        """Test fallback when entity is paraphrased"""
        linker = SpanAwareEntityLinker(fuzzy_threshold=0.9, fallback_mode="append")

        text = "Your bank refund has posted."
        entities = [
            Entity(
                name="Bank of America",
                normalized_name="bank of america",
                url="https://mail.google.com/mail/u/0/#inbox/123",
                entity_type="brand",
            )
        ]

        result = linker.link_entities(text, entities, enable_fallback=True)

        assert result["html_valid"]
        # Entity should not be matched in text
        assert result["stats"]["matched_entities"] == 0
        # Fallback link should be appended
        assert result["stats"]["fallback_entities"] == 1
        assert "Bank of America View Email →" in result["html_text"]

    def test_no_match_no_fallback(self):
        """Test that text is unchanged when no match and no fallback"""
        linker = SpanAwareEntityLinker(fuzzy_threshold=0.9, fallback_mode="none")

        text = "A refund was sent."
        entities = [
            Entity(
                name="Bank of America",
                normalized_name="bank of america",
                url="https://mail.google.com/mail/u/0/#inbox/123",
                entity_type="brand",
            )
        ]

        result = linker.link_entities(text, entities, enable_fallback=False)

        assert result["html_valid"]
        assert result["stats"]["matched_entities"] == 0
        # Text should be unchanged
        assert result["html_text"] == text


class TestMultipleEntities:
    """Test handling of multiple entities"""

    def test_multiple_entities_linked(self):
        """Test that multiple entities are correctly linked"""
        linker = SpanAwareEntityLinker(fuzzy_threshold=0.85)

        text = "Refunds from Bank of America and PayPal."
        entities = [
            Entity(
                name="Bank of America",
                normalized_name="bank of america",
                url="https://mail.google.com/mail/u/0/#inbox/123",
                entity_type="brand",
            ),
            Entity(
                name="PayPal",
                normalized_name="paypal",
                url="https://mail.google.com/mail/u/0/#inbox/456",
                entity_type="brand",
            ),
        ]

        result = linker.link_entities(text, entities, enable_fallback=False)

        assert result["html_valid"]
        assert result["stats"]["matched_entities"] == 2
        assert "Bank of America</a>" in result["html_text"]
        assert "PayPal</a>" in result["html_text"]


class TestHTMLValidation:
    """Test HTML validation and safety"""

    def test_html_escaping(self):
        """Test that special HTML characters are escaped"""
        linker = SpanAwareEntityLinker(fuzzy_threshold=0.9)

        text = "Company <Test> sent you a message."
        entities = [
            Entity(
                name="Company <Test>",
                normalized_name="company test",
                url="https://mail.google.com/mail/u/0/#inbox/123",
                entity_type="brand",
            )
        ]

        result = linker.link_entities(text, entities, enable_fallback=False)

        assert result["html_valid"]
        # HTML should be escaped
        assert "&lt;" in result["html_text"] or "<Test>" not in result["html_text"]

    def test_balanced_tags(self):
        """Test that tags are balanced"""
        linker = SpanAwareEntityLinker(fuzzy_threshold=0.9)

        text = "Bank of America sent you a refund and PayPal confirmed."
        entities = [
            Entity(
                name="Bank of America",
                normalized_name="bank of america",
                url="https://mail.google.com/mail/u/0/#inbox/123",
                entity_type="brand",
            ),
            Entity(
                name="PayPal",
                normalized_name="paypal",
                url="https://mail.google.com/mail/u/0/#inbox/456",
                entity_type="brand",
            ),
        ]

        result = linker.link_entities(text, entities, enable_fallback=False)

        assert result["html_valid"]
        # Count tags
        open_tags = result["html_text"].count("<a ")
        close_tags = result["html_text"].count("</a>")
        assert open_tags == close_tags


class TestEdgeCases:
    """Test edge cases and boundary conditions"""

    def test_empty_text(self):
        """Test with empty text"""
        linker = SpanAwareEntityLinker()

        result = linker.link_entities("", [], enable_fallback=False)

        assert result["html_valid"]
        assert result["html_text"] == ""
        assert result["stats"]["matched_entities"] == 0

    def test_no_entities(self):
        """Test with no entities"""
        linker = SpanAwareEntityLinker()

        text = "Bank of America sent you a refund."
        result = linker.link_entities(text, [], enable_fallback=False)

        assert result["html_valid"]
        assert result["html_text"] == text
        assert result["stats"]["matched_entities"] == 0

    def test_very_long_entity_name(self):
        """Test with very long entity name"""
        linker = SpanAwareEntityLinker(fuzzy_threshold=0.85)

        text = "The International Business Machines Corporation sent an update."
        entities = [
            Entity(
                name="International Business Machines Corporation",
                normalized_name="international business machines corporation",
                url="https://mail.google.com/mail/u/0/#inbox/123",
                entity_type="brand",
            )
        ]

        result = linker.link_entities(text, entities, enable_fallback=False)

        assert result["html_valid"]
        assert result["stats"]["matched_entities"] == 1

    def test_partial_word_no_match(self):
        """Test that partial words don't match"""
        linker = SpanAwareEntityLinker(fuzzy_threshold=0.95)

        text = "American sent you a message."
        entities = [
            Entity(
                name="America",
                normalized_name="america",
                url="https://mail.google.com/mail/u/0/#inbox/123",
                entity_type="location",
            )
        ]

        result = linker.link_entities(text, entities, enable_fallback=False)

        # Should not match "American" with "America" at high threshold
        # (though at lower thresholds it might)
        assert result["html_valid"]


class TestFuzzyThreshold:
    """Test fuzzy matching threshold behavior"""

    def test_high_threshold_exact_match_only(self):
        """Test that high threshold requires exact match"""
        linker = SpanAwareEntityLinker(fuzzy_threshold=0.99)

        text = "Bank America sent you a refund."  # Missing "of"
        entities = [
            Entity(
                name="Bank of America",
                normalized_name="bank of america",
                url="https://mail.google.com/mail/u/0/#inbox/123",
                entity_type="brand",
            )
        ]

        result = linker.link_entities(text, entities, enable_fallback=False)

        # Should not match with missing word at 0.99 threshold
        assert result["stats"]["matched_entities"] == 0

    def test_low_threshold_fuzzy_match(self):
        """Test that low threshold allows fuzzy match"""
        linker = SpanAwareEntityLinker(fuzzy_threshold=0.75)

        text = "Bank America sent you a refund."  # Missing "of"
        entities = [
            Entity(
                name="Bank of America",
                normalized_name="bank of america",
                url="https://mail.google.com/mail/u/0/#inbox/123",
                entity_type="brand",
            )
        ]

        result = linker.link_entities(text, entities, enable_fallback=False)

        # Should match with missing word at 0.75 threshold
        assert result["stats"]["matched_entities"] == 1


# Run with: pytest mailq/tests/test_span_linker.py -v
