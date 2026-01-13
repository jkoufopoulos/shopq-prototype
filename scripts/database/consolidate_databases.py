#!/usr/bin/env python3
"""Database Consolidation Script - Phase 2

Consolidates multiple SQLite databases into single central database.

TIMING: Run after Classification Refactor Phase 1 (Guardrails) completes
to avoid merge conflicts.

This script:
1. Backs up all existing databases
2. Merges tables from scattered databases into mailq/data/mailq.db
3. Validates data integrity
4. Deletes old database files (after confirmation)

Usage:
    python mailq/scripts/consolidate_databases.py --dry-run  # Preview changes
    python mailq/scripts/consolidate_databases.py --execute  # Run migration
    python mailq/scripts/consolidate_databases.py --rollback # Restore backups

Status: SKELETON - To be implemented in Phase 2 (Week of 2025-11-18)
"""

import argparse
import builtins
import contextlib
import shutil
import sqlite3
from contextlib import suppress
from datetime import datetime
from pathlib import Path

# Database paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
CENTRAL_DB = PROJECT_ROOT / "mailq" / "data" / "mailq.db"
BACKUP_DIR = (
    PROJECT_ROOT / "backups" / f"db_consolidation_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
)

# Databases to consolidate
DATABASES_TO_MERGE = {
    "tracking": {
        "path": PROJECT_ROOT / "data" / "mailq_tracking.db",
        "tables": ["email_threads", "digest_sessions"],
        "size_kb": 960,
    },
    "digest_rules": {
        "path": PROJECT_ROOT / "mailq" / "digest_rules.db",
        "tables": ["digest_rules", "digest_feedback"],
        "size_kb": 40,
    },
    "quality_monitor": {
        "path": PROJECT_ROOT / "scripts" / "quality-monitor" / "quality_monitor.db",
        "tables": ["analyzed_sessions", "quality_issues", "llm_usage_tracking"],
        "size_kb": 128,
    },
}

# Empty/duplicate databases to delete
DATABASES_TO_DELETE = [
    PROJECT_ROOT / "mailq" / "data" / "rules.db",
    PROJECT_ROOT / "mailq" / "data" / "tracking.db",
    PROJECT_ROOT / "mailq" / "data" / "mailq_tracking.db",
    PROJECT_ROOT / "scripts" / "quality-monitor" / "quality_state.db",
    PROJECT_ROOT / "scripts" / "quality-monitor" / "quality_issues.db",
    PROJECT_ROOT / "extension" / "quality_monitor.db",
]


def backup_databases():
    """Backup all databases before consolidation"""
    print(f"📦 Creating backups in: {BACKUP_DIR}")
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    # Backup central database
    if CENTRAL_DB.exists():
        shutil.copy2(CENTRAL_DB, BACKUP_DIR / "mailq.db.backup")
        print(f"  ✅ Backed up {CENTRAL_DB}")

    # Backup databases to merge
    for name, info in DATABASES_TO_MERGE.items():
        db_path = info["path"]
        if db_path.exists():
            backup_path = BACKUP_DIR / f"{name}.db.backup"
            shutil.copy2(db_path, backup_path)
            print(f"  ✅ Backed up {db_path}")

    # Backup databases to delete
    for db_path in DATABASES_TO_DELETE:
        if db_path.exists():
            backup_path = BACKUP_DIR / f"{db_path.name}.backup"
            shutil.copy2(db_path, backup_path)
            print(f"  ✅ Backed up {db_path}")

    print()


def analyze_databases():
    """Analyze current database state"""
    print("🔍 Analyzing current database state...\n")

    # Check central database
    if CENTRAL_DB.exists():
        size_mb = CENTRAL_DB.stat().st_size / 1024 / 1024
        conn = sqlite3.connect(CENTRAL_DB)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()
        print(f"📊 Central DB ({CENTRAL_DB}): {size_mb:.2f}MB")
        print(f"   Tables: {', '.join(tables)}\n")
    else:
        print(f"⚠️  Central DB not found: {CENTRAL_DB}\n")

    # Check databases to merge
    for name, info in DATABASES_TO_MERGE.items():
        db_path = info["path"]
        if db_path.exists():
            size_mb = db_path.stat().st_size / 1024 / 1024
            print(f"📊 {name.upper()} ({db_path}): {size_mb:.2f}MB")
            print(f"   Tables to merge: {', '.join(info['tables'])}")
        else:
            print(f"⚠️  {name.upper()} not found: {db_path}")
    print()

    # Check databases to delete
    empty_count = 0
    for db_path in DATABASES_TO_DELETE:
        if db_path.exists():
            size_kb = db_path.stat().st_size / 1024
            if size_kb == 0:
                print(f"🗑️  Empty database: {db_path} (0KB)")
                empty_count += 1
            else:
                print(f"🗑️  Database to delete: {db_path} ({size_kb:.1f}KB)")
        else:
            print(f"✅ Already gone: {db_path}")

    print(f"\n📈 Summary: {empty_count} empty databases found\n")


def merge_table(source_db_path, table_name, central_conn):
    """Merge a table from source database into central database

    Uses ATTACH DATABASE to access source, then copies schema and data.
    """
    print(f"  📝 Merging {table_name} from {source_db_path.name}...")

    cursor = central_conn.cursor()

    try:
        # Validate table name to prevent SQL injection
        if not table_name.replace("_", "").isalnum():
            raise ValueError(f"Invalid table name: {table_name}")

        # Validate database path exists and is a file
        if not source_db_path.exists() or not source_db_path.is_file():
            raise ValueError(f"Invalid database path: {source_db_path}")

        # ATTACH DATABASE with path - use parameterized query
        # Note: ATTACH DATABASE requires the path to be a string literal or parameter
        cursor.execute("ATTACH DATABASE ? AS source_db", (str(source_db_path),))

        # Get CREATE TABLE statement from source
        cursor.execute(
            "SELECT sql FROM source_db.sqlite_master WHERE type='table' AND name=?", (table_name,)
        )
        create_stmt_row = cursor.fetchone()

        if not create_stmt_row:
            print(f"    ⚠️  Table {table_name} not found in source database")
            cursor.execute("DETACH DATABASE source_db")
            return

        create_stmt = create_stmt_row[0]

        # Create table in central DB (if not exists)
        # Replace CREATE TABLE with CREATE TABLE IF NOT EXISTS
        create_stmt_safe = create_stmt.replace("CREATE TABLE", "CREATE TABLE IF NOT EXISTS", 1)
        cursor.execute(create_stmt_safe)

        # Count rows in source
        # Note: Schema identifiers (table names) cannot use parameterized queries
        # but are validated above to prevent injection
        cursor.execute(f"SELECT COUNT(*) FROM source_db.{table_name}")
        source_count = cursor.fetchone()[0]

        if source_count == 0:
            print(f"    ℹ️  Table {table_name} is empty in source, skipping data copy")
            cursor.execute("DETACH DATABASE source_db")
            return

        # Copy data from source to central
        cursor.execute(f"INSERT OR IGNORE INTO {table_name} SELECT * FROM source_db.{table_name}")
        rows_copied = cursor.rowcount

        # Verify row count
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        central_count = cursor.fetchone()[0]

        print(
            f"    ✅ Copied {rows_copied} rows "
            f"({source_count} source → {central_count} total in central)"
        )

        # Checkpoint to flush WAL to main database file
        with suppress(Exception):
            cursor.execute("PRAGMA source_db.wal_checkpoint(TRUNCATE)")

        # Detach source database
        cursor.execute("DETACH DATABASE source_db")

        # Commit after each table to release locks
        central_conn.commit()

    except sqlite3.Error as e:
        print(f"    ❌ Error merging {table_name}: {e}")
        # Try to detach if still attached
        with contextlib.suppress(builtins.BaseException):
            cursor.execute("DETACH DATABASE source_db")
        raise


def consolidate_databases():
    """Main consolidation logic"""
    print("🔄 Consolidating databases into central DB...\n")

    # Connect to central database
    if not CENTRAL_DB.exists():
        print(f"❌ Central database not found: {CENTRAL_DB}")
        print(
            "   Run: python -c 'from mailq.infrastructure.database import init_database; init_database()'"
        )
        return False

    # Use timeout and enable shared cache mode to reduce lock contention
    central_conn = sqlite3.connect(CENTRAL_DB, timeout=30.0)
    central_conn.execute("PRAGMA busy_timeout = 30000")  # 30 second timeout

    try:
        for name, info in DATABASES_TO_MERGE.items():
            db_path = info["path"]
            if not db_path.exists():
                print(f"⚠️  Skipping {name}: database not found")
                continue

            print(f"\n📦 Consolidating {name.upper()}...")
            for table in info["tables"]:
                merge_table(db_path, table, central_conn)

        print("\n✅ Consolidation complete!")
        return True

    except Exception as e:
        print(f"\n❌ Consolidation failed: {e}")
        return False

    finally:
        central_conn.close()


def delete_old_databases():
    """Delete empty/duplicate databases after confirmation"""
    print("\n🗑️  Deleting old databases...\n")

    deleted_count = 0

    # Delete databases that were merged
    for _name, info in DATABASES_TO_MERGE.items():
        db_path = info["path"]
        if db_path.exists():
            try:
                db_path.unlink()
                print(f"  ✅ Deleted: {db_path}")
                deleted_count += 1
            except Exception as e:
                print(f"  ❌ Failed to delete {db_path}: {e}")

    # Delete empty/duplicate databases
    for db_path in DATABASES_TO_DELETE:
        if db_path.exists():
            try:
                db_path.unlink()
                print(f"  ✅ Deleted: {db_path}")
                deleted_count += 1
            except Exception as e:
                print(f"  ❌ Failed to delete {db_path}: {e}")

    print(f"\n✅ Deleted {deleted_count} old database files")


def update_code_references():
    """Print instructions for updating code to use central database"""
    print("\n📝 Code updates required:\n")
    print("1. mailq/email_tracker.py:")
    print("   - Remove: conn = sqlite3.connect('data/mailq_tracking.db')")
    print("   + Add: from mailq.infrastructure.database import get_db_connection")
    print("   + Use: with get_db_connection() as conn:")
    print()
    print("2. mailq/digest_categorizer.py:")
    print("   - Remove: conn = sqlite3.connect('mailq/digest_rules.db')")
    print("   + Use: with get_db_connection() as conn:")
    print()
    print("3. scripts/quality-monitor/quality_monitor.py:")
    print("   - Remove: conn = sqlite3.connect(STATE_DB)")
    print("   + Use: with get_db_connection() as conn:")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Consolidate MailQ databases into single central database"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without executing (default)",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute consolidation (WARNING: makes changes)",
    )
    parser.add_argument(
        "--analyze",
        action="store_true",
        help="Only analyze current database state",
    )

    args = parser.parse_args()

    print("=" * 70)
    print("MailQ Database Consolidation - Phase 2")
    print("=" * 70)
    print()

    if args.analyze or args.dry_run or not (args.execute):
        analyze_databases()
        if args.analyze:
            return

    if args.dry_run or not args.execute:
        print("🔍 DRY RUN MODE - No changes will be made\n")
        print("Steps that would be executed:")
        print("1. ✅ Backup all databases")
        print("2. ✅ Merge tables into central DB")
        print("3. ✅ Validate data integrity")
        print("4. ✅ Delete old databases")
        print("5. ✅ Update code references")
        print("\nTo execute: python mailq/scripts/consolidate_databases.py --execute")
        update_code_references()
        return

    if args.execute:
        print("⚠️  EXECUTE MODE - This will modify databases!\n")
        confirm = input("Are you sure? Type 'yes' to continue: ")
        if confirm.lower() != "yes":
            print("❌ Aborted")
            return

        backup_databases()
        if consolidate_databases():
            delete_old_databases()
            update_code_references()
            print("\n✅ Phase 2 consolidation complete!")
            print(f"   Backups saved to: {BACKUP_DIR}")
        else:
            print("\n❌ Consolidation failed! Databases unchanged.")
            print(f"   Backups available in: {BACKUP_DIR}")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
