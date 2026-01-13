"""
Tests for retention and privacy module.

Validates:
1. 14-day retention policy correctly deletes old data
2. Anonymization properly masks PII for non-owners
3. Owner access is not anonymized
4. Cleanup stats are accurate
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from shopq.storage.retention import (
    anonymize_digest_session,
    anonymize_email_thread,
    cleanup_old_artifacts,
    get_retention_stats,
)


@pytest.fixture
def test_db():
    """Create in-memory test database with sample data."""
    conn = sqlite3.connect(":memory:")
    cursor = conn.cursor()

    # Create email_threads table
    cursor.execute("""
        CREATE TABLE email_threads (
            id INTEGER PRIMARY KEY,
            thread_id TEXT NOT NULL,
            message_id TEXT NOT NULL,
            from_email TEXT NOT NULL,
            subject TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            importance TEXT NOT NULL,
            user_id TEXT DEFAULT 'default' NOT NULL
        )
    """)

    # Create digest_sessions table
    cursor.execute("""
        CREATE TABLE digest_sessions (
            session_id TEXT PRIMARY KEY,
            digest_html TEXT,
            digest_text TEXT,
            generated_at TEXT,
            email_count INTEGER,
            user_id TEXT DEFAULT 'default' NOT NULL
        )
    """)

    conn.commit()
    yield conn
    conn.close()


def test_anonymize_email_thread_owner_access():
    """Test that owner has full access to their data."""
    thread = {
        "from_email": "alice@example.com",
        "subject": "Important meeting tomorrow",
        "message_id": "msg123",
        "summary_line": "Meeting with Bob at 2pm",
    }

    result = anonymize_email_thread(thread, owner_user_id="alice", requesting_user_id="alice")

    # Owner should get exact original data
    assert result == thread
    assert result["from_email"] == "alice@example.com"
    assert result["subject"] == "Important meeting tomorrow"
    assert result["message_id"] == "msg123"


def test_anonymize_email_thread_non_owner_access():
    """Test that non-owner gets anonymized data."""
    thread = {
        "from_email": "alice@example.com",
        "subject": "Important meeting tomorrow",
        "message_id": "msg123",
        "summary_line": "Meeting with Bob at 2pm",
        "entity_details": '{"flight": "AA123"}',
    }

    result = anonymize_email_thread(thread, owner_user_id="alice", requesting_user_id="bob")

    # Non-owner should get anonymized data
    # Email format: user_<hash>@domain_<hash>
    assert result["from_email"].startswith("user_")
    assert "@domain_" in result["from_email"]
    assert "alice" not in result["from_email"]  # No PII
    assert "example.com" not in result["from_email"]  # No domain leakage
    assert "[MASKED]" in result["subject"] or result["subject"] != thread["subject"]
    assert result["message_id"] == "[REDACTED]"  # Sensitive fields redacted
    assert result["summary_line"] == "[REDACTED]"
    assert result["entity_details"] == "[REDACTED]"


def test_anonymize_digest_session_owner_access():
    """Test that owner has full access to digest sessions."""
    session = {
        "session_id": "session123",
        "digest_html": "<html>Full digest content with PII</html>",
        "digest_text": "Text with alice@example.com",
        "email_count": 10,
        "critical_count": 2,
    }

    result = anonymize_digest_session(session, owner_user_id="alice", requesting_user_id="alice")

    # Owner gets full data
    assert result == session
    assert "Full digest content" in result["digest_html"]


def test_anonymize_digest_session_non_owner_access():
    """Test that non-owner gets only aggregate stats."""
    session = {
        "session_id": "session123",
        "digest_html": "<html>Full digest content with PII</html>",
        "digest_text": "Text with alice@example.com",
        "generated_at": "2025-11-11T12:00:00Z",
        "email_count": 10,
        "critical_count": 2,
        "time_sensitive_count": 5,
    }

    result = anonymize_digest_session(session, owner_user_id="alice", requesting_user_id="bob")

    # Non-owner gets only safe aggregate fields
    assert result["session_id"] == "session123"
    assert result["email_count"] == 10
    assert result["critical_count"] == 2
    assert result["time_sensitive_count"] == 5

    # PII fields should be removed
    assert "digest_html" not in result or result["digest_html"] == "[REDACTED]"
    assert "digest_text" not in result or result["digest_text"] == "[REDACTED]"


def test_cleanup_old_artifacts_dry_run(test_db, monkeypatch):
    """Test dry run mode doesn't actually delete data."""
    # Insert old and new threads
    now = datetime.now(UTC)
    old_date = (now - timedelta(days=20)).isoformat()
    new_date = (now - timedelta(days=5)).isoformat()

    cursor = test_db.cursor()
    cursor.execute(
        """
        INSERT INTO email_threads (thread_id, message_id, from_email, subject, timestamp, importance, user_id)
        VALUES
            ('thread1', 'msg1', 'old@example.com', 'Old email', ?, 'routine', 'alice'),
            ('thread2', 'msg2', 'new@example.com', 'New email', ?, 'critical', 'alice')
    """,
        (old_date, new_date),
    )
    test_db.commit()

    # Mock database connection to use test DB
    def mock_transaction():
        class MockContext:
            def __enter__(self):
                return test_db

            def __exit__(self, *args):
                test_db.commit()

        return MockContext()

    monkeypatch.setattr("shopq.storage.retention.db_transaction", mock_transaction)
    monkeypatch.setattr("shopq.storage.retention.get_db_connection", lambda: test_db)

    # Run cleanup in dry run mode
    stats = cleanup_old_artifacts(days=14, dry_run=True)

    # Verify nothing was deleted (dry run)
    cursor = test_db.cursor()
    cursor.execute("SELECT COUNT(*) FROM email_threads")
    count = cursor.fetchone()[0]

    assert count == 2  # Both threads still exist
    assert stats["email_threads_deleted"] == 0  # Dry run doesn't delete


def test_cleanup_old_artifacts_actual_deletion(test_db, monkeypatch):
    """Test that cleanup actually deletes old data."""
    # Insert old and new threads
    now = datetime.now(UTC)
    old_date = (now - timedelta(days=20)).isoformat()
    new_date = (now - timedelta(days=5)).isoformat()

    cursor = test_db.cursor()
    cursor.execute(
        """
        INSERT INTO email_threads (thread_id, message_id, from_email, subject, timestamp, importance, user_id)
        VALUES
            ('thread1', 'msg1', 'old@example.com', 'Old email', ?, 'routine', 'alice'),
            ('thread2', 'msg2', 'new@example.com', 'New email', ?, 'critical', 'alice')
    """,
        (old_date, new_date),
    )
    test_db.commit()

    # Mock database connection
    def mock_transaction():
        class MockContext:
            def __enter__(self):
                return test_db

            def __exit__(self, *args):
                test_db.commit()

        return MockContext()

    monkeypatch.setattr("shopq.storage.retention.db_transaction", mock_transaction)
    monkeypatch.setattr("shopq.storage.retention.get_db_connection", lambda: test_db)

    # Run cleanup
    stats = cleanup_old_artifacts(days=14, dry_run=False)

    # Verify old thread was deleted
    cursor = test_db.cursor()
    cursor.execute("SELECT COUNT(*) FROM email_threads")
    count = cursor.fetchone()[0]

    assert count == 1  # Only new thread remains
    assert stats["email_threads_deleted"] == 1

    # Verify remaining thread is the new one
    cursor.execute("SELECT thread_id FROM email_threads")
    remaining_thread = cursor.fetchone()[0]
    assert remaining_thread == "thread2"


def test_get_retention_stats(test_db, monkeypatch):
    """Test retention statistics calculation."""
    # Insert mix of old and new data
    now = datetime.now(UTC)
    very_old = (now - timedelta(days=30)).isoformat()
    old_date = (now - timedelta(days=20)).isoformat()
    new_date = (now - timedelta(days=5)).isoformat()

    cursor = test_db.cursor()
    cursor.execute(
        """
        INSERT INTO email_threads (thread_id, message_id, from_email, subject, timestamp, importance, user_id)
        VALUES
            ('thread1', 'msg1', 'a@example.com', 'Very old', ?, 'routine', 'alice'),
            ('thread2', 'msg2', 'b@example.com', 'Old', ?, 'routine', 'alice'),
            ('thread3', 'msg3', 'c@example.com', 'New', ?, 'critical', 'alice')
    """,
        (very_old, old_date, new_date),
    )
    test_db.commit()

    # Mock connection
    monkeypatch.setattr("shopq.storage.retention.get_db_connection", lambda: test_db)

    stats = get_retention_stats()

    # Verify stats
    assert stats["total_email_threads"] == 3
    assert stats["threads_older_than_14_days"] == 2  # very_old + old_date
    assert stats["oldest_thread"] == very_old
    assert stats["newest_thread"] == new_date


def test_email_anonymization_pattern():
    """Test email anonymization pattern."""
    thread = {
        "from_email": "alice.smith@example.com",
        "subject": "Contact alice.smith@example.com for details",
    }

    result = anonymize_email_thread(thread, owner_user_id="alice", requesting_user_id="bob")

    # Email should be anonymized with hashed format
    assert result["from_email"].startswith("user_")
    assert "@domain_" in result["from_email"]
    assert "alice" not in result["from_email"]
    assert "example.com" not in result["from_email"]

    # Emails in subject should also be anonymized
    assert "alice.smith@example.com" not in result["subject"]
    assert "user_" in result["subject"]  # Hashed format
    assert "@domain_" in result["subject"]


def test_anonymization_edge_cases():
    """Test edge cases in anonymization."""
    thread = {
        "from_email": "",
        "subject": None,
        "message_id": "test",
    }

    result = anonymize_email_thread(thread, owner_user_id="alice", requesting_user_id="bob")

    # Should handle empty/None values gracefully
    assert result["from_email"] == "[REDACTED]"
    assert result["subject"] == "" or result["subject"] is None
    assert result["message_id"] == "[REDACTED]"
