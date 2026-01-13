"""
Tests for tenancy enforcement utilities.

This module verifies that the tenancy enforcement mechanisms properly prevent
cross-tenant data leakage through decorator validation and SQL query checks.
"""

import sqlite3

import pytest

from mailq.storage.tenancy import TenancyViolationError, enforce_tenancy, require_user_scope

# Test Decorator Validation


def test_enforce_tenancy_missing_user_id_parameter():
    """Test that decorator raises error when function lacks user_id parameter."""

    @enforce_tenancy
    def query_without_user_id(session_id: str):
        return f"session: {session_id}"

    with pytest.raises(TenancyViolationError) as exc_info:
        query_without_user_id("session123")

    assert "user_id" in str(exc_info.value)


def test_enforce_tenancy_none_user_id():
    """Test that decorator raises error when user_id is None."""

    @enforce_tenancy
    def query_with_none_user_id(user_id: str, session_id: str):
        return f"user: {user_id}, session: {session_id}"

    with pytest.raises(TenancyViolationError) as exc_info:
        query_with_none_user_id(None, "session123")

    assert "received None for user_id" in str(exc_info.value)


def test_enforce_tenancy_empty_user_id():
    """Test that decorator raises error when user_id is empty string."""

    @enforce_tenancy
    def query_with_empty_user_id(user_id: str, session_id: str):
        return f"user: {user_id}, session: {session_id}"

    # Test empty string
    with pytest.raises(TenancyViolationError) as exc_info:
        query_with_empty_user_id("", "session123")

    assert "must be non-empty string" in str(exc_info.value)

    # Test whitespace-only string
    with pytest.raises(TenancyViolationError) as exc_info:
        query_with_empty_user_id("   ", "session123")

    assert "must be non-empty string" in str(exc_info.value)


def test_enforce_tenancy_invalid_user_id_type():
    """Test that decorator raises error when user_id is not a string."""

    @enforce_tenancy
    def query_with_invalid_type(user_id: str, session_id: str):
        return f"user: {user_id}, session: {session_id}"

    # Test with integer
    with pytest.raises(TenancyViolationError) as exc_info:
        query_with_invalid_type(123, "session123")

    assert "must be non-empty string" in str(exc_info.value)

    # Test with list
    with pytest.raises(TenancyViolationError) as exc_info:
        query_with_invalid_type(["user1"], "session123")

    assert "must be non-empty string" in str(exc_info.value)


def test_enforce_tenancy_valid_user_id():
    """Test that decorator allows valid user_id through."""

    @enforce_tenancy
    def query_with_valid_user_id(user_id: str, session_id: str):
        return f"user: {user_id}, session: {session_id}"

    # Should not raise any exception
    result = query_with_valid_user_id("user123", "session456")
    assert result == "user: user123, session: session456"


def test_enforce_tenancy_with_kwargs():
    """Test that decorator works with keyword arguments."""

    @enforce_tenancy
    def query_with_kwargs(user_id: str, session_id: str = "default"):
        return f"user: {user_id}, session: {session_id}"

    # Positional arguments
    result = query_with_kwargs("user123", "session456")
    assert result == "user: user123, session: session456"

    # Keyword arguments
    result = query_with_kwargs(user_id="user123", session_id="session456")
    assert result == "user: user123, session: session456"

    # Mixed
    result = query_with_kwargs("user123", session_id="session456")
    assert result == "user: user123, session: session456"

    # With default
    result = query_with_kwargs(user_id="user123")
    assert result == "user: user123, session: default"


# Test SQL Query Validation


def test_require_user_scope_valid_select_query():
    """Test that valid SELECT queries with user_id filtering pass."""
    query = "SELECT * FROM email_threads WHERE user_id = ? AND session_id = ?"

    # Should not raise any exception
    require_user_scope(query, "user123")


def test_require_user_scope_valid_join_query():
    """Test that JOIN queries with user_id filtering pass."""
    query = """
        SELECT e.*, d.digest_html
        FROM email_threads e
        JOIN digest_sessions d ON e.session_id = d.session_id
        WHERE e.user_id = ? AND d.user_id = ?
    """

    # Should not raise any exception
    require_user_scope(query, "user123")


def test_require_user_scope_valid_insert_query():
    """Test that INSERT queries with user_id pass."""
    query = "INSERT INTO email_threads (user_id, session_id, thread_id) VALUES (?, ?, ?)"

    # Should not raise any exception
    require_user_scope(query, "user123")


def test_require_user_scope_valid_update_query():
    """Test that UPDATE queries with user_id pass."""
    query = "UPDATE email_threads SET processed = 1 WHERE user_id = ? AND session_id = ?"

    # Should not raise any exception
    require_user_scope(query, "user123")


def test_require_user_scope_missing_user_id():
    """Test that queries without user_id are rejected."""
    query = "SELECT * FROM email_threads WHERE session_id = ?"

    with pytest.raises(TenancyViolationError) as exc_info:
        require_user_scope(query, "user123")

    assert "must include user_id filtering" in str(exc_info.value)


def test_require_user_scope_select_without_where():
    """Test that SELECT queries without WHERE clauses are rejected."""
    query = "SELECT * FROM email_threads"

    with pytest.raises(TenancyViolationError) as exc_info:
        require_user_scope(query, "user123")

    assert "user_id" in str(exc_info.value)


def test_require_user_scope_case_insensitive():
    """Test that SQL validation is case-insensitive."""
    query = "SELECT * FROM email_threads WHERE USER_ID = ? AND SESSION_ID = ?"

    # Should not raise any exception (user_id in uppercase)
    require_user_scope(query, "user123")


# Test Cross-Tenant Isolation (Integration Tests)


@pytest.fixture
def test_db():
    """Create a temporary test database with sample data."""
    conn = sqlite3.connect(":memory:")
    cursor = conn.cursor()

    # Create test table
    cursor.execute("""
        CREATE TABLE email_threads (
            id INTEGER PRIMARY KEY,
            user_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            thread_id TEXT NOT NULL,
            subject TEXT
        )
    """)

    # Insert test data for two users
    cursor.execute("""
        INSERT INTO email_threads (user_id, session_id, thread_id, subject)
        VALUES
            ('user_a', 'session1', 'thread1', 'User A Email 1'),
            ('user_a', 'session1', 'thread2', 'User A Email 2'),
            ('user_b', 'session2', 'thread3', 'User B Email 1'),
            ('user_b', 'session2', 'thread4', 'User B Email 2')
    """)

    conn.commit()
    yield conn
    conn.close()


def test_cross_tenant_isolation_select(test_db):
    """Test that user A cannot access user B's data."""

    @enforce_tenancy
    def get_user_threads(user_id: str, conn):
        query = "SELECT * FROM email_threads WHERE user_id = ?"
        require_user_scope(query, user_id)
        cursor = conn.cursor()
        cursor.execute(query, (user_id,))
        return cursor.fetchall()

    # User A should only see their own threads
    user_a_threads = get_user_threads("user_a", test_db)
    assert len(user_a_threads) == 2
    assert all(thread[1] == "user_a" for thread in user_a_threads)

    # User B should only see their own threads
    user_b_threads = get_user_threads("user_b", test_db)
    assert len(user_b_threads) == 2
    assert all(thread[1] == "user_b" for thread in user_b_threads)

    # Verify no overlap
    user_a_thread_ids = {thread[3] for thread in user_a_threads}
    user_b_thread_ids = {thread[3] for thread in user_b_threads}
    assert user_a_thread_ids.isdisjoint(user_b_thread_ids)


def test_cross_tenant_isolation_no_where_clause_blocked(test_db):
    """Test that queries without WHERE clause are blocked by require_user_scope."""

    @enforce_tenancy
    def get_all_threads_unsafe(user_id: str, conn):
        # This query doesn't filter by user_id in WHERE clause
        query = "SELECT * FROM email_threads"
        require_user_scope(query, user_id)
        cursor = conn.cursor()
        cursor.execute(query)
        return cursor.fetchall()

    # Should raise TenancyViolationError
    with pytest.raises(TenancyViolationError) as exc_info:
        get_all_threads_unsafe("user_a", test_db)

    assert "user_id" in str(exc_info.value)


def test_cross_tenant_isolation_wrong_user_id_in_query(test_db):
    """Test scenario where function receives user_id but query uses different user_id."""

    @enforce_tenancy
    def get_threads_with_hardcoded_user(user_id: str, conn):
        # Decorator validates user_id parameter is provided
        # But this is a code smell - query should use the parameter
        query = "SELECT * FROM email_threads WHERE user_id = ?"
        require_user_scope(query, user_id)
        cursor = conn.cursor()
        # Developer mistake: using hardcoded 'user_b' instead of parameter
        cursor.execute(query, ("user_b",))
        return cursor.fetchall()

    # Decorator passes (user_id parameter is valid)
    # SQL validator passes (query has WHERE user_id = ?)
    # But the actual query execution uses wrong user_id
    # This test demonstrates the limitation: we can't catch runtime parameter substitution
    result = get_threads_with_hardcoded_user("user_a", test_db)

    # This will return user_b's data even though function was called with user_a
    # This is a known limitation - the guards validate structure, not runtime values
    assert len(result) == 2
    assert all(thread[1] == "user_b" for thread in result)


def test_decorator_preserves_function_metadata():
    """Test that @enforce_tenancy preserves function name and docstring."""

    @enforce_tenancy
    def my_query_function(user_id: str, session_id: str):
        """This is my query function docstring."""
        return f"user: {user_id}, session: {session_id}"

    assert my_query_function.__name__ == "my_query_function"
    assert my_query_function.__doc__ == "This is my query function docstring."


def test_require_user_scope_with_subqueries():
    """Test that subqueries with user_id filtering pass."""
    query = """
        SELECT * FROM email_threads
        WHERE user_id = ?
        AND session_id IN (
            SELECT session_id FROM digest_sessions
            WHERE user_id = ? AND status = 'completed'
        )
    """

    # Should not raise any exception
    require_user_scope(query, "user123")


def test_require_user_scope_delete_query():
    """Test that DELETE queries with user_id filtering pass."""
    query = "DELETE FROM email_threads WHERE user_id = ? AND session_id = ?"

    # Should not raise any exception
    require_user_scope(query, "user123")
