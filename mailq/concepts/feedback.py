"""
Records user corrections and learns classification patterns from feedback.

When users correct classifications (change labels), records correction to database
and learns patterns to improve future classifications. Part of feedback loop for
continuous improvement.

Key: record_correction() stores feedback, _learn_from_correction() updates patterns.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from mailq.infrastructure.database import db_transaction, get_db_connection
from mailq.observability.logging import get_logger

logger = get_logger(__name__)


class FeedbackManager:
    """
    Manages user feedback and corrections using centralized database pool.

    All data stored in mailq.db using connection pooling for performance.
    """

    def __init__(self) -> None:
        """Initialize feedback manager (schema managed by database.py)"""
        # No initialization needed - schema is managed centrally
        logger.info("Feedback manager initialized with connection pool")

    def record_correction(
        self,
        email_id: str,
        user_id: str,
        from_field: str,
        subject: str,
        snippet: str,
        predicted_labels: list[str],
        actual_labels: list[str],
        predicted_result: dict[str, Any],
        headers: dict[str, Any] | None = None,
    ) -> int:
        """
        Record a user correction.

        Side Effects:
        - Writes to `corrections` table in mailq.db
        - Writes to `learned_patterns` table (via _learn_from_correction)
        - Creates or updates classification rules
        - Modifies future classification behavior for this sender

        Returns:
            correction_id
        """
        # Extract types and domains
        predicted_type = predicted_result.get("type", "unknown")
        predicted_domains = predicted_result.get("domains", [])

        actual_type = self._extract_type_from_labels(actual_labels)
        actual_domains = self._extract_domains_from_labels(actual_labels)

        _ = headers
        with db_transaction() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO corrections (
                    email_id, user_id, from_field, subject, snippet,
                    predicted_labels, actual_labels,
                    predicted_type, actual_type,
                    predicted_domains, actual_domains,
                    timestamp, confidence
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    email_id,
                    user_id,
                    from_field,
                    subject,
                    snippet,
                    json.dumps(predicted_labels),
                    json.dumps(actual_labels),
                    predicted_type,
                    actual_type,
                    json.dumps(predicted_domains),
                    json.dumps(actual_domains),
                    datetime.utcnow().isoformat(),
                    1.0,
                ),
            )
            correction_id = cursor.lastrowid

        logger.info(
            "Recorded correction #%s: %s → %s",
            correction_id,
            predicted_type,
            actual_type,
        )

        # Trigger learning (but NEVER learn "uncategorized" as a rule)
        if actual_type and actual_type != "uncategorized":
            self._learn_from_correction(from_field, subject, actual_type, actual_domains)
        else:
            logger.info("Skipping rule learning: uncategorized is not a valid classification")

        return int(correction_id)

    def _extract_type_from_labels(self, labels: list[str]) -> str | None:
        """Extract type from labels like ['MailQ/Receipts', 'MailQ/Finance']"""
        # Map label names back to types
        type_map = {
            "MailQ/Newsletters": "newsletter",
            "MailQ/Notifications": "notification",
            "MailQ/Receipts": "receipt",
            "MailQ/Events": "event",
            "MailQ/Promotions": "promotion",
            "MailQ/Messages": "message",
            "MailQ/Review-Later": "uncategorized",
            "MailQ/Uncategorized": "uncategorized",
        }
        for label in labels:
            if label in type_map:
                return type_map[label]
        return None

    def _extract_domains_from_labels(self, labels: list[str]) -> list[str]:
        """Extract domains from labels like ['MailQ/Finance', 'MailQ/Work']"""
        # Map label names back to domains
        domain_map = {
            "MailQ/Finance": "finance",
            "MailQ/Shopping": "shopping",
            "MailQ/Work": "professional",
            "MailQ/Personal": "personal",
        }
        domains = []
        for label in labels:
            if label in domain_map:
                domains.append(domain_map[label])
        return domains

    def _learn_from_correction(
        self, from_field: str, _subject: str, actual_type: str, actual_domains: list[str]
    ) -> None:
        """
        Learn pattern from correction.

        Side Effects:
        - Reads from `learned_patterns` table
        - Writes to `learned_patterns` table (creates new or increments support_count)
        - Updates last_seen timestamp for existing patterns
        """
        # Check if we have a pattern for this sender (read first)
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT support_count, classification
                FROM learned_patterns
                WHERE pattern_type = 'sender_exact' AND pattern_value = ?
            """,
                (from_field.lower(),),
            )
            row = cursor.fetchone()

        now = datetime.utcnow().isoformat()

        # Now write the update/insert
        with db_transaction() as conn:
            if row:
                # Increment support count
                support_count = row[0] + 1
                conn.execute(
                    """
                    UPDATE learned_patterns
                    SET support_count = ?, last_seen = ?
                    WHERE pattern_type = 'sender_exact' AND pattern_value = ?
                """,
                    (support_count, now, from_field.lower()),
                )

                logger.info(
                    "Pattern support increased: %s (n=%s)",
                    from_field,
                    support_count,
                )
            else:
                # Create new pattern
                classification = {"type": actual_type, "domains": actual_domains}

                conn.execute(
                    """
                    INSERT INTO learned_patterns (
                        pattern_type, pattern_value, classification,
                        support_count, confidence, first_seen, last_seen
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        "sender_exact",
                        from_field.lower(),
                        json.dumps(classification),
                        1,
                        1.0,
                        now,
                        now,
                    ),
                )

                logger.info("New pattern learned: %s", from_field)

    def get_high_confidence_patterns(self, min_support: int = 3) -> list[dict[str, Any]]:
        """
        Get patterns with high support (3+ corrections).
        These can be added to sender_allowlist or used for few-shot examples.
        """
        with get_db_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT pattern_value, classification, support_count
                FROM learned_patterns
                WHERE pattern_type = 'sender_exact' AND support_count >= ?
                ORDER BY support_count DESC
            """,
                (min_support,),
            )

            patterns = []
            for row in cursor.fetchall():
                patterns.append(
                    {
                        "sender": row[0],
                        "classification": json.loads(row[1]),
                        "support_count": row[2],
                    }
                )

            return patterns

    def get_correction_stats(self, user_id: str | None = None) -> dict[str, Any]:
        """Get statistics about corrections"""
        with get_db_connection() as conn:
            cursor = conn.cursor()

            if user_id:
                cursor.execute("SELECT COUNT(*) FROM corrections WHERE user_id = ?", (user_id,))
            else:
                cursor.execute("SELECT COUNT(*) FROM corrections")

            total_corrections = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM learned_patterns WHERE support_count >= 3")
            high_confidence_patterns = cursor.fetchone()[0]

            return {
                "total_corrections": total_corrections,
                "high_confidence_patterns": high_confidence_patterns,
            }

    def get_fewshot_examples(self, limit: int = 15) -> list[dict[str, Any]]:
        """
        Get best few-shot examples for prompt.
        Prioritizes:
        1. High support count patterns
        2. Diverse domains
        3. Recent corrections
        """
        with get_db_connection() as conn:
            cursor = conn.cursor()

            # Get diverse examples across domains
            cursor.execute(
                """
                SELECT
                    c.from_field,
                    c.subject,
                    c.snippet,
                    c.actual_type,
                    c.actual_domains,
                    p.support_count
                FROM corrections c
                JOIN learned_patterns p ON p.pattern_value = LOWER(c.from_field)
                WHERE p.support_count >= 3
                GROUP BY c.actual_type, c.actual_domains
                ORDER BY p.support_count DESC, c.timestamp DESC
                LIMIT ?
            """,
                (limit,),
            )

            examples = []
            for row in cursor.fetchall():
                examples.append(
                    {
                        "from_field": row[0],
                        "subject": row[1],
                        "snippet": row[2][:200],
                        "type": row[3],
                        "domains": json.loads(row[4]) if row[4] else [],
                        "support_count": row[5],
                    }
                )

            return examples

    def get_top_corrected_senders(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get senders with most corrections"""
        with get_db_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT
                    from_field,
                    COUNT(*) as correction_count,
                    predicted_type,
                    actual_type,
                    predicted_domains,
                    actual_domains
                FROM corrections
                GROUP BY from_field
                ORDER BY correction_count DESC
                LIMIT ?
            """,
                (limit,),
            )

            senders = []
            for row in cursor.fetchall():
                senders.append(
                    {
                        "from_field": row[0],
                        "count": row[1],
                        "most_common_predicted": f"{row[2]} {row[4] if row[4] else ''}",
                        "most_common_actual": f"{row[3]} {row[5] if row[5] else ''}",
                    }
                )

            return senders

    def get_recent_corrections(self, limit: int = 20) -> list[dict[str, Any]]:
        """Get most recent corrections"""
        with get_db_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT
                    timestamp,
                    from_field,
                    subject,
                    predicted_labels,
                    actual_labels,
                    predicted_type,
                    actual_type
                FROM corrections
                ORDER BY timestamp DESC
                LIMIT ?
            """,
                (limit,),
            )

            corrections = []
            for row in cursor.fetchall():
                corrections.append(
                    {
                        "timestamp": row[0],
                        "from_field": row[1],
                        "subject": row[2],
                        "predicted_labels": row[3],
                        "actual_labels": row[4],
                        "predicted_type": row[5],
                        "actual_type": row[6],
                    }
                )

            return corrections
