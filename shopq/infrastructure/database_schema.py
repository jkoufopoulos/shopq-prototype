"""
Database schema initialization for ShopQ.

Contains the SQL schema and initialization logic, extracted from database.py to reduce file size.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from shopq.observability.logging import get_logger

logger = get_logger(__name__)


def init_database(db_path: Path) -> None:
    """
    Initialize database with schema (idempotent)

    Safe to run multiple times - uses CREATE TABLE IF NOT EXISTS.

    Args:
        db_path: Path to the database file

    Side Effects:
    - Creates tables in shopq.db if they don't exist
    - Creates indexes for query performance
    - Creates shopq/data/ directory if needed
    - Idempotent: safe to run multiple times
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT DEFAULT 'default',
            pattern_type TEXT NOT NULL,
            pattern TEXT NOT NULL,
            category TEXT NOT NULL,
            confidence INTEGER DEFAULT 85,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            use_count INTEGER DEFAULT 0,
            UNIQUE(pattern_type, pattern, category)
        );

        CREATE TABLE IF NOT EXISTS pending_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT DEFAULT 'default',
            pattern_type TEXT NOT NULL,
            pattern TEXT NOT NULL,
            category TEXT NOT NULL,
            confidence INTEGER NOT NULL,
            seen_count INTEGER DEFAULT 1,
            last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, pattern_type, pattern, category)
        );

        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT DEFAULT 'default',
            name TEXT UNIQUE NOT NULL,
            description TEXT,
            color TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email_id TEXT NOT NULL,
            user_id TEXT DEFAULT 'default',
            from_field TEXT,
            subject TEXT,
            snippet TEXT,
            predicted_labels TEXT,
            actual_labels TEXT,
            corrected INTEGER DEFAULT 0,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS learned_patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pattern_type TEXT NOT NULL,
            pattern_value TEXT NOT NULL,
            classification TEXT NOT NULL,
            support_count INTEGER DEFAULT 1,
            confidence REAL DEFAULT 0.5,
            first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(pattern_type, pattern_value, classification)
        );

        CREATE INDEX IF NOT EXISTS idx_rules_user_pattern
        ON rules(user_id, pattern_type, pattern);

        CREATE INDEX IF NOT EXISTS idx_pending_rules_user_pattern
        ON pending_rules(user_id, pattern_type, pattern);

        -- Feedback Manager tables
        CREATE TABLE IF NOT EXISTS corrections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            from_field TEXT NOT NULL,
            subject TEXT NOT NULL,
            snippet TEXT,
            predicted_labels TEXT NOT NULL,
            actual_labels TEXT NOT NULL,
            predicted_type TEXT,
            actual_type TEXT,
            predicted_domains TEXT,
            actual_domains TEXT,
            timestamp TEXT NOT NULL,
            applied INTEGER DEFAULT 0,
            confidence REAL DEFAULT 1.0
        );

        CREATE INDEX IF NOT EXISTS idx_corrections_from ON corrections(from_field);
        CREATE INDEX IF NOT EXISTS idx_corrections_user ON corrections(user_id);
        CREATE INDEX IF NOT EXISTS idx_patterns_type ON learned_patterns(pattern_type);

        -- User credentials for Gmail OAuth (encrypted storage)
        CREATE TABLE IF NOT EXISTS user_credentials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL UNIQUE,
            encrypted_token_json TEXT NOT NULL,
            scopes TEXT NOT NULL,
            token_expiry TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_refresh_at TIMESTAMP,
            last_sync_at TIMESTAMP,
            sync_history_id TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_user_credentials_user_id
        ON user_credentials(user_id);

        CREATE INDEX IF NOT EXISTS idx_user_credentials_expiry
        ON user_credentials(token_expiry);

        -- Return Cards for Return Watch feature
        CREATE TABLE IF NOT EXISTS return_cards (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            version TEXT DEFAULT 'v1',
            merchant TEXT NOT NULL,
            merchant_domain TEXT DEFAULT '',
            item_summary TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            confidence TEXT NOT NULL DEFAULT 'unknown',
            source_email_ids TEXT DEFAULT '[]',
            order_number TEXT,
            amount REAL,
            currency TEXT DEFAULT 'USD',
            order_date TEXT,
            delivery_date TEXT,
            return_by_date TEXT,
            return_portal_link TEXT,
            shipping_tracking_link TEXT,
            evidence_snippet TEXT,
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            alerted_at TEXT
        );

        -- Indexes for return_cards queries
        CREATE INDEX IF NOT EXISTS idx_return_cards_user_status
        ON return_cards(user_id, status);

        CREATE INDEX IF NOT EXISTS idx_return_cards_user_return_by
        ON return_cards(user_id, return_by_date);

        CREATE INDEX IF NOT EXISTS idx_return_cards_merchant_domain
        ON return_cards(merchant_domain);
    """)

    conn.commit()
    conn.close()

    logger.info("Database initialized: %s", db_path)


def validate_schema(conn: sqlite3.Connection) -> bool:
    """
    Validate database has expected schema

    Args:
        conn: Active database connection

    Returns:
        True if valid

    Raises:
        ValueError: If tables are missing
    """
    required_tables = {
        "rules": ["id", "pattern_type", "pattern", "category"],
        "pending_rules": ["id", "pattern_type", "pattern", "category", "seen_count"],
        "categories": ["id", "name", "description"],
        "feedback": ["id", "email_id", "predicted_labels"],
        "learned_patterns": ["id", "pattern_type", "pattern_value"],
        "return_cards": ["id", "user_id", "merchant", "item_summary", "status", "confidence"],
    }

    cursor = conn.cursor()

    # Check tables exist
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    existing_tables = {row[0] for row in cursor.fetchall()}

    missing_tables = set(required_tables.keys()) - existing_tables
    if missing_tables:
        raise ValueError(f"Database missing tables: {missing_tables}")

    # Check columns exist
    for table, required_cols in required_tables.items():
        # Validate table name to prevent SQL injection
        # Table names come from hardcoded dict, but validate to be safe
        if not table.replace("_", "").isalnum():
            raise ValueError(f"Invalid table name: {table}")

        # Note: Schema identifiers (table names) cannot use parameterized queries
        # but are validated above to prevent injection
        cursor.execute(f"PRAGMA table_info({table})")
        existing_cols = {row[1] for row in cursor.fetchall()}

        missing_cols = set(required_cols) - existing_cols
        if missing_cols:
            raise ValueError(f"Table '{table}' missing columns: {missing_cols}")

    return True
