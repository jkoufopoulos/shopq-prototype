"""Migration: Add pending_rules table to existing mailq.db"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from mailq.observability.logging import get_logger

logger = get_logger(__name__)


def migrate():
    """Add pending_rules table to existing mailq.db"""
    db_path = Path(__file__).parent.parent / "data" / "mailq.db"

    logger.info("Looking for database at: %s", db_path)

    if not db_path.exists():
        logger.error("mailq.db not found at expected location")
        logger.info("   Expected: %s", db_path)
        logger.info("   Creating new database...")
        # If no DB exists, just initialize it
        from mailq.infrastructure.database import init_database

        init_database()  # Uses centralized database configuration
        logger.info("New database created with pending_rules table")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if pending_rules exists
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='pending_rules'
    """)

    if cursor.fetchone():
        logger.info("pending_rules table already exists")

        cursor.execute("PRAGMA table_info(pending_rules)")
        columns = cursor.fetchall()
        logger.info("\n📊 Table structure:")
        for col in columns:
            logger.info("   %s (%s)", col[1], col[2])

        conn.close()
        return

    # Create pending_rules table
    logger.info("Creating pending_rules table...")
    cursor.execute("""
        CREATE TABLE pending_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            pattern_type TEXT NOT NULL,
            pattern TEXT NOT NULL,
            category TEXT NOT NULL,
            confidence INTEGER NOT NULL,
            seen_count INTEGER DEFAULT 1,
            last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, pattern_type, pattern, category)
        )
    """)

    cursor.execute("""
        CREATE INDEX idx_pending_rules_user_pattern
        ON pending_rules(user_id, pattern_type, pattern)
    """)

    conn.commit()

    # Verify it worked
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]

    conn.close()

    logger.info("✅ Migration complete!")
    logger.info("\n📊 Tables in database: %s", ", ".join(tables))


if __name__ == "__main__":
    migrate()
