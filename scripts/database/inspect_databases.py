"""

from __future__ import annotations

Inspect all databases and show their contents
"""

import sqlite3
from pathlib import Path

from mailq.observability.logging import get_logger

logger = get_logger(__name__)


def inspect_db(db_path):
    """Show tables and row counts for a database"""
    if not db_path.exists():
        return None

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]

    info = {
        "path": str(db_path),
        "size_kb": db_path.stat().st_size / 1024,
        "tables": {},
    }

    for table in tables:
        # Validate table name to prevent SQL injection
        # Table names come from sqlite_master, but validate to be safe
        if not table.replace("_", "").isalnum():
            logger.warning("Skipping table with invalid name: %s", table)
            continue

        # Note: Schema identifiers (table names) cannot use parameterized queries
        # but are validated above to prevent injection
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        count = cursor.fetchone()[0]

        # Get column names
        cursor.execute(f"PRAGMA table_info({table})")
        columns = [row[1] for row in cursor.fetchall()]

        # Get sample data
        if count > 0:
            cursor.execute(f"SELECT * FROM {table} LIMIT 3")
            sample = cursor.fetchall()
        else:
            sample = []

        info["tables"][table] = {"count": count, "columns": columns, "sample": sample}

    conn.close()
    return info


def main():
    # Check both possible locations
    project_root = Path(__file__).parent.parent.parent  # mailq-prototype/

    locations = [
        project_root / "data",  # mailq-prototype/data/
        project_root / "mailq" / "data",  # mailq-prototype/mailq/data/
    ]

    databases = ["feedback.db", "mailq.db", "mailq.sqlite", "rules.db", "rules.sqlite"]

    logger.info("🔍 Database Inspection Report")
    logger.info("=" * 80)

    for location in locations:
        logger.info("\n📂 Checking: %s", location)

        if not location.exists():
            logger.warning("   ❌ Directory does not exist")
            continue

        found_any = False

        for db_name in databases:
            db_path = location / db_name

            if not db_path.exists():
                continue

            found_any = True
            info = inspect_db(db_path)

            if info is None:
                logger.warning("   ⚠️  Could not inspect %s", db_path)
                continue

            logger.info("\n   📁 %s", db_name)
            logger.info("      Size: %.1f KB", info["size_kb"])
            logger.info("      Tables: %s", len(info["tables"]))

            for table_name, table_info in info["tables"].items():
                logger.info("\n      📊 Table: %s", table_name)
                logger.info("         Rows: %s", table_info["count"])
                logger.info(
                    "         Columns: %s",
                    ", ".join(table_info["columns"][:8]),
                )

                if table_info["count"] > 0 and table_info["sample"]:
                    logger.info("         Sample (first 3 rows):")
                    for i, row in enumerate(table_info["sample"][:3], 1):
                        row_preview = str(row)[:100] + "..." if len(str(row)) > 100 else str(row)
                        logger.info("            %s. %s", i, row_preview)

        if not found_any:
            logger.info("   ℹ️  No database files found")

    logger.info("\n%s", "=" * 80)
    logger.info("\n💡 Recommendation:")
    logger.info("   1. Consolidate all tables into ONE database (mailq.db)")
    logger.info("   2. Choose ONE location (recommend: mailq/data/)")
    logger.info("   3. Delete duplicate/empty databases")
    logger.info("   4. Update code to use single database path")


if __name__ == "__main__":
    main()
