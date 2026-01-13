"""
Tracks email threads through classification pipeline for observability.

Records classification decisions, entity extraction results, verifier verdicts, and
digest inclusion for each email. Enables debugging and quality analysis via session
reports and CSV exports.

Key: EmailThreadTracker stores all decisions in central mailq.db for telemetry.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any

from mailq.infrastructure.database import db_transaction, get_db_connection
from mailq.observability.logging import get_logger

logger = get_logger(__name__)


def _sanitize_for_json_storage(data: Any, max_depth: int = 10) -> str:
    """
    Safely serialize data for database storage.

    Validates data structure and limits nesting depth to prevent
    malicious deeply nested objects that could cause issues on deserialization.

    Args:
        data: Data to serialize (dict, list, str, etc.)
        max_depth: Maximum nesting depth allowed

    Returns:
        JSON string

    Raises:
        ValueError: If data structure is invalid or too deeply nested

    Side Effects:
        - None (pure function)
    """
    if data is None:
        return "null"

    def check_depth(obj: Any, current_depth: int = 0) -> None:
        """Recursively check nesting depth"""
        if current_depth > max_depth:
            raise ValueError(f"JSON nesting exceeds maximum depth of {max_depth}")

        if isinstance(obj, dict):
            for value in obj.values():
                check_depth(value, current_depth + 1)
        elif isinstance(obj, list):
            for item in obj:
                check_depth(item, current_depth + 1)

    # Validate depth before serialization
    check_depth(data)

    # Use ensure_ascii=True to prevent encoding issues
    return json.dumps(data, ensure_ascii=True)


class EmailThreadTracker:
    """Track email threads through classification and digest pipeline

    NOTE: Uses central database (mailq/data/mailq.db) for all tracking data.
    Old database (data/mailq_tracking.db) is deprecated.
    """

    def __init__(self, db_path: str | None = None):
        # db_path parameter is deprecated but kept for backwards compatibility
        # All tracking now goes to central database
        if db_path is not None:
            logger.warning(
                "EmailThreadTracker: db_path parameter is deprecated. "
                "Using central database (mailq/data/mailq.db) instead."
            )

        # DEBUG mode detection for verbose logging
        self.verbose = os.getenv("DEBUG", "").lower() in ("true", "1", "yes")

        self._init_db()

    def _init_db(self) -> None:
        """
        Initialize tracking database (uses central mailq.db)

        Side Effects:
            - Creates email_threads table if not exists
            - Creates indexes on thread_id, session_id, importance, timestamp
            - Creates digest_sessions table if not exists
            - Writes schema changes to mailq.db via db_transaction
        """
        with db_transaction() as conn:
            cursor = conn.cursor()

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS email_threads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                thread_id TEXT NOT NULL,
                message_id TEXT NOT NULL,
                from_email TEXT NOT NULL,
                subject TEXT NOT NULL,
                received_date TEXT NOT NULL,
                email_type TEXT NOT NULL,
                type_confidence REAL,
                attention TEXT,
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
            )
        """)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_thread_id ON email_threads(thread_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_session ON email_threads(session_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_importance ON email_threads(importance)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON email_threads(timestamp)")

        cursor.execute("""
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
            )
        """)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_generated_at ON digest_sessions(generated_at)"
        )

    def track_classification(
        self,
        thread_id: str,
        message_id: str,
        from_email: str,
        subject: str,
        received_date: str,
        classification: dict[str, Any],
        importance: str,
        importance_reason: str,
        session_id: str,
    ) -> None:
        """
        Track initial classification decision

        Side Effects:
            - Writes to `email_threads` table in mailq.db (INSERT OR REPLACE)
            - Creates or updates tracking record for this thread
            - Committed immediately via db_transaction
        """
        with db_transaction() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO email_threads (
                    thread_id, message_id, from_email, subject, received_date,
                    email_type, type_confidence, attention,
                    importance, importance_reason, decider,
                    session_id, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    thread_id,
                    message_id,
                    from_email,
                    subject,
                    received_date,
                    classification.get("type", "unknown"),
                    classification.get("type_conf", 0.0),
                    classification.get("attention", "none"),
                    importance,
                    importance_reason,
                    classification.get("decider", "unknown"),
                    session_id,
                    datetime.now().isoformat(),
                ),
            )

    def track_verifier(
        self,
        thread_id: str,
        session_id: str,
        verifier_used: bool,
        verdict: str | None = None,
        reason: str | None = None,
    ) -> None:
        """
        Track verifier decision

        Side Effects:
            - Updates email_threads table via UPDATE statement
            - Modifies verifier_used, verifier_verdict, verifier_reason fields
            - Committed immediately via db_transaction
        """
        with db_transaction() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE email_threads
                SET verifier_used = ?,
                    verifier_verdict = ?,
                    verifier_reason = ?
                WHERE thread_id = ? AND session_id = ?
            """,
                (1 if verifier_used else 0, verdict, reason, thread_id, session_id),
            )

    def track_entity(
        self,
        thread_id: str,
        session_id: str,
        entity_extracted: bool,
        entity_type: str | None = None,
        entity_confidence: float | None = None,
        entity_details: dict[str, Any] | None = None,
    ) -> None:
        """
        Track entity extraction result

        Side Effects:
            - Updates email_threads table via UPDATE statement
            - Modifies entity_extracted, entity_type, entity_confidence, entity_details fields
            - Committed immediately via db_transaction
        """
        with db_transaction() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE email_threads
                SET entity_extracted = ?,
                    entity_type = ?,
                    entity_confidence = ?,
                    entity_details = ?
                WHERE thread_id = ? AND session_id = ?
            """,
                (
                    1 if entity_extracted else 0,
                    entity_type,
                    entity_confidence,
                    _sanitize_for_json_storage(entity_details) if entity_details else None,
                    thread_id,
                    session_id,
                ),
            )

    def track_digest_inclusion(
        self,
        thread_id: str,
        session_id: str,
        in_featured: bool = False,
        in_orphaned: bool = False,
        in_noise: bool = False,
        noise_category: str | None = None,
        summary_line: str | None = None,
        summary_linked: bool | None = None,
    ) -> None:
        """
        Track digest inclusion

        Side Effects:
            - Updates email_threads table via UPDATE statement
            - Modifies in_digest, in_featured, in_orphaned, in_noise fields
            - Committed immediately via db_transaction
        """
        in_digest = in_featured or in_orphaned or in_noise

        with db_transaction() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE email_threads
                SET in_digest = ?,
                    in_featured = ?,
                    in_orphaned = ?,
                    in_noise = ?,
                    noise_category = ?,
                    summary_line = ?,
                    summary_linked = ?
                WHERE thread_id = ? AND session_id = ?
            """,
                (
                    1 if in_digest else 0,
                    1 if in_featured else 0,
                    1 if in_orphaned else 0,
                    1 if in_noise else 0,
                    noise_category,
                    summary_line,
                    1 if summary_linked else 0 if summary_linked is not None else None,
                    thread_id,
                    session_id,
                ),
            )

    def save_digest_session(
        self,
        session_id: str,
        digest_html: str,
        digest_text: str,
        email_count: int,
        featured_count: int,
        critical_count: int = 0,
        time_sensitive_count: int = 0,
        routine_count: int = 0,
    ) -> None:
        """
        Save digest HTML and metadata for quality analysis

        Side Effects:
            - Writes to digest_sessions table (INSERT OR REPLACE)
            - Stores digest HTML, text, and counts
            - Committed immediately via db_transaction
            - Logs to logger if verbose mode enabled
        """
        with db_transaction() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO digest_sessions (
                    session_id, digest_html, digest_text, generated_at,
                    email_count, featured_count, critical_count,
                    time_sensitive_count, routine_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    session_id,
                    digest_html,
                    digest_text,
                    datetime.now().isoformat(),
                    email_count,
                    featured_count,
                    critical_count,
                    time_sensitive_count,
                    routine_count,
                ),
            )

        if self.verbose:
            logger.info(
                "Saved digest session %s (%s emails, %s featured)",
                session_id,
                email_count,
                featured_count,
            )

    def get_session_summary(self, session_id: str) -> dict[str, Any]:
        """
        Get summary statistics for a session

        Returns:
            Dict containing session stats (total_threads, importance breakdown, etc.)

        Side Effects:
            - Reads from email_threads and digest_sessions tables
            - Performs SELECT queries on mailq.db
        """
        with get_db_connection() as conn:
            cursor = conn.cursor()

        # Total counts
        cursor.execute(
            """
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN importance = 'critical' THEN 1 ELSE 0 END) as critical,
                SUM(CASE WHEN importance = 'time_sensitive' THEN 1 ELSE 0 END) as time_sensitive,
                SUM(CASE WHEN importance = 'routine' THEN 1 ELSE 0 END) as routine,
                SUM(CASE WHEN entity_extracted = 1 THEN 1 ELSE 0 END) as entities_extracted,
                SUM(CASE WHEN in_featured = 1 THEN 1 ELSE 0 END) as featured,
                SUM(CASE WHEN in_orphaned = 1 THEN 1 ELSE 0 END) as orphaned,
                SUM(CASE WHEN in_noise = 1 THEN 1 ELSE 0 END) as noise,
                SUM(CASE WHEN verifier_used = 1 THEN 1 ELSE 0 END) as verified
            FROM email_threads
            WHERE session_id = ?
        """,
            (session_id,),
        )

        row = cursor.fetchone()

        summary = {
            "session_id": session_id,
            "total_threads": row[0],
            "importance": {
                "critical": row[1] or 0,
                "time_sensitive": row[2] or 0,
                "routine": row[3] or 0,
            },
            "entities_extracted": row[4] or 0,
            "digest_breakdown": {
                "featured": row[5] or 0,
                "orphaned": row[6] or 0,
                "noise": row[7] or 0,
            },
            "verified_count": row[8] or 0,
        }

        # Validate digest coverage (handle None values)
        featured = row[5] or 0
        orphaned = row[6] or 0
        noise = row[7] or 0
        total = row[0] or 0
        summary["digest_coverage_valid"] = featured + orphaned + noise == total

        # Add classification stats (decider breakdown, confidence)
        cursor.execute(
            """
            SELECT
                decider,
                COUNT(*) as count,
                AVG(type_confidence) as avg_conf
            FROM email_threads
            WHERE session_id = ?
            GROUP BY decider
            ORDER BY count DESC
        """,
            (session_id,),
        )

        decider_breakdown = {}
        total_conf = 0.0
        conf_count = 0
        for dec_row in cursor.fetchall():
            decider_name = dec_row[0] or "unknown"
            decider_breakdown[decider_name] = dec_row[1]
            if dec_row[2] is not None:
                total_conf += dec_row[2] * dec_row[1]
                conf_count += dec_row[1]

        summary["classification"] = {
            "decider_breakdown": decider_breakdown,
            "avg_confidence": round(total_conf / conf_count, 3) if conf_count > 0 else 0,
        }

        # Add type breakdown
        cursor.execute(
            """
            SELECT
                email_type,
                COUNT(*) as count
            FROM email_threads
            WHERE session_id = ?
            GROUP BY email_type
            ORDER BY count DESC
        """,
            (session_id,),
        )

        type_breakdown = {}
        for type_row in cursor.fetchall():
            type_name = type_row[0] or "unknown"
            type_breakdown[type_name] = type_row[1]

        summary["classification"]["type_breakdown"] = type_breakdown

        # Fetch digest HTML if available
        cursor.execute(
            """
            SELECT digest_html, digest_text
            FROM digest_sessions
            WHERE session_id = ?
        """,
            (session_id,),
        )

        digest_row = cursor.fetchone()
        if digest_row:
            summary["digest_html"] = digest_row[0]
            summary["digest_text"] = digest_row[1]
        return summary

    def get_session_threads(self, session_id: str) -> list[dict[str, Any]]:
        """
        Get all threads for a session

        Returns:
            List of thread dicts with parsed JSON fields

        Side Effects:
            - Reads from email_threads table via SELECT query
        """
        with get_db_connection() as conn:
            conn.row_factory = lambda cursor, row: dict(
                zip([col[0] for col in cursor.description], row, strict=False)
            )
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT * FROM email_threads
                WHERE session_id = ?
                ORDER BY importance DESC, timestamp ASC
            """,
                (session_id,),
            )

            threads = []
            for row in cursor.fetchall():
                thread = row
                # Parse JSON fields
                thread["entity_details"] = (
                    json.loads(thread["entity_details"]) if thread["entity_details"] else None
                )
                threads.append(thread)
            return threads

    def get_unlinked_summaries(self, session_id: str) -> list[dict[str, Any]]:
        """
        Get summary lines without entity links (for debugging)

        Returns:
            List of thread dicts where summary_linked = 0

        Side Effects:
            - Reads from email_threads table via SELECT query
        """
        with get_db_connection() as conn:
            conn.row_factory = lambda cursor, row: dict(
                zip([col[0] for col in cursor.description], row, strict=False)
            )
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT thread_id, subject, summary_line, importance
                FROM email_threads
                WHERE session_id = ?
                  AND summary_line IS NOT NULL
                  AND summary_linked = 0
                ORDER BY importance DESC
            """,
                (session_id,),
            )

            return [row for row in cursor.fetchall()]

    def print_session_report(self, session_id: str) -> None:
        """Print session report - delegates to tracking_reports module."""
        from mailq.observability.tracking_reports import print_session_report

        print_session_report(self, session_id)

    def export_csv(self, session_id: str, output_path: str) -> None:
        """Export to CSV - delegates to tracking_reports module."""
        from mailq.observability.tracking_reports import export_csv

        export_csv(self, session_id, output_path)

    def sync_to_gcs(self, session_id: str, digest_html: str | None = None) -> bool:
        """Sync to GCS - delegates to tracking_reports module."""
        from mailq.observability.tracking_reports import sync_to_gcs

        return sync_to_gcs(self, session_id, digest_html)
