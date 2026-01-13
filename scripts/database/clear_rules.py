#!/usr/bin/env python3
"""
Clear all rules and corrections from the database.
Creates a backup before clearing.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from shopq.observability.logging import get_logger

# Database path
DB_PATH = Path(__file__).parent.parent / "data" / "shopq.db"
BACKUP_DIR = Path(__file__).parent.parent / "data" / "backups"
logger = get_logger(__name__)


def backup_rules(conn):
    """Backup rules to JSON file"""
    cursor = conn.cursor()

    # Create backup directory
    BACKUP_DIR.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = BACKUP_DIR / f"rules_backup_{timestamp}.json"

    # Fetch all data
    backup_data = {
        "timestamp": timestamp,
        "rules": [],
        "pending_rules": [],
        "corrections": [],
        "feedback": [],
    }

    # Backup rules
    cursor.execute("SELECT * FROM rules")
    columns = [desc[0] for desc in cursor.description]
    for row in cursor.fetchall():
        backup_data["rules"].append(dict(zip(columns, row, strict=False)))

    # Backup pending_rules
    cursor.execute("SELECT * FROM pending_rules")
    columns = [desc[0] for desc in cursor.description]
    for row in cursor.fetchall():
        backup_data["pending_rules"].append(dict(zip(columns, row, strict=False)))

    # Backup corrections
    try:
        cursor.execute("SELECT * FROM corrections")
        columns = [desc[0] for desc in cursor.description]
        for row in cursor.fetchall():
            backup_data["corrections"].append(dict(zip(columns, row, strict=False)))
    except sqlite3.OperationalError:
        pass  # Table might be empty or not exist

    # Backup feedback
    try:
        cursor.execute("SELECT * FROM feedback")
        columns = [desc[0] for desc in cursor.description]
        for row in cursor.fetchall():
            backup_data["feedback"].append(dict(zip(columns, row, strict=False)))
    except sqlite3.OperationalError:
        pass  # Table might be empty or not exist

    # Write backup
    with open(backup_file, "w") as f:
        json.dump(backup_data, f, indent=2)

    logger.info("Backup created: %s", backup_file)
    logger.info("   - %s rules", len(backup_data["rules"]))
    logger.info("   - %s pending rules", len(backup_data["pending_rules"]))
    logger.info("   - %s corrections", len(backup_data["corrections"]))
    logger.info("   - %s feedback entries", len(backup_data["feedback"]))

    return backup_file


def clear_rules(conn):
    """Clear all rules and corrections"""
    cursor = conn.cursor()

    # Clear tables
    cursor.execute("DELETE FROM rules")
    rules_deleted = cursor.rowcount

    cursor.execute("DELETE FROM pending_rules")
    pending_deleted = cursor.rowcount

    try:
        cursor.execute("DELETE FROM corrections")
        corrections_deleted = cursor.rowcount
    except sqlite3.OperationalError:
        corrections_deleted = 0

    try:
        cursor.execute("DELETE FROM feedback")
        feedback_deleted = cursor.rowcount
    except sqlite3.OperationalError:
        feedback_deleted = 0

    conn.commit()

    logger.info("\n🗑️  Cleared:")
    logger.info("   - %s rules", rules_deleted)
    logger.info("   - %s pending rules", pending_deleted)
    logger.info("   - %s corrections", corrections_deleted)
    logger.info("   - %s feedback entries", feedback_deleted)


def main():
    """Main function"""
    logger.info("Clearing rules database...\n")

    if not DB_PATH.exists():
        logger.error("Database not found: %s", DB_PATH)
        return

    conn = sqlite3.connect(str(DB_PATH))

    try:
        # Backup first
        backup_file = backup_rules(conn)

        # Confirm
        response = input("\n⚠️  Are you sure you want to clear all rules? (yes/no): ")
        if response.lower() != "yes":
            logger.warning("Cancelled")
            return

        # Clear
        clear_rules(conn)

        logger.info("\n✅ Rules cleared successfully!")
        logger.info("📦 Backup saved to: %s", backup_file)
        logger.info("\n💡 To restore, manually import from the backup JSON")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
