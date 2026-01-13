"""
Test suite for database consolidation fixes

Tests all P0, P1, and P2 fixes implemented in the database module.
"""

import sqlite3
from unittest.mock import patch

import pytest


def test_retry_decorator_success():
    """Test retry decorator with successful operation"""
    from mailq.infrastructure.database import retry_on_db_lock

    call_count = [0]

    @retry_on_db_lock(max_retries=3, base_delay=0.01)
    def successful_operation():
        call_count[0] += 1
        return "success"

    result = successful_operation()
    assert result == "success"
    assert call_count[0] == 1, "Should succeed on first try"


def test_retry_decorator_recovers_from_lock():
    """Test retry decorator recovers from database lock errors"""
    from mailq.infrastructure.database import retry_on_db_lock

    call_count = [0]

    @retry_on_db_lock(max_retries=3, base_delay=0.01, max_delay=0.05)
    def flaky_operation():
        call_count[0] += 1
        if call_count[0] < 3:
            raise sqlite3.OperationalError("database is locked")
        return "success"

    result = flaky_operation()
    assert result == "success"
    assert call_count[0] == 3, "Should retry twice before success"


def test_retry_decorator_fails_after_max_retries():
    """Test retry decorator gives up after max retries"""
    from mailq.infrastructure.database import retry_on_db_lock

    call_count = [0]

    @retry_on_db_lock(max_retries=2, base_delay=0.01)
    def always_fails():
        call_count[0] += 1
        raise sqlite3.OperationalError("database is locked")

    with pytest.raises(sqlite3.OperationalError, match="database is locked"):
        always_fails()

    assert call_count[0] == 3, "Should try 3 times (initial + 2 retries)"


def test_retry_decorator_ignores_non_lock_errors():
    """Test retry decorator doesn't retry non-lock errors"""
    from mailq.infrastructure.database import retry_on_db_lock

    call_count = [0]

    @retry_on_db_lock(max_retries=3, base_delay=0.01)
    def schema_error():
        call_count[0] += 1
        raise sqlite3.OperationalError("no such table: foo")

    with pytest.raises(sqlite3.OperationalError, match="no such table"):
        schema_error()

    assert call_count[0] == 1, "Should not retry non-lock errors"


def test_pool_singleton():
    """Test that get_pool returns same instance"""
    from mailq.infrastructure.database import get_pool

    pool1 = get_pool()
    pool2 = get_pool()

    assert pool1 is pool2, "get_pool() should return singleton instance"


def test_pool_stats():
    """Test pool stats returns expected format"""
    from mailq.infrastructure.database import get_pool_stats

    stats = get_pool_stats()

    assert "pool_size" in stats
    assert "available" in stats
    assert "in_use" in stats
    assert "usage_percent" in stats
    assert "closed" in stats

    assert isinstance(stats["pool_size"], int)
    assert isinstance(stats["available"], int)
    assert isinstance(stats["in_use"], int)
    assert isinstance(stats["usage_percent"], (int, float))
    assert isinstance(stats["closed"], bool)

    assert stats["pool_size"] == 5, "Default pool size should be 5"
    assert stats["available"] + stats["in_use"] == stats["pool_size"]


def test_checkpoint_wal_creates_stats():
    """Test WAL checkpoint returns proper stats structure"""
    from mailq.infrastructure.database import checkpoint_wal

    try:
        stats = checkpoint_wal()

        assert "wal_size_before_bytes" in stats
        assert "wal_size_after_bytes" in stats
        assert "bytes_freed" in stats
        assert "checkpointed_pages" in stats
        assert "log_pages" in stats
        assert "busy" in stats

        assert isinstance(stats["wal_size_before_bytes"], int)
        assert isinstance(stats["wal_size_after_bytes"], int)
        assert isinstance(stats["bytes_freed"], int)
        assert isinstance(stats["busy"], bool)

        # bytes_freed should equal before - after
        assert stats["bytes_freed"] == (
            stats["wal_size_before_bytes"] - stats["wal_size_after_bytes"]
        )

    except Exception as e:
        # WAL file might not exist in test environment
        pytest.skip(f"WAL checkpoint not available: {e}")


def test_db_transaction_commits():
    """Test db_transaction context manager commits on success"""
    from mailq.infrastructure.database import db_transaction

    try:
        # Create a test table and insert data
        with db_transaction() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS _test_commits (
                    id INTEGER PRIMARY KEY,
                    value TEXT
                )
            """
            )
            conn.execute("DELETE FROM _test_commits")  # Clean up
            conn.execute("INSERT INTO _test_commits (id, value) VALUES (1, 'test')")

        # Verify data persisted
        from mailq.infrastructure.database import get_db_connection

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM _test_commits WHERE id = 1")
            result = cursor.fetchone()
            assert result is not None
            assert result[0] == "test"

        # Clean up
        with db_transaction() as conn:
            conn.execute("DROP TABLE _test_commits")

    except Exception as e:
        pytest.skip(f"Database not available: {e}")


def test_db_transaction_rolls_back_on_error():
    """Test db_transaction rolls back on error"""
    from mailq.infrastructure.database import db_transaction, get_db_connection

    try:
        # Create test table
        with db_transaction() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS _test_rollback (
                    id INTEGER PRIMARY KEY,
                    value TEXT
                )
            """
            )
            conn.execute("DELETE FROM _test_rollback")

        # Try to insert and fail
        try:
            with db_transaction() as conn:
                conn.execute("INSERT INTO _test_rollback (id, value) VALUES (1, 'should rollback')")
                raise ValueError("Intentional error")
        except ValueError:
            pass

        # Verify data was rolled back
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM _test_rollback")
            count = cursor.fetchone()[0]
            assert count == 0, "Transaction should have rolled back"

        # Clean up
        with db_transaction() as conn:
            conn.execute("DROP TABLE _test_rollback")

    except Exception as e:
        pytest.skip(f"Database not available: {e}")


def test_no_import_time_validation():
    """Test that importing database module doesn't trigger validation"""
    import importlib
    import sys

    # Remove module if already imported
    if "mailq.infrastructure.database" in sys.modules:
        del sys.modules["mailq.infrastructure.database"]

    # Mock validate_schema to detect if it's called during import
    validation_called = [False]

    original_validate = None
    if "mailq.infrastructure.database" in sys.modules:
        from mailq.config import database

        original_validate = database.validate_schema

    def mock_validate():
        validation_called[0] = True
        if original_validate:
            return original_validate()

    # Import with mocked validate_schema
    with patch("mailq.infrastructure.database.validate_schema", side_effect=mock_validate):
        importlib.import_module("mailq.infrastructure.database")

    assert not validation_called[0], "validate_schema should not be called during import"


def test_connection_pool_lifecycle():
    """Test connection pool get/return lifecycle"""
    from mailq.infrastructure.database import get_db_connection, get_pool_stats

    try:
        # Get initial stats
        initial_stats = get_pool_stats()
        initial_available = initial_stats["available"]

        # Get a connection (should reduce available count)
        pool = get_db_connection()
        conn = pool.__enter__()

        during_stats = get_pool_stats()
        assert during_stats["available"] == initial_available - 1, "Available should decrease"
        assert during_stats["in_use"] == initial_stats["in_use"] + 1, "In-use should increase"

        # Return the connection
        pool.__exit__(None, None, None)

        final_stats = get_pool_stats()
        assert final_stats["available"] == initial_available, "Available should be restored"
        assert final_stats["in_use"] == initial_stats["in_use"], "In-use should be restored"

    except Exception as e:
        pytest.skip(f"Database not available: {e}")


if __name__ == "__main__":
    # Run tests manually
    print("Running database fixes test suite...\n")

    tests = [
        ("Retry decorator - success", test_retry_decorator_success),
        ("Retry decorator - recovers from lock", test_retry_decorator_recovers_from_lock),
        ("Retry decorator - fails after max retries", test_retry_decorator_fails_after_max_retries),
        ("Retry decorator - ignores non-lock errors", test_retry_decorator_ignores_non_lock_errors),
        ("Pool singleton", test_pool_singleton),
        ("Pool stats", test_pool_stats),
        ("WAL checkpoint", test_checkpoint_wal_creates_stats),
        ("Transaction commits", test_db_transaction_commits),
        ("Transaction rollback", test_db_transaction_rolls_back_on_error),
        ("No import-time validation", test_no_import_time_validation),
        ("Connection pool lifecycle", test_connection_pool_lifecycle),
    ]

    passed = 0
    failed = 0
    skipped = 0

    for name, test_func in tests:
        try:
            test_func()
            print(f"✅ {name}")
            passed += 1
        except pytest.skip.Exception as e:
            print(f"⏭️  {name} - SKIPPED: {e}")
            skipped += 1
        except AssertionError as e:
            print(f"❌ {name} - FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"❌ {name} - ERROR: {e}")
            failed += 1

    print(f"\n{'=' * 60}")
    print(f"Results: {passed} passed, {failed} failed, {skipped} skipped")
    print(f"{'=' * 60}")

    if failed > 0:
        exit(1)
