"""
Simplified tests for debug endpoints
"""

from __future__ import annotations

from datetime import datetime

import pytest

from mailq.api.routes import debug as api_debug
from mailq.api.routes.debug import _get_entity_title, set_last_digest
from mailq.classification.models import FlightEntity


class TestDebugEndpoints:
    """Test debug endpoint functionality"""

    def test_set_last_digest(self):
        """Test setting digest data"""
        test_data = {
            "total_ranked": 10,
            "filtered_remaining": 5,
            "featured": [],
            "all_entities": [],
            "importance_groups": {},
            "all_emails": [],
            "noise_breakdown": {},
        }

        set_last_digest(test_data)

        assert api_debug.last_digest_store["total_ranked"] == 10
        assert api_debug.last_digest_store["filtered_remaining"] == 5
        assert api_debug.last_digest_store["timestamp"] is not None

    def test_get_entity_title_flight(self):
        """Test entity title extraction for flight"""
        flight = FlightEntity(
            flight_number="AA123",
            confidence=0.95,
            source_email_id="msg_1",
            source_subject="Flight",
            source_snippet="Test flight",
            timestamp=datetime.now(),
        )

        title = _get_entity_title(flight)
        assert title == "Flight AA123"


class TestDebugInlineHints:
    """Test DEBUG_FEATURED inline hints"""

    def test_inline_debug_hidden_by_default(self):
        """Test that debug hints are not added when DEBUG_FEATURED is not set"""
        import os

        from mailq.digest.card_renderer import CardRenderer

        # Ensure DEBUG_FEATURED is not set
        os.environ.pop("DEBUG_FEATURED", None)

        renderer = CardRenderer()

        # Create a simple entity
        flight = FlightEntity(
            flight_number="AA123",
            confidence=0.95,
            source_email_id="msg_1",
            source_subject="Flight",
            source_snippet="Test",
            timestamp=datetime.now(),
        )
        flight.importance = "critical"
        flight.priority_score = 0.95

        digest_text = "Your flight AA123 departs at 10:00 AM."

        html = renderer.render(digest_text, entities=[flight])

        # Should NOT contain debug hints
        assert "[score=" not in html
        assert "conf=" not in html

    @pytest.mark.skip(reason="DEBUG_FEATURED inline hints not yet implemented in V2 CardRenderer")
    def test_inline_debug_shown_when_enabled(self):
        """Test that debug hints are added when DEBUG_FEATURED=true"""
        import os

        from mailq.digest.card_renderer import CardRenderer

        # Enable DEBUG_FEATURED
        os.environ["DEBUG_FEATURED"] = "true"

        renderer = CardRenderer()

        # Create a simple entity
        flight = FlightEntity(
            flight_number="AA123",
            confidence=0.95,
            source_email_id="msg_1",
            source_subject="Flight",
            source_snippet="Test",
            timestamp=datetime.now(),
        )
        flight.importance = "critical"
        flight.priority_score = 0.95

        digest_text = "Your flight AA123 departs at 10:00 AM."

        html = renderer.render(digest_text, entities=[flight])

        # Should contain debug hints
        assert "[score=" in html
        assert "critical" in html
        assert "conf=" in html

        # Clean up
        os.environ.pop("DEBUG_FEATURED")


# Run with: pytest mailq/tests/test_debug_endpoints_simple.py -v
