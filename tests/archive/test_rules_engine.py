from __future__ import annotations

# test_rules_engine.py
import os
import tempfile

import pytest

from shopq.classification.rules_engine import RulesEngine


class TestRulesEngine:
    @pytest.fixture
    def rules_engine(self):
        """Create a temporary rules engine for testing."""
        with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as temp_db:
            engine = RulesEngine(temp_db.name)
        yield engine
        os.unlink(temp_db.name)  # Cleanup

    def test_init_idempotent(self, rules_engine):
        """A1. init() is idempotent and creates sender_rules."""
        # Should not crash if called multiple times
        engine2 = RulesEngine(rules_engine.db_path)
        assert engine2.count() == 0

    def test_add_and_get_sender_rule(self, rules_engine):
        """A2. add_rule() followed by get_rule() returns the saved category."""
        rules_engine.add_rule("test@example.com", "Work")
        result = rules_engine.get_rule("test@example.com")
        assert result == {"category": "Work"}

        # Test nonexistent sender
        assert rules_engine.get_rule("nonexistent@example.com") is None

    def test_parse_and_learn_from_correction_variants(self, rules_engine):
        """A3. learn_from_correction() correctly parses mixed From formats."""
        test_cases = [
            {"from": "simple@example.com", "expected_sender": "simple@example.com"},
            {
                "from": "Name <email@example.com>",
                "expected_sender": "email@example.com",
            },
            {
                "from": '"Full Name" <full@example.com>',
                "expected_sender": "full@example.com",
            },
            {"From": "CAPS@EXAMPLE.COM", "expected_sender": "caps@example.com"},
        ]

        for i, case in enumerate(test_cases):
            email = {"from": case["from"]} if "from" in case else {"From": case["From"]}
            rules_engine.learn_from_correction(email, f"Category{i}")

            rule = rules_engine.get_rule(case["expected_sender"])
            assert rule == {"category": f"Category{i}"}

    def test_delete_rule(self, rules_engine):
        """A4. delete_rule() removes the mapping; subsequent get_rule() is None."""
        rules_engine.add_rule("delete@example.com", "Personal")
        assert rules_engine.get_rule("delete@example.com") == {"category": "Personal"}

        rules_engine.delete_rule("delete@example.com")
        assert rules_engine.get_rule("delete@example.com") is None

    def test_case_insensitive_match(self, rules_engine):
        """A5. get_rule() match is case-insensitive for sender."""
        rules_engine.add_rule("Test@Example.COM", "Work")

        # Should match regardless of case
        assert rules_engine.get_rule("test@example.com") == {"category": "Work"}
        assert rules_engine.get_rule("TEST@EXAMPLE.COM") == {"category": "Work"}
        assert rules_engine.get_rule("Test@Example.COM") == {"category": "Work"}

    def test_count_changes(self, rules_engine):
        """A6. count() reflects inserts/deletes."""
        assert rules_engine.count() == 0

        rules_engine.add_rule("one@example.com", "Work")
        assert rules_engine.count() == 1

        rules_engine.add_rule("two@example.com", "Personal")
        assert rules_engine.count() == 2

        # Update existing (should not increase count)
        rules_engine.add_rule("one@example.com", "Personal")
        assert rules_engine.count() == 2

        rules_engine.delete_rule("one@example.com")
        assert rules_engine.count() == 1

    def test_upsert_behavior(self, rules_engine):
        """Test that re-adding updates the category."""
        rules_engine.add_rule("update@example.com", "Work")
        assert rules_engine.get_rule("update@example.com") == {"category": "Work"}

        # Update to different category
        rules_engine.add_rule("update@example.com", "Personal")
        assert rules_engine.get_rule("update@example.com") == {"category": "Personal"}
        assert rules_engine.count() == 1  # Should still be 1 rule

    def test_uncategorized_rules_blocked_from_correction(self, rules_engine):
        """Test that 'uncategorized' rules are NEVER created from user corrections."""
        email = {"from": "test@example.com"}

        # Try to create uncategorized rule - should be blocked
        rules_engine.learn_from_correction(email, "Uncategorized")

        # Verify no rule was created
        import sqlite3

        conn = sqlite3.connect(rules_engine.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM rules WHERE category = 'Uncategorized'")
        count = cursor.fetchone()[0]
        conn.close()

        assert count == 0, "Uncategorized rules should never be created"

    def test_uncategorized_variants_blocked(self, rules_engine):
        """Test that all variants of uncategorized are blocked."""
        email = {"from": "test@example.com"}

        blocked_categories = [
            "uncategorized",
            "Uncategorized",
            "review-later",
            "Review-Later",
            "unknown",
            "Unknown",
        ]

        for category in blocked_categories:
            rules_engine.learn_from_correction(email, category)

        # Verify no rules were created
        import sqlite3

        conn = sqlite3.connect(rules_engine.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM rules")
        total_count = cursor.fetchone()[0]
        conn.close()

        assert total_count == 0, (
            f"No uncategorized rules should be created, but found {total_count}"
        )

    def test_uncategorized_blocked_from_classification(self, rules_engine):
        """Test that 'uncategorized' is not added to pending rules from Gemini classifications."""
        # Try to learn uncategorized from classification
        rules_engine.learn_from_classification(
            subject="Test subject",
            snippet="Test snippet",
            from_field="test@example.com",
            category="Uncategorized",
            confidence=0.95,
        )

        # Verify no pending rule was created
        import sqlite3

        conn = sqlite3.connect(rules_engine.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM pending_rules WHERE category = 'Uncategorized'")
        count = cursor.fetchone()[0]
        conn.close()

        assert count == 0, "Uncategorized should not be added to pending rules"
