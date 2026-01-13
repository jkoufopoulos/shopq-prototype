"""Rules-based email classification with learning"""

from __future__ import annotations

import re
from typing import Any

from shopq.infrastructure.database import db_transaction, get_db_connection
from shopq.observability.logging import get_logger
from shopq.runtime.gates import feature_gates

logger = get_logger(__name__)


class RulesEngine:
    """
    Rules-based email classifier using centralized database connection pool.

    Uses shopq.db for all rule storage and retrieval.
    Connection pooling provides 10x performance improvement over direct connections.
    """

    def __init__(self) -> None:
        """Initialize rules engine (schema managed by database.py)"""
        # No initialization needed - schema is managed centrally

    def _extract_email_address(self, from_field: str) -> str:
        """Extract just email address from 'Name <email@domain.com>' format"""
        email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", from_field)
        if email_match:
            return email_match.group(0).lower()
        return from_field.lower()

    def _patterns_match(self, pattern: str, from_field: str) -> bool:
        """Check if a pattern matches the from field (case-insensitive)"""
        pattern_lower = pattern.lower().strip()
        from_lower = from_field.lower().strip()

        # Extract email addresses from both
        pattern_email = self._extract_email_address(pattern)
        from_email = self._extract_email_address(from_field)

        # Try multiple matching strategies
        # 1. Exact match on full string
        if pattern_lower == from_lower:
            return True

        # 2. Pattern is substring of from_field
        if pattern_lower in from_lower:
            return True

        # 3. Email addresses match
        if pattern_email == from_email:
            return True

        # 4. Pattern email is in from_field
        return bool(pattern_email and pattern_email in from_lower)

    def classify(
        self, _subject: str, _snippet: str, from_field: str, user_id: str = "default"
    ) -> dict[str, Any]:
        """Classify email using learned rules (case-insensitive matching)

        Side Effects:
            - Increments use_count in rules table for matched rule
            - Writes to shopq.db via db_transaction()
            - Logs warnings if use_count update fails
        """
        with get_db_connection() as conn:
            cursor = conn.cursor()

            # Get all 'from' rules ordered by confidence and usage
            cursor.execute(
                """
                SELECT id, category, confidence, use_count, pattern
                FROM rules
                WHERE user_id = ? AND pattern_type = 'from'
                ORDER BY confidence DESC, use_count DESC
            """,
                (user_id,),
            )

            rules = cursor.fetchall()

            for rule_id, category, confidence, _use_count, pattern in rules:
                # Check if pattern matches (case-insensitive)
                if self._patterns_match(pattern, from_field):
                    # Atomically increment use count
                    # Using a separate transaction is safe here because use_count is
                    # a monotonic counter and lost updates are acceptable (it's just metrics)
                    try:
                        with db_transaction() as write_conn:
                            write_conn.execute(
                                """
                                UPDATE rules
                                SET use_count = use_count + 1
                                WHERE id = ?
                            """,
                                (rule_id,),
                            )
                    except Exception as e:
                        # Don't fail classification if use_count update fails
                        logger.warning(f"Failed to increment use_count for rule {rule_id}: {e}")

                    return {
                        "category": category,
                        "confidence": confidence / 100.0,
                        "source": "rule",
                    }

            # No rule matched
            return {"category": "Uncategorized", "confidence": 0.0, "source": "no_rule"}

    def get_matching_rules(
        self, from_field: str, _subject: str, user_id: str = "default"
    ) -> list[dict[str, Any]]:
        """Get all rules that match this email (case-insensitive)

        Side Effects:
            - None (read-only query)
            - Logs info message if test_mode enabled
        """
        # If test mode is enabled, return empty list (no rules matching)
        if feature_gates.is_enabled("test_mode"):
            logger.info("🧪 Test mode enabled - skipping rules engine")
            return []

        with get_db_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT id, category, confidence, pattern, pattern_type, use_count
                FROM rules
                WHERE user_id = ? AND pattern_type = 'from'
                ORDER BY confidence DESC, use_count DESC
            """,
                (user_id,),
            )

            matching_rules = []
            for (
                rule_id,
                category,
                confidence,
                pattern,
                pattern_type,
                use_count,
            ) in cursor.fetchall():
                # Check if this rule matches (case-insensitive)
                if self._patterns_match(pattern, from_field):
                    matching_rules.append(
                        {
                            "id": rule_id,
                            "pattern": pattern,
                            "pattern_type": pattern_type,
                            "category": category,
                            "confidence": confidence,
                            "use_count": use_count,
                        }
                    )

            return matching_rules

    def learn_from_classification(
        self,
        _subject: str,
        _snippet: str,
        from_field: str,
        category: str,
        user_id: str = "default",
        confidence: float = 0.85,
    ) -> None:
        """
        Learn from user corrections or LLM classifications.

        NOTE: Disabled in test mode to prevent rule creation during testing.

        Side Effects:
        - May insert/update records in `rules` or `pending_rules` tables
        - Uses atomic SQL operations to prevent race conditions
        """
        # If test mode is enabled, don't learn from classifications
        if feature_gates.is_enabled("test_mode"):
            logger.info("🧪 Test mode enabled - skipping rule learning")
            return

        """
        Learn from Gemini classification - requires 2+ consistent classifications.

        NOTE: Does NOT create rules for "uncategorized" - that's not a classification.
        """
        # ✅ NEVER create "uncategorized" rules
        if category.lower() in ["uncategorized", "review-later", "unknown"]:
            logger.info(
                f"⏭️  Skipping pending rule: '{category}' is not a valid classification target"
            )
            return

        from_normalized = from_field.lower().strip()

        # ATOMIC OPERATION: Single transaction for rule check, pending rule upsert, and promotion
        # This prevents TOCTOU race conditions
        with db_transaction() as conn:
            cursor = conn.cursor()

            # Step 1: Check if a confirmed rule already exists
            cursor.execute(
                """
                SELECT confidence FROM rules
                WHERE user_id = ? AND pattern_type = 'from' AND pattern = ?
            """,
                (user_id, from_normalized),
            )

            existing_rule = cursor.fetchone()

            if existing_rule:
                existing_confidence = existing_rule[0]

                # Try to update if new confidence is higher
                if int(confidence * 100) > existing_confidence:
                    cursor.execute(
                        """
                        UPDATE rules
                        SET category = ?, confidence = ?
                        WHERE user_id = ? AND pattern_type = 'from' AND pattern = ?
                    """,
                        (category, int(confidence * 100), user_id, from_normalized),
                    )
                    logger.info(
                        f"📝 Updated rule: {from_field} → {category} (confidence: {confidence:.2f})"
                    )
                else:
                    logger.info("⏭️ Skipping rule update: existing rule has higher confidence")
                return

            # Step 2: No confirmed rule exists - try to insert new pending rule
            cursor.execute(
                """
                INSERT OR IGNORE INTO pending_rules (
                    user_id,
                    pattern_type,
                    pattern,
                    category,
                    confidence,
                    seen_count
                )
                VALUES (?, 'from', ?, ?, ?, 1)
            """,
                (user_id, from_normalized, category, int(confidence * 100)),
            )

            was_inserted = cursor.rowcount > 0

            if was_inserted:
                logger.info(
                    f"📝 Added to pending: {from_field} → {category} "
                    f"(1/2, confidence: {confidence:.2f})"
                )
                return

            # Step 3: Pending rule already exists - atomically increment and check for promotion
            cursor.execute(
                """
                UPDATE pending_rules
                SET seen_count = seen_count + 1,
                    confidence = ?,
                    last_seen = CURRENT_TIMESTAMP
                WHERE user_id = ? AND pattern_type = 'from' AND pattern = ? AND category = ?
                RETURNING seen_count
            """,
                (int(confidence * 100), user_id, from_normalized, category),
            )

            result = cursor.fetchone()
            if not result:
                # Pending rule was deleted between INSERT and UPDATE (rare)
                logger.warning(f"⚠️  Pending rule vanished during update: {from_field} → {category}")
                return

            new_count = result[0]

            # Step 4: Promote to real rule after 2 consistent classifications
            if new_count >= 2:
                # Insert into rules (OR IGNORE if another thread already promoted)
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO rules
                    (user_id, pattern_type, pattern, category, confidence)
                    VALUES (?, 'from', ?, ?, ?)
                """,
                    (user_id, from_normalized, category, int(confidence * 100)),
                )

                rule_was_created = cursor.rowcount > 0

                # Delete from pending
                cursor.execute(
                    """
                    DELETE FROM pending_rules
                    WHERE user_id = ? AND pattern_type = 'from' AND pattern = ? AND category = ?
                """,
                    (user_id, from_normalized, category),
                )

                if rule_was_created:
                    logger.info(
                        f"✅ PROMOTED to rule: {from_field} → {category} "
                        f"(seen {new_count} times, confidence: {confidence:.2f})"
                    )
                else:
                    logger.info(
                        f"⏭️  Rule already promoted by concurrent thread: {from_field} → {category}"
                    )
            else:
                logger.info(
                    f"📊 Pending rule updated: {from_field} → {category} (seen {new_count}/2 times)"
                )

    def learn_from_correction(
        self, email: dict[str, Any], category: str, user_id: str = "default"
    ) -> None:
        """
        Learn from user feedback - IMMEDIATELY creates rule (bypasses pending).

        NOTE: Does NOT create rules for "uncategorized" - that's not a classification.

        Side Effects:
            - Inserts or replaces rule in rules table (confidence=95)
            - Deletes matching pending_rules entries
            - Writes to shopq.db via db_transaction()
            - Logs info messages about rule creation
        """
        # ✅ NEVER create "uncategorized" rules
        if category.lower() in ["uncategorized", "review-later", "unknown"]:
            logger.info(
                f"⏭️  Skipping rule creation: '{category}' is not a valid classification target"
            )
            return

        from_field = email.get("from", "").lower().strip()

        # ✅ User feedback ALWAYS creates immediate rule (except for uncategorized)
        with db_transaction() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO rules (user_id, pattern_type, pattern, category, confidence)
                VALUES (?, 'from', ?, ?, 95)
            """,
                (user_id, from_field, category),
            )

            # Remove from pending if exists
            conn.execute(
                """
                DELETE FROM pending_rules
                WHERE user_id = ? AND pattern_type = 'from' AND pattern = ?
            """,
                (user_id, from_field),
            )

        logger.info(
            f"✅ USER CORRECTION (immediate rule): {from_field} → {category} (confidence: 0.95)"
        )

    def get_pending_rules(self, user_id: str = "default") -> list[dict]:
        """Get all pending rules awaiting promotion

        Side Effects: None (read-only query)
        """
        with get_db_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT pattern, category, confidence, seen_count, last_seen
                FROM pending_rules
                WHERE user_id = ?
                ORDER BY last_seen DESC
            """,
                (user_id,),
            )

            pending = []
            for row in cursor.fetchall():
                pending.append(
                    {
                        "pattern": row[0],
                        "category": row[1],
                        "confidence": row[2] / 100.0,
                        "seen_count": row[3],
                        "last_seen": row[4],
                    }
                )

            return pending
