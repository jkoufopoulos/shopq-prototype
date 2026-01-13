"""
User Preference Learning Module

Allows users to set explicit importance preferences for email threads.
Preferences apply after base classification but before digest sectioning.

Philosophy:
- Taxonomy stays immutable (email IS finance, event_start=2pm)
- Preferences personalize ordering/sectioning (user CARES about finance more/less)
- Thread-level preferences (all messages in thread get same preference)

Features:
- Cap: ≤200 preferences/user
- Expiry: 30 days (configurable) - prevents stale preferences
- Performance: ≤100ms to apply
- Explainability: Original classification preserved

Temporal Decay Interaction (Architecture Decision):
    Preferences respect temporal relevance with nuanced rules:

    1. **Active items**: Explicit preference wins until preference TTL expires
       - User marks "Important conference" as critical
       - Stays critical in digest until preference expires (default: 30 days)

    2. **Expired/irrelevant items**: Temporal decay CAN demote even if preferred
       - Past events (event_start < now)
       - Lapsed OTPs (temporal_context indicates expired)
       - These may be hidden/demoted regardless of preference

    3. **Preference age metadata**: Available for UI display
       - Show "You marked this important 45 days ago"
       - Allow user to "refresh" preference (reset timestamp)

    This preserves user intent without surfacing stale content.

Integration Point:
    Stage 1.5 in context_digest.py (after Stage 1 importance classification,
    before Stage 2 entity extraction). See context_digest.py lines ~667-721.

Usage:
    from shopq.concepts.preferences import UserPreferenceManager

    manager = UserPreferenceManager(user_id="alice")

    # Set explicit preference
    manager.add_preference(
        thread_id="thread_123",
        importance="critical",
        reason="Important client thread"
    )

    # Apply preferences to classified emails
    classified_emails = [...]
    personalized = manager.apply_preferences(classified_emails)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from shopq.infrastructure.database import db_transaction, get_db_connection
from shopq.observability.logging import get_logger

logger = get_logger(__name__)

# Preference policy
MAX_PREFERENCES_PER_USER = 200
DEFAULT_EXPIRY_DAYS = 30


class UserPreferenceManager:
    """Manages explicit user preferences for thread-level importance personalization.

    Note: Preferences do not change taxonomy (email type, event dates).
    They personalize importance/sectioning based on user's stated preferences.
    """

    def __init__(self, user_id: str):
        """
        Initialize UserPreferenceManager for a specific user.

        Args:
            user_id: User ID (for multi-tenant isolation)
        """
        self.user_id = user_id
        self._ensure_table_exists()

    def _ensure_table_exists(self):
        """Create user_preferences table if it doesn't exist.

        Note: This stores explicit user preferences (not taxonomy corrections).
        Preferences personalize importance without changing base classification.

        Side Effects:
            - Creates user_preferences table in shopq.db if not exists
            - Creates indexes for fast lookups and expiry cleanup
            - Writes to database via db_transaction()
        """
        with db_transaction() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_preferences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    thread_id TEXT NOT NULL,
                    importance TEXT,
                    type TEXT,
                    reason TEXT,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    UNIQUE(user_id, thread_id)
                )
            """)

            # Index for fast lookups
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_pref_user_thread
                ON user_preferences(user_id, thread_id)
            """)

            # Index for expiry cleanup
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_pref_expires_at
                ON user_preferences(expires_at)
            """)

    def add_preference(
        self,
        thread_id: str,
        importance: str | None = None,
        email_type: str | None = None,
        reason: str | None = None,
        expiry_days: int = DEFAULT_EXPIRY_DAYS,
    ) -> dict[str, Any]:
        """
        Add or update preference for a thread.

        Args:
            thread_id: Gmail thread ID
            importance: Preference for importance (critical, time_sensitive, routine, or None)
            email_type: Preference for type (event, finance, travel, etc. or None)
            reason: Human-readable reason for preference
            expiry_days: Days until preference expires (default: 30)

        Returns:
            Dict with preference details

        Raises:
            ValueError: If preference cap exceeded

        Side Effects:
            - Inserts or updates user_preferences table in shopq.db
            - Writes to database via db_transaction()
            - Logs info message about preference storage
        """
        # Validate at least one preference field is provided
        if importance is None and email_type is None:
            raise ValueError("Must provide at least one of: importance, email_type")

        # Check preference cap
        if not self._can_add_preference(thread_id):
            raise ValueError(f"Preference cap exceeded ({MAX_PREFERENCES_PER_USER} per user)")

        now = datetime.now(UTC)
        expires_at = now + timedelta(days=expiry_days)

        with db_transaction() as conn:
            # Upsert preference (replace if exists)
            conn.execute(
                """
                INSERT INTO user_preferences
                    (user_id, thread_id, importance, type, reason, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, thread_id) DO UPDATE SET
                    importance = excluded.importance,
                    type = excluded.type,
                    reason = excluded.reason,
                    created_at = excluded.created_at,
                    expires_at = excluded.expires_at
            """,
                (
                    self.user_id,
                    thread_id,
                    importance,
                    email_type,
                    reason or "User preference",
                    now.isoformat(),
                    expires_at.isoformat(),
                ),
            )

        logger.info(
            f"Added preference for thread {thread_id}: importance={importance}, type={email_type}",
            extra={
                "user_id": self.user_id,
                "thread_id": thread_id,
                "importance": importance,
                "type": email_type,
            },
        )

        return {
            "thread_id": thread_id,
            "importance": importance,
            "type": email_type,
            "reason": reason or "User preference",
            "expires_at": expires_at.isoformat(),
        }

    def _can_add_preference(self, thread_id: str) -> bool:
        """
        Check if user can add another preference.

        Args:
            thread_id: Thread ID to check (updating existing doesn't count against cap)

        Returns:
            True if user can add preference, False if cap exceeded
        """
        with get_db_connection() as conn:
            # Count current preferences (excluding expired and the thread being updated)
            cursor = conn.execute(
                """
                SELECT COUNT(*) FROM user_preferences
                WHERE user_id = ?
                AND expires_at > ?
                AND thread_id != ?
            """,
                (self.user_id, datetime.now(UTC).isoformat(), thread_id),
            )
            count = cursor.fetchone()[0]

        return count < MAX_PREFERENCES_PER_USER

    def get_preference(self, thread_id: str) -> dict[str, Any] | None:
        """
        Get preference for a specific thread.

        Args:
            thread_id: Gmail thread ID

        Returns:
            Preference dict or None if no active preference exists
        """
        with get_db_connection() as conn:
            cursor = conn.execute(
                """
                SELECT importance, type, reason, created_at, expires_at
                FROM user_preferences
                WHERE user_id = ? AND thread_id = ? AND expires_at > ?
            """,
                (self.user_id, thread_id, datetime.now(UTC).isoformat()),
            )
            row = cursor.fetchone()

        if not row:
            return None

        return {
            "thread_id": thread_id,
            "importance": row[0],
            "type": row[1],
            "reason": row[2],
            "created_at": row[3],
            "expires_at": row[4],
        }

    def apply_preferences(self, classified_emails: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Apply user preferences to classified emails.

        This runs AFTER LLM/mapper/guardrails but BEFORE digest sectioning.
        Performance target: ≤100ms for typical digest (100 emails).

        Args:
            classified_emails: List of classified email dicts with thread_id, importance, type

        Returns:
            List of emails with preferences applied (original importance/type preserved in metadata)
        """
        if not classified_emails:
            return classified_emails

        # Extract unique thread IDs (filter out None values for type safety)
        thread_ids_set = {
            email.get("thread_id") for email in classified_emails if email.get("thread_id")
        }
        thread_ids = [tid for tid in thread_ids_set if tid is not None]

        if not thread_ids:
            return classified_emails

        # Batch fetch all overrides for these threads (single query for performance)
        preferences = self._batch_get_preferences(thread_ids)

        if not preferences:
            return classified_emails

        # Apply overrides
        preference_count = 0
        for email in classified_emails:
            thread_id = email.get("thread_id")
            if thread_id and thread_id in preferences:
                preference = preferences[thread_id]

                # Preserve original classification in metadata for explainability
                email["original_importance"] = email.get("importance")
                email["original_type"] = email.get("type")
                email["original_source"] = email.get("source", "classifier")

                # Apply override
                if preference["importance"]:
                    email["importance"] = preference["importance"]
                if preference["type"]:
                    email["type"] = preference["type"]

                # Mark as user override
                email["source"] = "user_preference"
                email["preference_reason"] = preference["reason"]

                preference_count += 1

        logger.info(
            f"Applied preferences to {len(classified_emails)} emails",
            extra={
                "user_id": self.user_id,
                "preference_count": preference_count,
                "total_emails": len(classified_emails),
            },
        )

        return classified_emails

    def _batch_get_preferences(self, thread_ids: list[str]) -> dict[str, dict[str, Any]]:
        """
        Batch fetch preferences for multiple threads (performance optimization).

        Args:
            thread_ids: List of thread IDs to fetch

        Returns:
            Dict mapping thread_id → preference dict
        """
        if not thread_ids:
            return {}

        # Build SQL with placeholders
        placeholders = ",".join("?" * len(thread_ids))
        query = f"""
            SELECT thread_id, importance, type, reason
            FROM user_preferences
            WHERE user_id = ?
            AND thread_id IN ({placeholders})
            AND expires_at > ?
        """

        params = [self.user_id] + thread_ids + [datetime.now(UTC).isoformat()]

        with get_db_connection() as conn:
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()

        return {row[0]: {"importance": row[1], "type": row[2], "reason": row[3]} for row in rows}

    def list_preferences(self, include_expired: bool = False) -> list[dict[str, Any]]:
        """
        List all preferences for this user.

        Args:
            include_expired: If True, include expired preferences

        Returns:
            List of preference dicts
        """
        with get_db_connection() as conn:
            if include_expired:
                cursor = conn.execute(
                    """
                    SELECT thread_id, importance, type, reason, created_at, expires_at
                    FROM user_preferences
                    WHERE user_id = ?
                    ORDER BY created_at DESC
                """,
                    (self.user_id,),
                )
            else:
                cursor = conn.execute(
                    """
                    SELECT thread_id, importance, type, reason, created_at, expires_at
                    FROM user_preferences
                    WHERE user_id = ? AND expires_at > ?
                    ORDER BY created_at DESC
                """,
                    (self.user_id, datetime.now(UTC).isoformat()),
                )

            rows = cursor.fetchall()

        return [
            {
                "thread_id": row[0],
                "importance": row[1],
                "type": row[2],
                "reason": row[3],
                "created_at": row[4],
                "expires_at": row[5],
            }
            for row in rows
        ]

    def remove_preference(self, thread_id: str) -> bool:
        """
        Remove preference for a thread.

        Args:
            thread_id: Thread ID to remove override for

        Returns:
            True if preference was removed, False if no preference existed

        Side Effects:
            - Deletes row from user_preferences table in shopq.db
            - Writes to database via db_transaction()
            - Logs info message if preference removed
        """
        with db_transaction() as conn:
            cursor = conn.execute(
                """
                DELETE FROM user_preferences
                WHERE user_id = ? AND thread_id = ?
            """,
                (self.user_id, thread_id),
            )

            deleted = cursor.rowcount > 0

        if deleted:
            logger.info(
                f"Removed preference for thread {thread_id}",
                extra={"user_id": self.user_id},
            )

        return deleted

    def cleanup_expired(self) -> int:
        """
        Delete expired preferences (cleanup task, run daily).

        Returns:
            Number of expired preferences deleted

        Side Effects:
            - Deletes expired rows from user_preferences table in shopq.db
            - Writes to database via db_transaction()
            - Logs info message if preferences deleted
        """
        with db_transaction() as conn:
            cursor = conn.execute(
                """
                DELETE FROM user_preferences
                WHERE expires_at < ?
            """,
                (datetime.now(UTC).isoformat(),),
            )
            deleted = cursor.rowcount

        if deleted > 0:
            logger.info(f"Cleaned up {deleted} expired preferences")

        return deleted

    def get_stats(self) -> dict[str, Any]:
        """
        Get preference statistics for this user.

        Returns:
            Dict with stats: total_overrides, expired_count, by_importance, by_type
        """
        with get_db_connection() as conn:
            # Total and expired counts
            cursor = conn.execute(
                """
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN expires_at < ? THEN 1 ELSE 0 END) as expired
                FROM user_preferences
                WHERE user_id = ?
            """,
                (datetime.now(UTC).isoformat(), self.user_id),
            )
            row = cursor.fetchone()
            total = row[0]
            expired = row[1]

            # By importance
            cursor = conn.execute(
                """
                SELECT importance, COUNT(*) as count
                FROM user_preferences
                WHERE user_id = ? AND expires_at > ?
                GROUP BY importance
            """,
                (self.user_id, datetime.now(UTC).isoformat()),
            )
            by_importance = {row[0]: row[1] for row in cursor.fetchall() if row[0]}

            # By type
            cursor = conn.execute(
                """
                SELECT type, COUNT(*) as count
                FROM user_preferences
                WHERE user_id = ? AND expires_at > ?
                GROUP BY type
            """,
                (self.user_id, datetime.now(UTC).isoformat()),
            )
            by_type = {row[0]: row[1] for row in cursor.fetchall() if row[0]}

        return {
            "total_preferences": total,
            "active_preferences": total - (expired or 0),
            "expired_count": expired or 0,
            "cap": MAX_PREFERENCES_PER_USER,
            "remaining": max(0, MAX_PREFERENCES_PER_USER - (total - (expired or 0))),
            "by_importance": by_importance,
            "by_type": by_type,
        }


def get_explainer(email: dict[str, Any]) -> dict[str, str]:
    """
    Get 'Why is this here?' explainer for an email.

    Shows importance, reason, and source to help users understand classification.

    Args:
        email: Classified email dict with importance, source, reason fields

    Returns:
        Dict with explainer fields for UI display
    """
    source = email.get("source", "classifier")
    importance = email.get("importance", "routine")
    reason = email.get("importance_reason", "No reason provided")

    # If user preference (explicit), show original classification too
    if source in ("user_preference", "user_override"):  # Support both old and new
        original_importance = email.get("original_importance", "unknown")
        original_source = email.get("original_source", "classifier")
        preference_reason = email.get("preference_reason") or email.get(
            "override_reason",
            "User preference",
        )

        return {
            "importance": importance,
            "source": "You set this preference",
            "reason": preference_reason,
            "original": f"Originally: {original_importance} (from {original_source})",
        }

    # Map source to user-friendly text
    source_map = {
        "guardrails": "Safety rule",
        "type_mapper": "Calendar detection",
        "temporal_decay": "Time-based importance",
        "classifier": "AI classification",
        "rules": "Pattern match",
    }

    return {
        "importance": importance,
        "source": source_map.get(source, source),
        "reason": reason,
    }
