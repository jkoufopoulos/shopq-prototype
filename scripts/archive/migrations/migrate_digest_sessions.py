#!/usr/bin/env python3
"""
Migration: Add digest_sessions table to existing tracking database

This table is required for storing digest HTML and metadata for quality analysis.
The table schema exists in email_tracker.py but was not created in production DB.

Usage:
    python scripts/migrate_digest_sessions.py
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

# Determine database path
DB_PATH = Path("data/shopq_tracking.db")

print("ShopQ Digest Sessions Table Migration")
print("=" * 60)
print(f"Database: {DB_PATH}")
print()

# Check if database exists
if not DB_PATH.exists():
    print(f"❌ Database not found at {DB_PATH}")
    print("   This migration is for local development only.")
    print("   Production DB in /tmp will be created automatically on next digest run.")
    sys.exit(1)

# Connect to database
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Check if table already exists
cursor.execute("""
    SELECT name FROM sqlite_master
    WHERE type='table' AND name='digest_sessions'
""")
table_exists = cursor.fetchone() is not None

if table_exists:
    print("✅ digest_sessions table already exists")
    print()

    # Show row count
    cursor.execute("SELECT COUNT(*) FROM digest_sessions")
    count = cursor.fetchone()[0]
    print(f"   Current row count: {count}")

    conn.close()
    sys.exit(0)

print("📝 Creating digest_sessions table...")

# Create table (schema from email_tracker.py lines 117-129)
cursor.execute("""
    CREATE TABLE IF NOT EXISTS digest_sessions (
        session_id TEXT PRIMARY KEY,
        digest_html TEXT,
        digest_text TEXT,
        generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        email_count INTEGER,
        featured_count INTEGER,
        critical_count INTEGER,
        time_sensitive_count INTEGER,
        routine_count INTEGER
    )
""")

conn.commit()

print("✅ Table created successfully")
print()

# Verify creation
cursor.execute("""
    SELECT sql FROM sqlite_master
    WHERE type='table' AND name='digest_sessions'
""")
schema = cursor.fetchone()[0]
print("Schema:")
print(schema)
print()

conn.close()

print("=" * 60)
print("✅ Migration complete!")
print()
print("Next steps:")
print("  1. Run a ShopQ digest to populate the table")
print("  2. Verify: SELECT * FROM digest_sessions")
