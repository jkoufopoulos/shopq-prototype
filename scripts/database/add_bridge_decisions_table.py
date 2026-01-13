"""
Add bridge_decisions table for shadow logging.

This table tracks:
- Backend LLM classification → importance
- Bridge mapper decision → mapped importance + source (guardrail|rule|default)
- User corrections (label changes)

Used for:
- Quality monitoring
- Mapper accuracy analysis
- Identifying guardrail effectiveness
- A/B testing different mapping strategies
"""

from shopq.infrastructure.database import get_db_connection

SQL_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS bridge_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email_id TEXT NOT NULL,
    user_id TEXT DEFAULT 'default',

    -- Backend classification
    backend_importance TEXT,           -- critical | time_sensitive | routine
    backend_confidence REAL,
    backend_type TEXT,                 -- event | deadline | notification | etc.
    backend_attention TEXT,            -- action_required | awareness | fyi
    backend_domains TEXT,              -- JSON array: ["finance", "shopping"]

    -- Bridge mapper decision
    mapper_importance TEXT NOT NULL,   -- urgent | critical | time_sensitive | routine
    mapper_source TEXT NOT NULL,       -- guardrail | rule | default
    mapper_rule_name TEXT,             -- Name of rule that matched
    mapper_reason TEXT,                -- Human-readable reason
    mapper_labels TEXT,                -- JSON array of Gmail labels applied

    -- User feedback
    user_corrected INTEGER DEFAULT 0,  -- 1 if user changed labels
    user_importance TEXT,              -- User's corrected importance (if changed)
    user_labels TEXT,                  -- User's corrected labels (JSON array)

    -- Temporal context
    temporal_start TEXT,               -- ISO8601 datetime
    temporal_end TEXT,                 -- ISO8601 datetime
    temporal_proximity_hours REAL,     -- Hours until event/deadline

    -- Metadata
    timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Indexes for common queries
    UNIQUE(email_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_bridge_decisions_user_id
    ON bridge_decisions(user_id, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_bridge_decisions_mapper_source
    ON bridge_decisions(mapper_source, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_bridge_decisions_user_corrected
    ON bridge_decisions(user_corrected, timestamp DESC)
    WHERE user_corrected = 1;
"""


def create_table():
    """Create bridge_decisions table."""
    print("Creating bridge_decisions table...")

    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Execute SQL (multiple statements)
        cursor.executescript(SQL_CREATE_TABLE)

        conn.commit()

    print("✅ bridge_decisions table created")

    # Verify table exists
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='bridge_decisions'
        """)
        result = cursor.fetchone()

        if result:
            print(f"✅ Verified: {result[0]} table exists")

            # Count rows
            cursor.execute("SELECT COUNT(*) FROM bridge_decisions")
            count = cursor.fetchone()[0]
            print(f"   Current rows: {count}")
        else:
            print("❌ Error: Table not found after creation")


if __name__ == "__main__":
    create_table()
