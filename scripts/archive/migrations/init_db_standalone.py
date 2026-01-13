#!/usr/bin/env python3
"""
Standalone database initialization script for Docker builds.

This script creates an empty database file.
Tables will be created on-demand by modules via their init_db() methods.
"""

import sqlite3
from pathlib import Path

# Database path
DB_PATH = Path("/app/shopq/data/shopq.db")


def init_database():
    """Create empty database file (tables created on-demand by application)"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Create empty database - tables will be created by modules on first use
    conn = sqlite3.connect(DB_PATH)

    # Just create a simple version table to validate database creation
    conn.execute("""
        CREATE TABLE IF NOT EXISTS _db_version (
            version TEXT PRIMARY KEY,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("INSERT OR IGNORE INTO _db_version (version) VALUES ('1.0.0')")
    conn.commit()
    conn.close()

    print(f"✅ Database file created: {DB_PATH}")
    print("   Tables will be initialized on first use by application modules")
    return


def init_database_full():
    """Full database initialization with all tables (kept for reference)"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)

    # Execute full schema from database.py
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

        CREATE TABLE IF NOT EXISTS fewshot_examples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_field TEXT NOT NULL,
            subject TEXT NOT NULL,
            snippet TEXT NOT NULL,
            classification TEXT NOT NULL,
            category TEXT NOT NULL,
            priority INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_corrections_from ON corrections(from_field);
        CREATE INDEX IF NOT EXISTS idx_corrections_user ON corrections(user_id);
        CREATE INDEX IF NOT EXISTS idx_patterns_type ON learned_patterns(pattern_type);

        -- Digest Learning tables
        CREATE TABLE IF NOT EXISTS digest_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            thread_id TEXT NOT NULL,
            message_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            predicted_importance TEXT NOT NULL,
            predicted_section TEXT NOT NULL,
            action TEXT NOT NULL,
            vote TEXT NOT NULL,
            vote_strength REAL NOT NULL,
            time_in_inbox INTEGER,
            from_email TEXT,
            subject TEXT,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_digest_feedback_session ON digest_feedback(session_id);
        CREATE INDEX IF NOT EXISTS idx_digest_feedback_thread ON digest_feedback(thread_id);
        CREATE INDEX IF NOT EXISTS idx_digest_feedback_user ON digest_feedback(user_id);

        CREATE TABLE IF NOT EXISTS digest_patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pattern_type TEXT NOT NULL,
            pattern_value TEXT NOT NULL,
            importance_level TEXT NOT NULL,
            upvotes INTEGER DEFAULT 0,
            downvotes INTEGER DEFAULT 0,
            confidence REAL DEFAULT 0.0,
            user_ids TEXT DEFAULT '[]',
            first_seen TEXT NOT NULL,
            last_updated TEXT NOT NULL,
            UNIQUE(pattern_type, pattern_value, importance_level)
        );

        -- Tracking tables (from EmailThreadTracker)
        CREATE TABLE IF NOT EXISTS email_threads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            thread_id TEXT NOT NULL,
            message_id TEXT NOT NULL,
            from_email TEXT NOT NULL,
            subject TEXT NOT NULL,
            received_date TEXT NOT NULL,
            email_type TEXT NOT NULL,
            type_confidence REAL,
            domains TEXT,
            domain_confidence TEXT,
            attention TEXT,
            relationship TEXT,
            importance TEXT NOT NULL,
            importance_reason TEXT,
            decider TEXT NOT NULL,
            verifier_used BOOLEAN DEFAULT 0,
            verifier_verdict TEXT,
            verifier_reason TEXT,
            entity_extracted BOOLEAN DEFAULT 0,
            entity_type TEXT,
            entity_confidence REAL,
            entity_details TEXT,
            in_digest BOOLEAN DEFAULT 0,
            in_featured BOOLEAN DEFAULT 0,
            in_orphaned BOOLEAN DEFAULT 0,
            in_noise BOOLEAN DEFAULT 0,
            noise_category TEXT,
            summary_line TEXT,
            summary_linked BOOLEAN,
            session_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            UNIQUE(thread_id, session_id)
        );

        CREATE INDEX IF NOT EXISTS idx_thread_id ON email_threads(thread_id);
        CREATE INDEX IF NOT EXISTS idx_session ON email_threads(session_id);
        CREATE INDEX IF NOT EXISTS idx_importance ON email_threads(importance);
        CREATE INDEX IF NOT EXISTS idx_timestamp ON email_threads(timestamp);

        CREATE TABLE IF NOT EXISTS digest_sessions (
            session_id TEXT PRIMARY KEY,
            digest_html TEXT,
            digest_text TEXT,
            generated_at TEXT NOT NULL,
            email_count INTEGER,
            featured_count INTEGER,
            critical_count INTEGER,
            time_sensitive_count INTEGER,
            routine_count INTEGER
        );

        CREATE INDEX IF NOT EXISTS idx_generated_at ON digest_sessions(generated_at);

        -- Confidence logging table
        CREATE TABLE IF NOT EXISTS confidence_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            email_id TEXT,
            from_field TEXT NOT NULL,
            subject TEXT,
            type TEXT NOT NULL,
            type_conf REAL NOT NULL,
            domains TEXT,
            domain_conf TEXT,
            attention TEXT,
            attention_conf REAL,
            relationship TEXT,
            relationship_conf REAL,
            decider TEXT NOT NULL,
            labels TEXT,
            labels_conf TEXT,
            filtered_labels INTEGER DEFAULT 0,
            reason TEXT,
            notes TEXT,
            model_name TEXT,
            model_version TEXT,
            prompt_version TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_conf_logs_timestamp ON confidence_logs(timestamp DESC);
        CREATE INDEX IF NOT EXISTS idx_conf_logs_type_conf ON confidence_logs(type_conf);
        CREATE INDEX IF NOT EXISTS idx_conf_logs_decider ON confidence_logs(decider);
    """)

    conn.commit()

    # VALIDATE: Verify all expected tables exist
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    existing_tables = {row[0] for row in cursor.fetchall()}

    required_tables = {
        "rules",
        "pending_rules",
        "categories",
        "feedback",
        "learned_patterns",
        "corrections",
        "fewshot_examples",
        "digest_feedback",
        "digest_patterns",
        "email_threads",
        "digest_sessions",
        "confidence_logs",
    }

    missing = required_tables - existing_tables
    if missing:
        conn.close()
        if DB_PATH.exists():
            DB_PATH.unlink()  # Delete incomplete database
        raise RuntimeError(
            f"Database initialization incomplete. Missing tables: {missing}\n"
            f"Found tables: {existing_tables}\n"
            f"Deleted incomplete database file."
        )

    print(f"✅ Database initialized: {DB_PATH}")
    print(f"   Created {len(existing_tables)} tables successfully")

    # Validate indexes exist
    cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
    index_count = len(cursor.fetchall())
    if index_count < 10:  # We expect ~20 indexes
        conn.close()
        if DB_PATH.exists():
            DB_PATH.unlink()  # Delete incomplete database
        raise RuntimeError(
            f"Database initialization incomplete. "
            f"Expected ~20 indexes, found {index_count}\n"
            f"Deleted incomplete database file."
        )

    print(f"   Created {index_count} indexes successfully")
    conn.close()


if __name__ == "__main__":
    # Use full initialization for Docker builds to ensure all tables exist
    init_database_full()
