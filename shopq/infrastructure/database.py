"""Centralized database configuration

**DATABASE POLICY**: ShopQ uses ONE SQLite database: shopq/data/shopq.db

All features MUST use this central database via get_db_connection().
Creating new .db files is FORBIDDEN without architectural review.

Provides:
- Connection pooling for performance (reuses connections)
- Single source of truth for database path (ONE database only)
- Connection management with proper settings
- Schema validation
- Test database support
- Enforcement of single-database architecture

Design Pattern: Singleton connection pool ensures all code uses the same database.
This prevents database proliferation and enables cross-domain queries.
"""

from __future__ import annotations

import atexit
import os
import random
import sqlite3
import time
from collections.abc import Callable, Generator
from contextlib import contextmanager
from functools import lru_cache, wraps
from pathlib import Path
from queue import Empty, Full, Queue
from threading import Lock
from typing import Any, TypeVar

from shopq.config import (
    DB_CONNECT_TIMEOUT,
    DB_POOL_SIZE,
    DB_POOL_TIMEOUT,
    DB_RETRY_BASE_DELAY,
    DB_RETRY_JITTER,
    DB_RETRY_MAX,
    DB_RETRY_MAX_DELAY,
    DB_TEMP_CONN_MAX,
)
from shopq.observability.logging import get_logger
from shopq.observability.telemetry import counter

F = TypeVar("F", bound=Callable[..., Any])

# Database path
DB_PATH = Path(__file__).parent.parent / "data" / "shopq.db"
TEST_DB_PATH = Path(__file__).parent.parent / "data" / "shopq_test.db"

logger = get_logger(__name__)


def retry_on_db_lock(
    max_retries: int = DB_RETRY_MAX,
    base_delay: float = DB_RETRY_BASE_DELAY,
    max_delay: float = DB_RETRY_MAX_DELAY,
) -> Callable[[F], F]:
    """
    Decorator to retry database operations on SQLITE_BUSY errors

    SQLite can return "database is locked" errors during concurrent access.
    This decorator implements exponential backoff with jitter to resolve
    transient lock contention.

    Args:
        max_retries: Maximum number of retry attempts (default: 5)
        base_delay: Initial delay in seconds (default: 0.1)
        max_delay: Maximum delay between retries (default: 2.0)

    Usage:
        @retry_on_db_lock()
        def my_database_operation():
            with db_transaction() as conn:
                conn.execute("INSERT INTO ...")

    Side Effects:
        - Retries wrapped function up to max_retries times on database lock errors
        - Sleeps between retries (exponential backoff with jitter)
        - Logs warning messages for each retry attempt
        - Logs error when retries exhausted
    """

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_error = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)

                except sqlite3.OperationalError as e:
                    last_error = e

                    # Only retry on lock errors
                    if "locked" not in str(e).lower() and "busy" not in str(e).lower():
                        raise

                    # Don't retry on last attempt
                    if attempt >= max_retries:
                        logger.error(
                            "Database lock retry exhausted after %d attempts: %s",
                            max_retries,
                            e,
                        )
                        raise

                    # Exponential backoff with jitter
                    delay = min(base_delay * (2**attempt), max_delay)
                    jitter = random.uniform(0, delay * DB_RETRY_JITTER)
                    sleep_time = delay + jitter

                    logger.warning(
                        "Database locked (attempt %d/%d), retrying in %.2fs: %s",
                        attempt + 1,
                        max_retries,
                        sleep_time,
                        e,
                    )

                    time.sleep(sleep_time)

            # This should never be reached, but satisfy type checker
            raise last_error  # type: ignore

        return wrapper  # type: ignore[return-value]

    return decorator


class DatabaseConnectionPool:
    """
    Thread-safe connection pool for SQLite

    Maintains a pool of reusable database connections for better performance.
    Connections are configured with optimal SQLite settings (WAL mode, etc.)
    """

    def __init__(self, db_path, pool_size=DB_POOL_SIZE):
        """
        Initialize connection pool

        Args:
            db_path: Path to SQLite database file
            pool_size: Number of connections to maintain in pool
        """
        self.db_path = db_path
        self.pool_size = pool_size
        self.pool = Queue(maxsize=pool_size)
        self.lock = Lock()
        self.closed = False
        self.temp_conn_count = 0
        self.temp_conn_max = DB_TEMP_CONN_MAX
        self._initialize_pool()

        # Register cleanup on program exit
        atexit.register(self.close_all)

    def _create_connection(self):
        """
        Create optimized SQLite connection

        Returns:
            sqlite3.Connection with optimal settings

        Side Effects:
            - Opens database connection to shopq.db
            - Executes PRAGMA statements (journal_mode, synchronous, foreign_keys)
            - Modifies connection row_factory

        Raises:
            RuntimeError: If database corruption is detected (CODE-010)
        """
        conn = sqlite3.connect(
            str(self.db_path),
            timeout=DB_CONNECT_TIMEOUT,
            check_same_thread=False,  # Allow use across threads
        )

        # CODE-010: Quick integrity check on new connections
        # quick_check is faster than integrity_check but catches most corruption
        try:
            result = conn.execute("PRAGMA quick_check(1)").fetchone()
            if result[0] != "ok":
                conn.close()
                logger.critical("Database corruption detected: %s", result[0])
                counter("database.corruption_detected")
                raise RuntimeError(f"Database corruption detected: {result[0]}")
        except sqlite3.DatabaseError as e:
            conn.close()
            logger.critical("Database corruption or error during integrity check: %s", e)
            counter("database.corruption_detected")
            raise RuntimeError(f"Database corruption detected: {e}") from e

        # Enable Write-Ahead Logging (much faster for concurrent access)
        conn.execute("PRAGMA journal_mode=WAL")

        # NORMAL synchronous mode (faster, still safe)
        conn.execute("PRAGMA synchronous=NORMAL")

        # Enable foreign keys (SQLite doesn't by default)
        conn.execute("PRAGMA foreign_keys=ON")

        # Return rows as dictionaries
        conn.row_factory = sqlite3.Row

        return conn

    def _initialize_pool(self):
        """
        Pre-create connections for the pool

        Side Effects:
            - Creates database connections to shopq.db
            - Adds connections to the pool queue
            - Writes log warnings if connection creation fails
        """
        for _ in range(self.pool_size):
            try:
                conn = self._create_connection()
                self.pool.put(conn)
            except Exception as e:
                logger.warning("Failed to create pooled connection: %s", e)

    def get_connection(self) -> sqlite3.Connection:
        """
        Get connection from pool

        Returns:
            sqlite3.Connection from pool (or new connection if pool exhausted)

        Raises:
            RuntimeError: If pool closed or temporary connection limit exceeded

        Side Effects:
            - Increments temp_conn_count if creating temporary connection
            - Logs error/critical messages if pool exhausted
            - Calls log_event telemetry for pool exhaustion monitoring
            - Creates new database connection if pool empty
        """
        if self.closed:
            raise RuntimeError("Connection pool has been closed")

        try:
            # Try to get from pool (wait up to DB_POOL_TIMEOUT seconds)
            return self.pool.get(block=True, timeout=DB_POOL_TIMEOUT)
        except Empty:
            # Pool exhausted - check if we can create temporary connection
            with self.lock:
                if self.temp_conn_count >= self.temp_conn_max:
                    logger.critical(
                        "Temporary connection limit reached: %d/%d. "
                        "This indicates a connection leak or insufficient pool size. "
                        "Current pool_size=%d.",
                        self.temp_conn_count,
                        self.temp_conn_max,
                        self.pool_size,
                    )
                    msg = (
                        "Database connection pool exhausted and temporary "
                        f"connection limit reached. pool_size={self.pool_size}, "
                        f"temp_conn_count={self.temp_conn_count}, "
                        f"temp_conn_max={self.temp_conn_max}. "
                        "This indicates a connection leak."
                    )
                    raise RuntimeError(msg) from None

                self.temp_conn_count += 1
                temp_count = self.temp_conn_count

            logger.error(
                "Connection pool exhausted (pool_size=%d). "
                "Creating temporary connection %d/%d. "
                "This indicates leaked connections or insufficient pool size.",
                self.pool_size,
                temp_count,
                self.temp_conn_max,
            )

            # Emit telemetry for monitoring/alerting
            try:
                from shopq.observability.telemetry import log_event

                log_event(
                    "database.pool_exhausted",
                    pool_size=self.pool_size,
                    temp_conn_count=temp_count,
                    severity="error",
                )
            except Exception as e:
                logger.warning("Failed to emit pool exhaustion telemetry: %s", e)

            conn = self._create_connection()
            conn._is_temporary = True  # Mark as temporary
            return conn

    def return_connection(self, conn: sqlite3.Connection) -> None:
        """
        Return connection to pool

        Args:
            conn: Connection to return (will be reused or closed)

        Side Effects:
            - Closes temporary connections and decrements temp_conn_count
            - Returns pooled connections to the pool for reuse
            - Modifies self.temp_conn_count counter (if temporary connection)
            - Writes log entries for closed temporary connections
        """
        # Check if this is a temporary connection
        is_temp = getattr(conn, "_is_temporary", False)

        if self.closed or is_temp:
            # Close temporary connections or if pool is closed
            conn.close()
            if is_temp:
                with self.lock:
                    self.temp_conn_count -= 1
                logger.debug("Closed temporary connection (remaining: %d)", self.temp_conn_count)
            return

        try:
            # Try to return pooled connection back to pool
            self.pool.put_nowait(conn)
        except Full:
            # Pool full (shouldn't happen) - close it
            logger.warning("Failed to return connection to pool (pool full), closing")
            conn.close()

    def close_all(self) -> None:
        """
        Close all pooled connections (cleanup)

        Side Effects:
            - Sets self.closed flag to True
            - Closes all database connections in pool
            - Empties the connection pool queue
        """
        self.closed = True
        while not self.pool.empty():
            try:
                conn = self.pool.get_nowait()
                conn.close()
            except Empty:
                break


@lru_cache(maxsize=1)
def get_pool() -> DatabaseConnectionPool:
    """
    Get or create global connection pool

    Thread-safe singleton pattern using @lru_cache.

    @lru_cache provides proper thread-safe memoization with memory barriers,
    fixing the double-checked locking race condition in the previous implementation.

    Returns:
        DatabaseConnectionPool instance

    Side Effects:
        - Creates DatabaseConnectionPool instance on first call (singleton)
        - Initializes database connection pool (opens connections to shopq.db)
        - Registers atexit cleanup handler
    """
    db_path = get_db_path()
    return DatabaseConnectionPool(db_path, pool_size=DB_POOL_SIZE)


def get_db_path() -> Path:
    """
    Get database path (environment-aware)

    Checks SHOPQ_DB_PATH environment variable first,
    falls back to default location.
    """
    if env_path := os.getenv("SHOPQ_DB_PATH"):
        return Path(env_path)

    return DB_PATH


@contextmanager
def get_db_connection() -> Generator[sqlite3.Connection, None, None]:
    """
    Get pooled database connection (context manager)

    Usage:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM rules")
            results = cursor.fetchall()
        # Connection automatically returned to pool

    Yields:
        sqlite3.Connection from pool with Row factory enabled

    Raises:
        FileNotFoundError: If database doesn't exist
    """
    db_path = get_db_path()

    if not db_path.exists():
        raise FileNotFoundError(
            f"Database not found: {db_path}\nRun: python shopq/scripts/consolidate_databases.py"
        )

    pool = get_pool()
    conn = pool.get_connection()
    try:
        yield conn
    finally:
        pool.return_connection(conn)


@contextmanager
def db_transaction() -> Generator[sqlite3.Connection, None, None]:
    """
    Context manager for database transactions

    Automatically commits on success, rolls back on error.

    Usage:
        with db_transaction() as conn:
            conn.execute("INSERT INTO rules ...")
            conn.execute("UPDATE categories ...")
        # Auto-commits on success, rolls back on error

    Side Effects:
        - Commits transaction to shopq.db on success (writes changes to disk)
        - Rolls back transaction on exception (discards uncommitted changes)
        - Acquires database connection from pool
    """
    with get_db_connection() as conn:
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e


def execute_query(
    query: str,
    params: tuple[Any, ...] | dict[str, Any] | None = None,
    fetch: str = "all",
) -> list[sqlite3.Row] | sqlite3.Row | None:
    """
    Execute a query and return results (uses connection pool)

    Args:
        query: SQL query string
        params: Query parameters (tuple or dict)
        fetch: 'all', 'one', or 'none'

    Returns:
        Query results (list of Rows, single Row, or None)

    Side Effects:
        - Executes SQL query on shopq.db
        - Commits transaction if fetch='none' (write queries)
        - May modify database tables (INSERT, UPDATE, DELETE)
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()

        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)

        if fetch == "all":
            return cursor.fetchall()
        if fetch == "one":
            return cursor.fetchone()
        conn.commit()  # Commit if it's a write query
        return None


def validate_schema() -> bool:
    """
    Validate database has expected schema

    Returns:
        True if valid

    Raises:
        ValueError: If tables are missing
    """
    from shopq.infrastructure.database_schema import validate_schema as _validate_schema

    with get_db_connection() as conn:
        return _validate_schema(conn)


def get_pool_stats() -> dict[str, Any]:
    """
    Get connection pool health metrics

    Returns:
        dict with pool size, available connections, and usage stats
    """
    pool = get_pool()
    available = pool.pool.qsize()
    in_use = pool.pool_size - available
    usage_percent = (in_use / pool.pool_size) * 100 if pool.pool_size > 0 else 0

    return {
        "pool_size": pool.pool_size,
        "available": available,
        "in_use": in_use,
        "usage_percent": round(usage_percent, 1),
        "closed": pool.closed,
    }


def checkpoint_wal() -> dict[str, Any]:
    """
    Manually checkpoint the WAL file to prevent unbounded growth

    In Cloud Run, WAL files can grow unbounded if not checkpointed regularly.
    This function forces a checkpoint to merge WAL into main database.

    Should be called periodically (e.g., every 5 minutes) or after bulk writes.

    Side Effects:
    - Writes WAL frames to main database file (shopq.db)
    - Truncates WAL file (shopq.db-wal) to zero bytes
    - Blocks other writers briefly during checkpoint
    - Logs checkpoint statistics

    Returns:
        dict with checkpoint statistics (pages checkpointed, wal size before/after)
    """
    db_path = get_db_path()

    # Get WAL size before checkpoint
    wal_path = db_path.with_suffix(".db-wal")
    wal_size_before = wal_path.stat().st_size if wal_path.exists() else 0

    with get_db_connection() as conn:
        cursor = conn.cursor()

        # PRAGMA wal_checkpoint(TRUNCATE) does:
        # 1. Checkpoint all WAL frames to database
        # 2. Truncate WAL file to zero bytes
        # Returns: (busy, log, checkpointed)
        cursor.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        result = cursor.fetchone()

        busy, log_pages, checkpointed_pages = result if result else (0, 0, 0)

    # Get WAL size after checkpoint
    wal_size_after = wal_path.stat().st_size if wal_path.exists() else 0

    stats = {
        "wal_size_before_bytes": wal_size_before,
        "wal_size_after_bytes": wal_size_after,
        "bytes_freed": wal_size_before - wal_size_after,
        "checkpointed_pages": checkpointed_pages,
        "log_pages": log_pages,
        "busy": bool(busy),
    }

    logger.info(
        "WAL checkpoint completed: freed %d bytes (%d pages)",
        stats["bytes_freed"],
        checkpointed_pages,
    )

    return stats


def get_test_db_connection() -> sqlite3.Connection:
    """
    Get connection to test database (isolated from production)

    Useful for unit tests - creates a separate database.

    Side Effects:
        - Opens connection to shopq_test.db (creates file if doesn't exist)
        - Executes PRAGMA foreign_keys = ON
        - Modifies connection row_factory
    """
    conn = sqlite3.connect(TEST_DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_database() -> None:
    """
    Initialize database with schema (idempotent)

    Safe to run multiple times - uses CREATE TABLE IF NOT EXISTS.

    Side Effects:
    - Creates tables in shopq.db if they don't exist
    - Creates indexes for query performance
    - Creates shopq/data/ directory if needed
    - Idempotent: safe to run multiple times
    """
    from shopq.infrastructure.database_schema import init_database as _init_database

    db_path = get_db_path()
    _init_database(db_path)


# Note: Schema validation now happens at application startup
# See @app.on_event("startup") in shopq/api.py
# This prevents import-time side effects and provides better error handling
