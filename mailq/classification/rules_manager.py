"""
CRUD operations for classification rules (user-learned patterns).

Manages rules stored in central mailq.db, supporting user corrections that create
new classification patterns. Rules are applied by RulesEngine before LLM fallback.

Key: add_rule(), update_rule(), delete_rule() with connection pooling.
"""

from __future__ import annotations

from typing import Any

from mailq.infrastructure.database import db_transaction, get_db_connection


# ✅ ADD: RulesManager class wrapper
class RulesManager:
    """Wrapper around rules database for API usage (uses centralized connection pool)"""

    def __init__(self, db_path: str | None = None):
        # db_path parameter kept for backward compatibility but ignored
        # All connections now use centralized pool
        pass

    def get_pending_rules(self, user_id: str = "default") -> list[dict[str, Any]]:
        """Get pending rules awaiting promotion (seen 1 time, need 1 more)"""
        from mailq.classification.rules_engine import RulesEngine

        engine = RulesEngine()
        return engine.get_pending_rules(user_id)


def get_rules(user_id: str = "default") -> list[dict[str, Any]]:
    """
    Fetch all active rules for a user

    Args:
        user_id: User identifier (default: 'default')

    Returns:
        List of rule dictionaries with pattern_type, pattern, category
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT id, pattern_type, pattern, category, confidence, use_count
            FROM rules
            WHERE user_id = ?
            ORDER BY id
        """,
            (user_id,),
        )

        return [dict(row) for row in cursor.fetchall()]


def add_rule(
    pattern_type: str,
    pattern: str,
    category: str,
    confidence: int = 85,
    user_id: str = "default",
) -> int:
    """
    Add a new classification rule

    Side Effects:
    - Writes to `rules` table in mailq.db
    - Affects future classifications matching this pattern
    - Committed immediately via db_transaction

    Args:
        pattern_type: Type of pattern ('from', 'subject', 'keyword')
        pattern: The actual pattern to match
        category: Category to assign (e.g., 'Finance', 'Promotions')
        confidence: Confidence score (0-100)
        user_id: User identifier

    Returns:
        ID of the newly created rule

    Raises:
        sqlite3.IntegrityError: If rule already exists (duplicate)
    """
    with db_transaction() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO rules (user_id, pattern_type, pattern, category, confidence)
            VALUES (?, ?, ?, ?, ?)
        """,
            (user_id, pattern_type, pattern, category, confidence),
        )

        return int(cursor.lastrowid)


def update_rule(rule_id: int, **kwargs: Any) -> bool:
    """
    Update an existing rule

    Side Effects:
    - Writes to `rules` table in mailq.db (updates specified fields)
    - Affects future classifications matching this rule
    - Committed immediately via db_transaction

    Args:
        rule_id: ID of rule to update
        **kwargs: Fields to update (pattern, category, confidence, etc.)

    Returns:
        True if rule was updated, False if not found
    """
    if not kwargs:
        return False

    # Build SET clause dynamically
    set_clause = ", ".join(f"{key} = ?" for key in kwargs)
    values = list(kwargs.values()) + [rule_id]

    with db_transaction() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            UPDATE rules
            SET {set_clause}
            WHERE id = ?
        """,
            values,
        )

        return bool(cursor.rowcount > 0)


def delete_rule(rule_id: int) -> bool:
    """
    Delete a rule by ID

    Side Effects:
    - Deletes from `rules` table in mailq.db
    - Removes classification behavior for this pattern
    - Committed immediately via db_transaction

    Args:
        rule_id: ID of rule to delete

    Returns:
        True if deleted, False if not found
    """
    with db_transaction() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM rules WHERE id = ?", (rule_id,))
        return bool(cursor.rowcount > 0)


def get_rule_stats() -> dict[str, Any]:
    """
    Get statistics about rules

    Returns:
        Dict with total_rules, by_type, by_category, etc.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Total rules
        cursor.execute("SELECT COUNT(*) FROM rules")
        total = cursor.fetchone()[0]

        # By type
        cursor.execute("""
            SELECT pattern_type, COUNT(*) as count
            FROM rules
            GROUP BY pattern_type
        """)
        by_type = {row["pattern_type"]: row["count"] for row in cursor.fetchall()}

        # By category
        cursor.execute("""
            SELECT category, COUNT(*) as count
            FROM rules
            GROUP BY category
            ORDER BY count DESC
        """)
        by_category = {row["category"]: row["count"] for row in cursor.fetchall()}

        # Most used rules
        cursor.execute("""
            SELECT id, pattern, category, use_count
            FROM rules
            WHERE use_count > 0
            ORDER BY use_count DESC
            LIMIT 10
        """)
        most_used = [dict(row) for row in cursor.fetchall()]

        return {
            "total_rules": total,
            "by_type": by_type,
            "by_category": by_category,
            "most_used": most_used,
        }


def get_pending_rules(user_id: str = "default") -> list[dict[str, Any]]:
    """Get pending rules awaiting promotion"""
    manager = RulesManager()
    return manager.get_pending_rules(user_id)
