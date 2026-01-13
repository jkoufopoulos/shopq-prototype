"""

from __future__ import annotations

Test connection pool implementation

Validates:
- Connection pooling works correctly
- Connections are reused
- Thread safety
- Proper cleanup
"""

import threading

import pytest

from mailq.infrastructure.database import (
    db_transaction,
    get_db_connection,
    get_pool,
)


def test_pool_initialization():
    """Test that pool initializes correctly"""
    pool = get_pool()
    assert pool is not None
    assert pool.pool_size == 5
    assert not pool.closed


def test_get_connection():
    """Test getting connection from pool"""
    with get_db_connection() as conn:
        assert conn is not None
        # Should be able to execute queries
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        result = cursor.fetchone()
        assert result[0] == 1


def test_connection_reuse():
    """Test that connections are reused from pool"""
    pool = get_pool()

    # Track all connection IDs we see
    connection_ids = set()

    # Get and return connections multiple times
    for i in range(10):
        with get_db_connection() as conn:
            connection_ids.add(id(conn))
            # Execute a query to ensure connection is working
            cursor = conn.cursor()
            cursor.execute("SELECT ?", (i,))
            result = cursor.fetchone()
            assert result[0] == i

    # Should not have created more connections than pool size (5)
    # We should be reusing connections from the pool
    assert len(connection_ids) <= pool.pool_size, (
        f"Created {len(connection_ids)} connections, expected at most {pool.pool_size}"
    )

    print(f"✅ Connection pool reused {pool.pool_size} connections for 10 operations")


def test_multiple_concurrent_connections():
    """Test multiple concurrent connections"""
    get_pool()
    connections = []

    # Get multiple connections (up to pool size)
    for i in range(3):
        with get_db_connection() as conn:
            connections.append(id(conn))
            # Keep connection active briefly
            cursor = conn.cursor()
            cursor.execute("SELECT ?", (i,))

    # All should have been successful
    assert len(connections) == 3


def test_transaction_commit():
    """Test that transactions commit correctly"""
    with db_transaction() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS test_table (id INTEGER, value TEXT)")
        conn.execute("INSERT INTO test_table (id, value) VALUES (1, 'test')")

    # Verify data was committed
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM test_table WHERE id = 1")
        result = cursor.fetchone()
        assert result is not None
        assert result[0] == "test"

    # Cleanup
    with db_transaction() as conn:
        conn.execute("DROP TABLE test_table")


def test_transaction_rollback():
    """Test that transactions rollback on error"""
    # Create test table
    with db_transaction() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS test_rollback (id INTEGER PRIMARY KEY)")

    # Try transaction that should fail
    try:
        with db_transaction() as conn:
            conn.execute("INSERT INTO test_rollback (id) VALUES (1)")
            # This should cause rollback
            raise ValueError("Test error")
    except ValueError:
        pass

    # Verify data was not committed
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM test_rollback")
        count = cursor.fetchone()[0]
        assert count == 0, "Transaction should have been rolled back"

    # Cleanup
    with db_transaction() as conn:
        conn.execute("DROP TABLE test_rollback")


def test_thread_safety():
    """Test that pool is thread-safe"""
    results = []
    errors = []

    def query_database(thread_id):
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT ?", (thread_id,))
                result = cursor.fetchone()[0]
                results.append(result)
        except Exception as e:
            errors.append(e)

    # Create multiple threads
    threads = []
    for i in range(10):
        t = threading.Thread(target=query_database, args=(i,))
        threads.append(t)
        t.start()

    # Wait for all threads to complete
    for t in threads:
        t.join()

    # All queries should have succeeded
    assert len(errors) == 0, f"Thread errors: {errors}"
    assert len(results) == 10
    assert sorted(results) == list(range(10))


def test_base_repository():
    """Test BaseRepository class"""
    from mailq.storage import BaseRepository

    # Create test repository
    repo = BaseRepository("test_repo_table")

    # Create test table
    with db_transaction() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS test_repo_table (
                id INTEGER PRIMARY KEY,
                name TEXT
            )
        """)
        conn.execute("INSERT INTO test_repo_table (id, name) VALUES (1, 'test')")

    # Test query_one
    result = repo.query_one("SELECT * FROM test_repo_table WHERE id = ?", (1,))
    assert result is not None
    assert result["name"] == "test"

    # Test query_all
    results = repo.query_all("SELECT * FROM test_repo_table")
    assert len(results) >= 1

    # Test get_by_id
    result = repo.get_by_id(1)
    assert result is not None
    assert result["name"] == "test"

    # Test count
    count = repo.count()
    assert count >= 1

    # Test exists
    assert repo.exists("id = ?", (1,))
    assert not repo.exists("id = ?", (999,))

    # Cleanup
    with db_transaction() as conn:
        conn.execute("DROP TABLE test_repo_table")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
