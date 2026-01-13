"""
Migration: Add version tracking columns to confidence_logs table.

This migration adds model_name, model_version, and prompt_version columns
to the confidence_logs table to support version tracking.

Safe to run multiple times (uses ALTER TABLE IF NOT EXISTS pattern via try/except).
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from mailq.infrastructure.database import get_db_connection  # noqa: E402


def migrate():
    """Add version columns to confidence_logs table"""

    print("Starting migration: Add version columns to confidence_logs")

    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Check if columns already exist
        cursor.execute("PRAGMA table_info(confidence_logs)")
        existing_columns = {row[1] for row in cursor.fetchall()}

        columns_to_add = {
            "model_name": "TEXT",
            "model_version": "TEXT",
            "prompt_version": "TEXT",
        }

        added_count = 0
        for column_name, column_type in columns_to_add.items():
            if column_name not in existing_columns:
                # Validate column name to prevent SQL injection
                # Only allow alphanumeric and underscore
                if not column_name.replace("_", "").isalnum():
                    raise ValueError(f"Invalid column name: {column_name}")
                if column_type not in ["TEXT", "INTEGER", "REAL", "BLOB"]:
                    raise ValueError(f"Invalid column type: {column_type}")

                print(f"  Adding column: {column_name} {column_type}")
                # Note: Schema identifiers (table/column names) cannot use parameterized queries
                # but are validated above to prevent injection
                cursor.execute(f"""
                    ALTER TABLE confidence_logs
                    ADD COLUMN {column_name} {column_type}
                """)
                added_count += 1
            else:
                print(f"  Column {column_name} already exists, skipping")

        conn.commit()

    if added_count > 0:
        print(f"✓ Migration complete: Added {added_count} column(s)")
    else:
        print("✓ Migration complete: No changes needed (columns already exist)")

    return True


if __name__ == "__main__":
    try:
        migrate()
        sys.exit(0)
    except Exception as e:
        print(f"✗ Migration failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
