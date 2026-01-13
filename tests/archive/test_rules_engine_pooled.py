"""

from __future__ import annotations

Test RulesEngine with connection pooling

Validates that RulesEngine correctly uses the connection pool
and performs all operations without database errors.
"""

import pytest

from mailq.classification.rules_engine import RulesEngine
from mailq.infrastructure.database import get_db_connection, init_database


@pytest.fixture(scope="module", autouse=True)
def setup_database():
    """Ensure database is initialized before tests"""
    init_database()


@pytest.fixture
def rules_engine():
    """Create RulesEngine instance"""
    return RulesEngine()


@pytest.fixture
def clean_test_data():
    """Clean up test data after each test"""
    yield
    # Cleanup test data
    with get_db_connection() as conn:
        conn.execute("DELETE FROM rules WHERE user_id = 'test_user'")
        conn.execute("DELETE FROM pending_rules WHERE user_id = 'test_user'")
        conn.commit()


def test_classify_no_match(rules_engine):
    """Test classification when no rules match"""
    result = rules_engine.classify(
        subject="Test Email",
        snippet="Test content",
        from_field="unknown@example.com",
        user_id="test_user",
    )

    assert result["category"] == "Uncategorized"
    assert result["confidence"] == 0.0
    assert result["source"] == "no_rule"


def test_learn_from_classification_pending(rules_engine, _clean_test_data):
    """Test that first classification creates pending rule"""
    rules_engine.learn_from_classification(
        subject="Test",
        snippet="Test",
        from_field="test@example.com",
        category="Newsletters",
        user_id="test_user",
        confidence=0.90,
    )

    # Check pending rules
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT seen_count, category FROM pending_rules
            WHERE user_id = 'test_user' AND pattern = 'test@example.com'
        """)
        result = cursor.fetchone()

    assert result is not None
    assert result[0] == 1  # seen_count
    assert result[1] == "Newsletters"


def test_learn_from_classification_promotion(rules_engine, _clean_test_data):
    """Test that 2 classifications promote pending to confirmed rule"""
    # First classification - creates pending
    rules_engine.learn_from_classification(
        subject="Test",
        snippet="Test",
        from_field="promote@example.com",
        category="Newsletters",
        user_id="test_user",
        confidence=0.90,
    )

    # Second classification - promotes to rule
    rules_engine.learn_from_classification(
        subject="Test",
        snippet="Test",
        from_field="promote@example.com",
        category="Newsletters",
        user_id="test_user",
        confidence=0.90,
    )

    # Verify rule was created
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT category FROM rules
            WHERE user_id = 'test_user' AND pattern = 'promote@example.com'
        """)
        result = cursor.fetchone()

    assert result is not None
    assert result[0] == "Newsletters"


def test_learn_from_correction_immediate(rules_engine, _clean_test_data):
    """Test that user correction creates immediate rule"""
    rules_engine.learn_from_correction(
        email={"from": "correction@example.com"},
        category="Receipts",
        user_id="test_user",
    )

    # Verify rule was created immediately
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT category, confidence FROM rules
            WHERE user_id = 'test_user' AND pattern = 'correction@example.com'
        """)
        result = cursor.fetchone()

    assert result is not None
    assert result[0] == "Receipts"
    assert result[1] == 95  # User corrections get 95% confidence


def test_classify_with_rule(rules_engine, _clean_test_data):
    """Test classification when rule exists"""
    # Create a rule first
    rules_engine.learn_from_correction(
        email={"from": "match@example.com"}, category="Newsletters", user_id="test_user"
    )

    # Classify email that matches the rule
    result = rules_engine.classify(
        subject="Test",
        snippet="Test",
        from_field="match@example.com",
        user_id="test_user",
    )

    assert result["category"] == "Newsletters"
    assert result["confidence"] == 0.95
    assert result["source"] == "rule"


def test_get_matching_rules(rules_engine, _clean_test_data):
    """Test getting all matching rules"""
    # Create a rule
    rules_engine.learn_from_correction(
        email={"from": "matching@example.com"},
        category="Newsletters",
        user_id="test_user",
    )

    # Get matching rules
    matches = rules_engine.get_matching_rules(
        from_field="matching@example.com", subject="Test", user_id="test_user"
    )

    assert len(matches) == 1
    assert matches[0]["category"] == "Newsletters"
    assert matches[0]["pattern"] == "matching@example.com"


def test_get_pending_rules(rules_engine, _clean_test_data):
    """Test getting all pending rules"""
    # Create a pending rule
    rules_engine.learn_from_classification(
        subject="Test",
        snippet="Test",
        from_field="pending@example.com",
        category="Newsletters",
        user_id="test_user",
        confidence=0.90,
    )

    # Get pending rules
    pending = rules_engine.get_pending_rules(user_id="test_user")

    assert len(pending) == 1
    assert pending[0]["pattern"] == "pending@example.com"
    assert pending[0]["category"] == "Newsletters"
    assert pending[0]["seen_count"] == 1


def test_uncategorized_blocked_from_learning(rules_engine, _clean_test_data):
    """Test that uncategorized is never learned as a rule"""
    rules_engine.learn_from_classification(
        subject="Test",
        snippet="Test",
        from_field="uncategorized@example.com",
        category="Uncategorized",
        user_id="test_user",
        confidence=0.90,
    )

    # Verify no pending rule was created
    pending = rules_engine.get_pending_rules(user_id="test_user")
    assert len(pending) == 0


def test_concurrent_access(rules_engine, _clean_test_data):
    """Test that connection pool handles concurrent operations"""
    import threading

    def learn_rule(thread_id):
        rules_engine.learn_from_correction(
            email={"from": f"thread{thread_id}@example.com"},
            category="Newsletters",
            user_id="test_user",
        )

    # Create 10 threads that learn rules concurrently
    threads = []
    for i in range(10):
        t = threading.Thread(target=learn_rule, args=(i,))
        threads.append(t)
        t.start()

    # Wait for all threads
    for t in threads:
        t.join()

    # Verify all rules were created
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) FROM rules
            WHERE user_id = 'test_user' AND pattern LIKE 'thread%'
        """)
        count = cursor.fetchone()[0]

    assert count == 10


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
