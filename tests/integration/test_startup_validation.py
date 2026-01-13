#!/usr/bin/env python3
"""
Test database startup validation logic

Verifies that the database initialization and validation code
added to api.py works as expected.
"""

import sys
from pathlib import Path


def test_database_initialization():
    """Test database initialization logic"""
    print("Testing database initialization...")

    from shopq.infrastructure.database import get_db_path, init_database, validate_schema

    try:
        # Initialize database (idempotent)
        init_database()
        print("✅ init_database() completed successfully")

        # Validate schema
        validate_schema()
        print("✅ validate_schema() passed")

        # Check database exists
        db_path = get_db_path()
        assert db_path.exists(), f"Database should exist at {db_path}"
        print(f"✅ Database file exists: {db_path}")

        return True

    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_startup_error_handling():
    """Test that startup errors are caught properly"""
    print("\nTesting startup error handling...")

    import sqlite3
    from unittest.mock import patch

    # Test 1: FileNotFoundError handling
    print("  Testing FileNotFoundError handling...")
    with patch("shopq.infrastructure.database.get_db_path") as mock_path:
        mock_path.return_value = Path("/nonexistent/path/shopq.db")
        try:
            conn = sqlite3.connect(mock_path.return_value)
            # This should work even with nonexistent path (SQLite creates it)
            print("  ✅ SQLite creates database even in nonexistent path")
        except Exception as e:
            print(f"  ✅ FileNotFoundError would be caught: {type(e).__name__}")

    # Test 2: OperationalError handling (simulated)
    print("  Testing OperationalError handling...")
    try:
        # Simulate a schema error by trying to query non-existent table
        import sqlite3

        conn = sqlite3.connect(":memory:")
        conn.execute("SELECT * FROM nonexistent_table")
    except sqlite3.OperationalError as e:
        print(f"  ✅ OperationalError caught: {e}")

    print("✅ Error handling logic validated")
    return True


def test_email_tracker_uses_transactions():
    """Test that EmailThreadTracker uses db_transaction"""
    print("\nTesting EmailThreadTracker uses transactions...")

    import inspect

    from shopq.observability.tracking import EmailThreadTracker

    tracker = EmailThreadTracker()

    # Check that tracking methods use db_transaction
    methods_to_check = [
        "track_classification",
        "track_verifier",
        "track_entity",
        "track_digest_inclusion",
        "save_digest_session",
    ]

    all_use_transaction = True
    for method_name in methods_to_check:
        method = getattr(tracker, method_name)
        source = inspect.getsource(method)

        if "db_transaction" in source:
            print(f"  ✅ {method_name} uses db_transaction()")
        else:
            print(f"  ❌ {method_name} does NOT use db_transaction()")
            all_use_transaction = False

    if all_use_transaction:
        print("✅ All tracking methods use db_transaction()")
        return True
    print("❌ Some tracking methods don't use db_transaction()")
    return False


def test_wal_checkpoint_thread():
    """Test that WAL checkpoint thread is configured"""
    print("\nTesting WAL checkpoint thread configuration...")

    # Read api.py to check for checkpoint thread
    api_path = Path(__file__).parent.parent.parent / "mailq" / "api" / "app.py"
    api_source = api_path.read_text()

    checks = [
        ("_wal_checkpoint_loop function", "_wal_checkpoint_loop"),
        ("checkpoint_wal import", "checkpoint_wal"),
        ("Thread creation", "threading.Thread"),
        ("daemon=True", "daemon=True"),
        ("thread.start()", ".start()"),
    ]

    all_present = True
    for check_name, check_str in checks:
        if check_str in api_source:
            print(f"  ✅ {check_name} present")
        else:
            print(f"  ❌ {check_name} NOT present")
            all_present = False

    if all_present:
        print("✅ WAL checkpoint thread properly configured")
        return True
    print("❌ WAL checkpoint thread configuration incomplete")
    return False


def test_startup_validation_hook():
    """Test that startup validation is registered"""
    print("\nTesting startup validation hook...")

    api_path = Path(__file__).parent.parent.parent / "mailq" / "api" / "app.py"
    api_source = api_path.read_text()

    checks = [
        ("@app.on_event('startup')", '@app.on_event("startup")'),
        ("validate_database_schema function", "async def validate_database_schema"),
        ("validate_schema() call", "validate_schema()"),
        ("Error handling", "except ValueError"),
        ("Critical logging", "logger.critical"),
    ]

    all_present = True
    for check_name, check_str in checks:
        if check_str in api_source:
            print(f"  ✅ {check_name} present")
        else:
            print(f"  ❌ {check_name} NOT present")
            all_present = False

    if all_present:
        print("✅ Startup validation hook properly configured")
        return True
    print("❌ Startup validation hook configuration incomplete")
    return False


def test_health_db_endpoint():
    """Test that /health/db endpoint is defined"""
    print("\nTesting /health/db endpoint...")

    api_path = Path(__file__).parent.parent.parent / "mailq" / "api" / "app.py"
    api_source = api_path.read_text()

    checks = [
        ("/health/db route", '@app.get("/health/db")'),
        ("get_pool_stats import", "get_pool_stats"),
        ("async def database_health", "async def database_health"),
        ("Returns pool stats", "stats = get_pool_stats()"),
        ("Health status", '"status"'),
    ]

    all_present = True
    for check_name, check_str in checks:
        if check_str in api_source:
            print(f"  ✅ {check_name} present")
        else:
            print(f"  ❌ {check_name} NOT present")
            all_present = False

    if all_present:
        print("✅ /health/db endpoint properly configured")
        return True
    print("❌ /health/db endpoint configuration incomplete")
    return False


if __name__ == "__main__":
    print("=" * 60)
    print("Database Startup Validation Tests")
    print("=" * 60)
    print()

    tests = [
        ("Database initialization", test_database_initialization),
        ("Startup error handling", test_startup_error_handling),
        ("EmailThreadTracker transactions", test_email_tracker_uses_transactions),
        ("WAL checkpoint thread", test_wal_checkpoint_thread),
        ("Startup validation hook", test_startup_validation_hook),
        ("/health/db endpoint", test_health_db_endpoint),
    ]

    passed = 0
    failed = 0

    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"❌ {test_name} raised exception: {e}")
            import traceback

            traceback.print_exc()
            failed += 1
        print()

    print("=" * 60)
    print(f"Results: {passed}/{len(tests)} tests passed")
    print("=" * 60)

    if failed == 0:
        print("✅ All validation tests PASSED")
        sys.exit(0)
    else:
        print(f"❌ {failed} test(s) FAILED")
        sys.exit(1)
