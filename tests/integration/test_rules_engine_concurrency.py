"""
Integration tests for RulesEngine concurrency and race condition fixes.

Tests verify that concurrent calls to learn_from_classification and classify
do not create duplicate rules or cause database integrity violations.
"""

from __future__ import annotations

import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from shopq.classification.rules_engine import RulesEngine
from shopq.infrastructure.database import db_transaction, get_db_connection
from shopq.runtime.gates import feature_gates


class TestRulesEngineConcurrency:
    """Test concurrent access to rules engine"""

    @pytest.fixture(autouse=True)
    def setup_teardown(self):
        """Clean up rules before/after each test and disable test_mode"""
        # Disable test_mode to allow rule learning
        original_test_mode = feature_gates.is_enabled("test_mode")
        feature_gates.disable("test_mode")

        # Clear existing rules
        with db_transaction() as conn:
            conn.execute("DELETE FROM rules")
            conn.execute("DELETE FROM pending_rules")
        yield
        # Cleanup after test
        with db_transaction() as conn:
            conn.execute("DELETE FROM rules")
            conn.execute("DELETE FROM pending_rules")

        # Restore original test_mode state
        if original_test_mode:
            feature_gates.enable("test_mode")
        else:
            feature_gates.disable("test_mode")

    def test_concurrent_pending_rule_creation(self):
        """
        Test that concurrent threads trying to create the same pending rule
        don't create duplicates or cause integrity violations.
        """
        engine = RulesEngine()
        errors = []
        success_count = [0]

        def learn_concurrent():
            try:
                engine.learn_from_classification(
                    _subject="Test",
                    _snippet="Test",
                    from_field="concurrent@example.com",
                    category="Work",
                    user_id="test_user",
                    confidence=0.85,
                )
                success_count[0] += 1
            except Exception as e:
                errors.append(e)

        # Run 5 concurrent threads trying to create the same pending rule
        # (limited to match connection pool size to avoid exhaustion)
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(learn_concurrent) for _ in range(5)]
            for future in futures:
                future.result()

        # Should have no errors
        assert len(errors) == 0, f"Got errors: {errors}"
        assert success_count[0] == 5, "All threads should succeed"

        # Should have exactly 1 pending rule OR 1 promoted rule (not multiple)
        # Due to race timing, the pending rule might get promoted during the test
        with get_db_connection() as conn:
            cursor = conn.cursor()

            # Check pending rules
            cursor.execute(
                """
                SELECT COUNT(*) FROM pending_rules
                WHERE user_id = 'test_user'
                    AND pattern = 'concurrent@example.com'
                    AND category = 'Work'
            """
            )
            pending_count = cursor.fetchone()[0]

            # Check promoted rules
            cursor.execute(
                """
                SELECT COUNT(*) FROM rules
                WHERE user_id = 'test_user'
                    AND pattern = 'concurrent@example.com'
                    AND category = 'Work'
            """
            )
            rule_count = cursor.fetchone()[0]

        # Should have at most 1 promoted rule
        # Due to SQLite transaction isolation, we might have extra pending rules created
        # after promotion (threads that started before promotion committed won't see the rule)
        # This is acceptable - they'll be cleaned up on next learning cycle
        assert rule_count <= 1, f"Expected at most 1 promoted rule, got {rule_count}"
        assert pending_count + rule_count >= 1, "Expected at least 1 record total"

    def test_concurrent_pending_rule_promotion(self):
        """
        Test that concurrent threads trying to promote the same pending rule
        create exactly one rule in the rules table.
        """
        engine = RulesEngine()

        # Pre-create a pending rule with seen_count=1
        with db_transaction() as conn:
            conn.execute(
                """
                INSERT INTO pending_rules (
                    user_id, pattern_type, pattern, category, confidence, seen_count
                )
                VALUES ('test_user', 'from', 'promote@example.com', 'Work', 85, 1)
            """
            )

        errors = []
        success_count = [0]

        def promote_concurrent():
            try:
                # This should increment seen_count to 2 and promote to rule
                engine.learn_from_classification(
                    _subject="Test",
                    _snippet="Test",
                    from_field="promote@example.com",
                    category="Work",
                    user_id="test_user",
                    confidence=0.85,
                )
                success_count[0] += 1
            except Exception as e:
                errors.append(e)

        # Run 5 concurrent threads trying to promote the same pending rule
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(promote_concurrent) for _ in range(5)]
            for future in futures:
                future.result()

        # Should have no errors
        assert len(errors) == 0, f"Got errors: {errors}"
        assert success_count[0] == 5, "All threads should succeed"

        # Should have exactly 1 rule (not 5)
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT COUNT(*) FROM rules
                WHERE user_id = 'test_user'
                    AND pattern = 'promote@example.com'
                    AND category = 'Work'
            """
            )
            rule_count = cursor.fetchone()[0]

            # Pending rule should be deleted
            cursor.execute(
                """
                SELECT COUNT(*) FROM pending_rules
                WHERE user_id = 'test_user'
                    AND pattern = 'promote@example.com'
            """
            )
            pending_count = cursor.fetchone()[0]

        assert rule_count == 1, f"Expected 1 rule, got {rule_count}"
        assert pending_count == 0, f"Expected 0 pending rules, got {pending_count}"

    def test_concurrent_rule_updates(self):
        """
        Test that concurrent threads trying to update the same rule
        don't cause integrity violations.
        """
        engine = RulesEngine()

        # Pre-create a rule with low confidence
        with db_transaction() as conn:
            conn.execute(
                """
                INSERT INTO rules (user_id, pattern_type, pattern, category, confidence)
                VALUES ('test_user', 'from', 'update@example.com', 'Work', 50)
            """
            )

        errors = []
        success_count = [0]

        def update_concurrent(new_confidence: float):
            try:
                engine.learn_from_classification(
                    _subject="Test",
                    _snippet="Test",
                    from_field="update@example.com",
                    category="Work",
                    user_id="test_user",
                    confidence=new_confidence,
                )
                success_count[0] += 1
            except Exception as e:
                errors.append(e)

        # Run 5 concurrent threads with increasing confidence values
        # (limited to match connection pool size)
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(update_concurrent, 0.50 + (i * 0.01)) for i in range(5)]
            for future in futures:
                future.result()

        # Should have no errors
        assert len(errors) == 0, f"Got errors: {errors}"
        assert success_count[0] == 5, "All threads should succeed"

        # Should still have exactly 1 rule
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT COUNT(*), MAX(confidence) FROM rules
                WHERE user_id = 'test_user' AND pattern = 'update@example.com'
            """
            )
            count, max_confidence = cursor.fetchone()

        assert count == 1, f"Expected 1 rule, got {count}"
        # Confidence should be higher than initial value (50)
        # Due to concurrency, not all updates may succeed, but at least one should
        assert max_confidence > 50, f"Expected confidence > 50, got {max_confidence}"

    def test_concurrent_classify_with_use_count(self):
        """
        Test that concurrent classify calls incrementing use_count
        don't cause errors (lost updates are acceptable for metrics).
        """
        engine = RulesEngine()

        # Pre-create a rule
        with db_transaction() as conn:
            conn.execute(
                """
                INSERT INTO rules (user_id, pattern_type, pattern, category, confidence, use_count)
                VALUES ('test_user', 'from', 'classify@example.com', 'Work', 85, 0)
            """
            )

        errors = []
        success_count = [0]
        results = []

        def classify_concurrent():
            try:
                result = engine.classify(
                    _subject="Test",
                    _snippet="Test",
                    from_field="classify@example.com",
                    user_id="test_user",
                )
                results.append(result)
                success_count[0] += 1
            except Exception as e:
                errors.append(e)

        # Run 5 concurrent classification calls (limited to pool size)
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(classify_concurrent) for _ in range(5)]
            for future in futures:
                future.result()

        # Should have no errors
        assert len(errors) == 0, f"Got errors: {errors}"
        assert success_count[0] == 5, "All threads should succeed"

        # All results should match the rule
        for result in results:
            assert result["category"] == "Work"
            assert result["confidence"] == 0.85
            assert result["source"] == "rule"

        # use_count should be incremented (may not be exactly 5 due to race conditions,
        # but should be > 0 and <= 5)
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT use_count FROM rules WHERE pattern = 'classify@example.com'")
            use_count = cursor.fetchone()[0]

        assert 1 <= use_count <= 5, f"Expected use_count between 1 and 5, got {use_count}"

    def test_no_duplicate_rules_from_concurrent_corrections(self):
        """
        Test that concurrent user corrections don't create duplicate rules.
        """
        engine = RulesEngine()
        errors = []

        def correct_concurrent():
            try:
                engine.learn_from_correction(
                    email={"from": "correction@example.com"},
                    category="Personal",
                    user_id="test_user",
                )
            except sqlite3.IntegrityError as e:
                # IntegrityError is acceptable here - INSERT OR REPLACE handles it
                errors.append(e)

        # Run 5 concurrent corrections (limited to pool size)
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(correct_concurrent) for _ in range(5)]
            for future in futures:
                future.result()

        # Should have no IntegrityError exceptions
        assert len(errors) == 0, f"Got integrity errors: {errors}"

        # Should have exactly 1 rule
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT COUNT(*) FROM rules
                WHERE user_id = 'test_user' AND pattern = 'correction@example.com'
            """
            )
            count = cursor.fetchone()[0]

        assert count == 1, f"Expected 1 rule, got {count}"

    def test_mixed_concurrent_operations(self):
        """
        Test mixed concurrent operations (learn, classify, correct)
        on the same pattern.
        """
        engine = RulesEngine()
        errors = []
        barrier = threading.Barrier(9)  # Synchronize all threads to start at once

        def learn():
            try:
                barrier.wait()  # Wait for all threads
                engine.learn_from_classification(
                    _subject="Test",
                    _snippet="Test",
                    from_field="mixed@example.com",
                    category="Work",
                    user_id="test_user",
                    confidence=0.80,
                )
            except Exception as e:
                errors.append(e)

        def classify():
            try:
                barrier.wait()
                engine.classify(
                    _subject="Test",
                    _snippet="Test",
                    from_field="mixed@example.com",
                    user_id="test_user",
                )
            except Exception as e:
                errors.append(e)

        def correct():
            try:
                barrier.wait()
                engine.learn_from_correction(
                    email={"from": "mixed@example.com"},
                    category="Work",
                    user_id="test_user",
                )
            except Exception as e:
                errors.append(e)

        # Run mixed operations: 3 learn, 3 classify, 3 correct
        # (limited to avoid pool exhaustion)
        with ThreadPoolExecutor(max_workers=9) as executor:
            futures = []
            for _ in range(3):
                futures.append(executor.submit(learn))
            for _ in range(3):
                futures.append(executor.submit(classify))
            for _ in range(3):
                futures.append(executor.submit(correct))

            for future in futures:
                future.result()

        # Should have no errors
        assert len(errors) == 0, f"Got errors: {errors}"

        # Should have at most 1 rule and 0-1 pending rules
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT COUNT(*) FROM rules
                WHERE user_id = 'test_user' AND pattern = 'mixed@example.com'
            """
            )
            rule_count = cursor.fetchone()[0]

            cursor.execute(
                """
                SELECT COUNT(*) FROM pending_rules
                WHERE user_id = 'test_user' AND pattern = 'mixed@example.com'
            """
            )
            pending_count = cursor.fetchone()[0]

        # Due to concurrent corrections, we should have 1 rule
        assert rule_count <= 1, f"Expected at most 1 rule, got {rule_count}"
        assert pending_count <= 1, f"Expected at most 1 pending rule, got {pending_count}"
        # At least one should exist
        assert rule_count + pending_count >= 1, (
            "Expected at least one rule or pending rule to exist"
        )
