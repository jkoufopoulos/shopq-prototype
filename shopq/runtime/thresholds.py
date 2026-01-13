"""

from __future__ import annotations

Confidence Score Tracking and Analysis

Logs all classification confidence scores to SQLite for:
- Monitoring model performance
- Identifying low-confidence patterns
- Tuning confidence thresholds
- Detecting drift over time
"""

from datetime import datetime
from typing import Any

from shopq.infrastructure.database import db_transaction, get_db_connection
from shopq.observability.confidence import (
    LOGGING_LOW_CONFIDENCE,
)
from shopq.observability.logging import get_logger

logger = get_logger(__name__)


class ConfidenceLogger:
    """
    Track confidence scores for all classifications.

    Uses the centralized database connection pool (shopq.db).
    Logs are stored in the confidence_logs table for analysis.
    """

    def __init__(self):
        """Initialize logger (schema is managed by database.py)"""
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """
        Ensure confidence_logs table exists

        Side Effects:
            - Creates confidence_logs table in shopq.db (if not exists)
            - Creates indexes on timestamp, type_conf, and decider columns
            - Commits transaction to database
        """
        with db_transaction() as conn:
            conn.execute("""
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
                )
            """)

            # Create indexes for common queries
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_conf_logs_timestamp
                ON confidence_logs(timestamp DESC)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_conf_logs_type_conf
                ON confidence_logs(type_conf)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_conf_logs_decider
                ON confidence_logs(decider)
            """)

    def log_classification(
        self,
        result: dict[str, Any],
        email_id: str | None = None,
        subject: str | None = None,
        filtered_labels: int = 0,
        notes: str | None = None,
    ) -> None:
        """
        Log a classification result with all confidence scores.

        Args:
            result: Classification result dict
            email_id: Optional email ID
            subject: Optional email subject
            filtered_labels: Number of labels filtered out by confidence
            notes: Optional notes (e.g., "low confidence", "verifier triggered")

        Side Effects:
            - Inserts row into confidence_logs table in shopq.db
            - Commits transaction to database
        """
        import json

        from shopq.utils.versioning import get_version_metadata

        # Determine if this is a low-confidence classification
        is_low_conf = result.get("type_conf", 0) < LOGGING_LOW_CONFIDENCE
        if is_low_conf and not notes:
            notes = f"Low confidence (< {LOGGING_LOW_CONFIDENCE})"

        # Get version metadata (falls back to defaults if not in result)
        versions = get_version_metadata()
        model_name = result.get("model_name", versions["model_name"])
        model_version = result.get("model_version", versions["model_version"])
        prompt_version = result.get("prompt_version", versions["prompt_version"])

        with db_transaction() as conn:
            # Note: domains/domain_conf columns exist in DB schema for backwards compatibility
            # but we no longer write to them (they'll be NULL for new rows)
            conn.execute(
                """
                INSERT INTO confidence_logs (
                    timestamp, email_id, from_field, subject,
                    type, type_conf,
                    attention, attention_conf, relationship, relationship_conf,
                    decider, labels, labels_conf, filtered_labels, reason, notes,
                    model_name, model_version, prompt_version
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    datetime.now().isoformat(),
                    email_id,
                    result.get("from", ""),
                    subject,
                    result.get("type", ""),
                    result.get("type_conf", 0.0),
                    result.get("attention", ""),
                    result.get("attention_conf", 0.0),
                    result.get("relationship", ""),
                    result.get("relationship_conf", 0.0),
                    result.get("decider", ""),
                    json.dumps(result.get("labels", [])),
                    json.dumps(result.get("labels_conf", {})),
                    filtered_labels,
                    result.get("reason", ""),
                    notes,
                    model_name,
                    model_version,
                    prompt_version,
                ),
            )

    def get_low_confidence_classifications(
        self, limit: int = 100, min_conf: float = LOGGING_LOW_CONFIDENCE
    ) -> list[dict]:
        """
        Get recent low-confidence classifications for review.

        Args:
            limit: Max number of results
            min_conf: Confidence threshold (default from config)

        Returns:
            List of low-confidence classification dicts
        """
        import json

        with get_db_connection() as conn:
            cursor = conn.cursor()
            # Note: domains column excluded - deprecated field
            cursor.execute(
                """
                SELECT
                    timestamp, from_field, subject, type, type_conf,
                    attention, decider, labels, reason, notes
                FROM confidence_logs
                WHERE type_conf < ?
                ORDER BY timestamp DESC
                LIMIT ?
            """,
                (min_conf, limit),
            )

            rows = cursor.fetchall()
            results = []
            for row in rows:
                results.append(
                    {
                        "timestamp": row[0],
                        "from": row[1],
                        "subject": row[2],
                        "type": row[3],
                        "type_conf": row[4],
                        "attention": row[5],
                        "decider": row[6],
                        "labels": json.loads(row[7] or "[]"),
                        "reason": row[8],
                        "notes": row[9],
                    }
                )

            return results

    def get_confidence_stats(self, days: int = 7) -> dict[str, Any]:
        """
        Get confidence statistics for the past N days.

        Args:
            days: Number of days to analyze

        Returns:
            Dict with confidence statistics
        """
        from datetime import timedelta

        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        with get_db_connection() as conn:
            cursor = conn.cursor()

            # Overall stats
            cursor.execute(
                """
                SELECT
                    COUNT(*) as total,
                    AVG(type_conf) as avg_type_conf,
                    MIN(type_conf) as min_type_conf,
                    MAX(type_conf) as max_type_conf,
                    SUM(CASE WHEN type_conf < ? THEN 1 ELSE 0 END) as low_conf_count,
                    SUM(filtered_labels) as total_filtered
                FROM confidence_logs
                WHERE timestamp >= ?
            """,
                (LOGGING_LOW_CONFIDENCE, cutoff),
            )

            row = cursor.fetchone()
            stats = {
                "total_classifications": row[0] or 0,
                "avg_type_confidence": round(row[1] or 0.0, 3),
                "min_type_confidence": round(row[2] or 0.0, 3),
                "max_type_confidence": round(row[3] or 0.0, 3),
                "low_confidence_count": row[4] or 0,
                "total_filtered_labels": row[5] or 0,
                "low_confidence_rate": round((row[4] or 0) / max(row[0], 1), 3),
                "days": days,
            }

            # By decider
            cursor.execute(
                """
                SELECT
                    decider,
                    COUNT(*) as count,
                    AVG(type_conf) as avg_conf,
                    SUM(CASE WHEN type_conf < ? THEN 1 ELSE 0 END) as low_conf
                FROM confidence_logs
                WHERE timestamp >= ?
                GROUP BY decider
            """,
                (LOGGING_LOW_CONFIDENCE, cutoff),
            )

            stats["by_decider"] = {}
            for row in cursor.fetchall():
                stats["by_decider"][row[0]] = {
                    "count": row[1],
                    "avg_confidence": round(row[2], 3),
                    "low_confidence_count": row[3],
                    "low_confidence_rate": round(row[3] / max(row[1], 1), 3),
                }

            # By type
            cursor.execute(
                """
                SELECT
                    type,
                    COUNT(*) as count,
                    AVG(type_conf) as avg_conf
                FROM confidence_logs
                WHERE timestamp >= ?
                GROUP BY type
                ORDER BY count DESC
            """,
                (cutoff,),
            )

            stats["by_type"] = {}
            for row in cursor.fetchall():
                stats["by_type"][row[0]] = {
                    "count": row[1],
                    "avg_confidence": round(row[2], 3),
                }

            return stats

    def get_confidence_trend(self, days: int = 30, _bucket_hours: int = 24) -> list[dict[str, Any]]:
        """
        Get confidence trend over time (for charts/monitoring).

        Args:
            days: Number of days to analyze
            bucket_hours: Group by N hours (default 24 = daily)

        Returns:
            List of time-bucketed confidence stats
            Side Effects:
                Modifies local data structures
        """
        from datetime import timedelta

        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        with get_db_connection() as conn:
            cursor = conn.cursor()

            # SQLite doesn't have easy time bucketing, so we'll get all and group in Python
            cursor.execute(
                """
                SELECT
                    timestamp,
                    type_conf,
                    decider
                FROM confidence_logs
                WHERE timestamp >= ?
                ORDER BY timestamp ASC
            """,
                (cutoff,),
            )

            rows = cursor.fetchall()

            # Group by day (simplified bucketing)
            from collections import defaultdict

            buckets: defaultdict[str, dict[str, float | int]] = defaultdict(
                lambda: {"total": 0, "sum_conf": 0.0, "low_conf": 0}
            )

            for row in rows:
                timestamp_str, type_conf, decider = row
                day = timestamp_str[:10]  # YYYY-MM-DD
                buckets[day]["total"] += 1
                buckets[day]["sum_conf"] += type_conf
                if type_conf < LOGGING_LOW_CONFIDENCE:
                    buckets[day]["low_conf"] += 1

            # Convert to list
            trend = []
            for day in sorted(buckets.keys()):
                data = buckets[day]
                trend.append(
                    {
                        "date": day,
                        "total": data["total"],
                        "avg_confidence": round(data["sum_conf"] / max(data["total"], 1), 3),
                        "low_confidence_count": data["low_conf"],
                        "low_confidence_rate": round(data["low_conf"] / max(data["total"], 1), 3),
                    }
                )

            return trend

    def clear_old_logs(self, days: int = 90) -> int:
        """
        Clear logs older than N days to prevent database bloat.

        Args:
            days: Keep logs from the last N days

        Side Effects:
            - Deletes rows from confidence_logs table in shopq.db
            - Commits transaction to database
            - Writes log entry with deletion count
        """
        from datetime import timedelta

        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        with db_transaction() as conn:
            cursor = conn.execute(
                """
                DELETE FROM confidence_logs
                WHERE timestamp < ?
            """,
                (cutoff,),
            )

            deleted = cursor.rowcount
            logger.info("Deleted %s confidence logs older than %s days", deleted, days)

            return deleted
