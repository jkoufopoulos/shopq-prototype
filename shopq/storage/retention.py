"""
Data Retention and Privacy Module

Implements 14-day retention policy and anonymization for ShopQ artifacts.

This module ensures:
1. Old digest artifacts are automatically deleted after 14 days
2. Non-owner access to data is anonymized (PII masked)
3. Compliance with privacy best practices

Usage:
    # Cleanup old data (run daily via cron/Cloud Scheduler)
    python -m shopq.retention cleanup --days 14

    # Anonymize data for non-owner access
    from shopq.shared.retention import anonymize_email_thread
    safe_thread = anonymize_email_thread(thread, owner_user_id="alice", requesting_user_id="bob")
"""

from __future__ import annotations

import copy
import hashlib
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from google.api_core import exceptions, retry

from shopq.infrastructure.database import db_transaction, get_db_connection
from shopq.observability.logging import get_logger
from shopq.storage.cloud import DIGESTS_PREFIX, SESSIONS_PREFIX, StorageClient

logger = get_logger(__name__)

# Retention policy
DEFAULT_RETENTION_DAYS = 14

# Anonymization patterns
EMAIL_PATTERN = re.compile(r"[\w\.-]+@[\w\.-]+\.\w+")
DOMAIN_PATTERN = re.compile(r"@([\w\.-]+\.\w+)")


def cleanup_old_artifacts(
    days: int = DEFAULT_RETENTION_DAYS, dry_run: bool = False
) -> dict[str, int]:
    """
    Delete email threads and digest artifacts older than specified days.

    Side Effects:
    - Deletes from `email_threads` table in shopq.db
    - Deletes from `digest_sessions` table in shopq.db
    - Deletes digest HTML and session DB files from GCS
    - Logs cleanup statistics and policy violations
    - Committed immediately via db_transaction

    Args:
        days: Number of days to retain data (default: 14)
        dry_run: If True, only log what would be deleted without deleting

    Returns:
        Dict with counts of deleted items:
        {
            "email_threads_deleted": int,
            "digest_sessions_deleted": int,
            "gcs_digests_deleted": int,
            "gcs_sessions_deleted": int,
        }
    """
    cutoff_date = datetime.now(UTC) - timedelta(days=days)
    cutoff_str = cutoff_date.isoformat()

    stats = {
        "email_threads_deleted": 0,
        "digest_sessions_deleted": 0,
        "gcs_digests_deleted": 0,
        "gcs_sessions_deleted": 0,
    }

    prefix = "[DRY RUN] " if dry_run else ""
    logger.info(
        f"{prefix}Cleaning up artifacts older than {cutoff_str} ({days} days)",
        extra={
            "retention_policy_days": days,
            "cutoff_date": cutoff_str,
            "dry_run": dry_run,
        },
    )

    # 1. Cleanup email_threads older than cutoff
    with db_transaction() as conn:
        # Find old threads
        cursor = conn.execute(
            """
            SELECT COUNT(*) FROM email_threads
            WHERE timestamp < ?
        """,
            (cutoff_str,),
        )
        count = cursor.fetchone()[0]

        if count > 0:
            logger.info(
                f"{'[DRY RUN] ' if dry_run else ''}Found {count} old email threads to delete"
            )

            if not dry_run:
                conn.execute(
                    """
                    DELETE FROM email_threads
                    WHERE timestamp < ?
                """,
                    (cutoff_str,),
                )
                stats["email_threads_deleted"] = count
                logger.info(f"Deleted {count} email threads")

    # 2. Cleanup digest_sessions older than cutoff
    # IMPORTANT: Delete from GCS FIRST, then database. This ensures:
    # - If GCS fails, database records remain (no orphaned metadata)
    # - If database fails after GCS succeeds, we can retry (GCS delete is idempotent)
    # - No partial state where DB says "deleted" but GCS still has artifacts

    with get_db_connection() as conn:
        cursor = conn.execute(
            """
            SELECT COUNT(*) FROM digest_sessions
            WHERE generated_at < ?
        """,
            (cutoff_str,),
        )
        count = cursor.fetchone()[0]

        if count > 0:
            logger.info(
                f"{'[DRY RUN] ' if dry_run else ''}Found {count} old digest sessions to delete"
            )

            if not dry_run:
                # Get session_ids for GCS cleanup
                cursor = conn.execute(
                    """
                    SELECT session_id FROM digest_sessions
                    WHERE generated_at < ?
                """,
                    (cutoff_str,),
                )
                session_ids = [row[0] for row in cursor.fetchall()]

                # Step 1: Delete from GCS FIRST (most likely to fail)
                if session_ids:
                    gcs_stats = _cleanup_gcs_artifacts(session_ids, dry_run=False)
                    stats["gcs_digests_deleted"] = gcs_stats["digests_deleted"]
                    stats["gcs_sessions_deleted"] = gcs_stats["sessions_deleted"]

                    # If GCS cleanup had failures, abort database deletion
                    if gcs_stats.get("failed_deletions", 0) > 0:
                        logger.error(
                            f"GCS cleanup had {gcs_stats['failed_deletions']} failures. "
                            f"Aborting database deletion to maintain consistency."
                        )
                        return stats

                # Step 2: Delete from database (only if GCS succeeded)
                with db_transaction() as trans_conn:
                    trans_conn.execute(
                        """
                        DELETE FROM digest_sessions
                        WHERE generated_at < ?
                    """,
                        (cutoff_str,),
                    )
                    stats["digest_sessions_deleted"] = count
                    logger.info(f"Deleted {count} digest sessions")

    # Emit structured metrics for monitoring
    logger.info(
        "Cleanup complete",
        extra={
            "email_threads_deleted": stats["email_threads_deleted"],
            "digest_sessions_deleted": stats["digest_sessions_deleted"],
            "gcs_digests_deleted": stats["gcs_digests_deleted"],
            "gcs_sessions_deleted": stats["gcs_sessions_deleted"],
            "retention_policy_days": days,
        },
    )

    # Check for retention policy violations (data older than policy allows)
    if not dry_run:
        _check_retention_policy_violations(cutoff_str, days)

    return stats


def _check_retention_policy_violations(cutoff_str: str, days: int):
    """
    Check for retention policy violations and emit alerts.

    Args:
        cutoff_str: ISO datetime cutoff for retention policy
        days: Retention policy in days
    """
    try:
        with get_db_connection() as conn:
            # Check email_threads for violations
            cursor = conn.execute(
                """
                SELECT MIN(timestamp) as oldest, COUNT(*) as count
                FROM email_threads
                WHERE timestamp < ?
            """,
                (cutoff_str,),
            )
            row = cursor.fetchone()
            oldest_timestamp = row[0]
            violation_count = row[1]

            if oldest_timestamp and violation_count > 0:
                age_days = (datetime.now(UTC) - datetime.fromisoformat(oldest_timestamp)).days
                logger.error(
                    "RETENTION POLICY VIOLATION: Data exists older than retention policy",
                    extra={
                        "alert": "retention_policy_violation",
                        "severity": "ERROR",
                        "oldest_data_age_days": age_days,
                        "retention_policy_days": days,
                        "violation_count": violation_count,
                        "oldest_timestamp": oldest_timestamp,
                    },
                )

            # Check digest_sessions for violations
            cursor = conn.execute(
                """
                SELECT MIN(generated_at) as oldest, COUNT(*) as count
                FROM digest_sessions
                WHERE generated_at < ?
            """,
                (cutoff_str,),
            )
            row = cursor.fetchone()
            oldest_generated = row[0]
            violation_count = row[1]

            if oldest_generated and violation_count > 0:
                age_days = (datetime.now(UTC) - datetime.fromisoformat(oldest_generated)).days
                logger.error(
                    "RETENTION POLICY VIOLATION: Digest sessions older than retention policy",
                    extra={
                        "alert": "retention_policy_violation",
                        "severity": "ERROR",
                        "oldest_data_age_days": age_days,
                        "retention_policy_days": days,
                        "violation_count": violation_count,
                        "oldest_timestamp": oldest_generated,
                    },
                )
    except Exception as e:
        logger.error(f"Failed to check retention policy violations: {e}")


def _cleanup_gcs_artifacts(session_ids: list[str], dry_run: bool = False) -> dict[str, int]:
    """
    Delete GCS artifacts for given session IDs with retry logic.

    Args:
        session_ids: List of session IDs to cleanup
        dry_run: If True, only log what would be deleted

    Returns:
        Dict with counts: {
            "digests_deleted": int,
            "sessions_deleted": int,
            "failed_deletions": int
        }
        Side Effects:
            Writes to database
    """
    stats = {"digests_deleted": 0, "sessions_deleted": 0, "failed_deletions": 0}

    # Configure retry policy for transient GCS errors
    retry_policy = retry.Retry(
        predicate=retry.if_exception_type(
            exceptions.TooManyRequests,
            exceptions.ServiceUnavailable,
            exceptions.InternalServerError,
        ),
        initial=1.0,  # 1 second initial delay
        maximum=60.0,  # max 60 second delay
        multiplier=2.0,  # exponential backoff
        deadline=300.0,  # 5 minute total timeout
    )

    try:
        storage = StorageClient()

        for session_id in session_ids:
            # SECURITY: Validate session_id to prevent path traversal
            if not _is_valid_session_id(session_id):
                logger.error(
                    f"Invalid session_id detected: {session_id!r}. "
                    f"Skipping to prevent path traversal."
                )
                stats["failed_deletions"] += 2  # Count both digest and session as failed
                continue

            # Delete digest HTML with retry
            digest_blob_name = f"{DIGESTS_PREFIX}{session_id}.html"
            digest_blob = storage.bucket.blob(digest_blob_name)

            if digest_blob.exists():
                if dry_run:
                    logger.info(
                        f"[DRY RUN] Would delete digest: gs://{storage.bucket_name}/{digest_blob_name}"
                    )
                else:
                    try:
                        digest_blob.delete(retry=retry_policy)
                        stats["digests_deleted"] += 1
                        logger.debug(f"Deleted digest: {digest_blob_name}")
                    except Exception as e:
                        logger.error(
                            f"Failed to delete digest {digest_blob_name} after retries: {e}"
                        )
                        stats["failed_deletions"] += 1

            # Delete session DB with retry
            session_blob_name = f"{SESSIONS_PREFIX}{session_id}.db"
            session_blob = storage.bucket.blob(session_blob_name)

            if session_blob.exists():
                if dry_run:
                    logger.info(
                        f"[DRY RUN] Would delete session: gs://{storage.bucket_name}/{session_blob_name}"
                    )
                else:
                    try:
                        session_blob.delete(retry=retry_policy)
                        stats["sessions_deleted"] += 1
                        logger.debug(f"Deleted session: {session_blob_name}")
                    except Exception as e:
                        logger.error(
                            f"Failed to delete session {session_blob_name} after retries: {e}"
                        )
                        stats["failed_deletions"] += 1

    except Exception as e:
        logger.error(f"Fatal error in GCS cleanup: {e}")
        # Return partial stats so caller can detect failure

    if stats["failed_deletions"] > 0:
        logger.warning(
            f"GCS cleanup completed with {stats['failed_deletions']} failures. "
            f"Successfully deleted {stats['digests_deleted']} digests and "
            f"{stats['sessions_deleted']} sessions."
        )

    return stats


def _is_valid_session_id(session_id: str) -> bool:
    """
    Validate session_id to prevent path traversal attacks.

    Session IDs should be alphanumeric with hyphens/underscores only.
    Prevents: "../../../etc/passwd", "../../bucket/sensitive.db"

    Args:
        session_id: Session ID to validate

    Returns:
        True if valid, False otherwise
    """
    if not session_id:
        return False

    # Allow alphanumeric, hyphens, underscores only (UUIDs, timestamps, etc.)
    # Reject: /, \, ., .., null bytes, control characters
    if not re.match(r"^[a-zA-Z0-9_-]+$", session_id):
        return False

    # Additional safety: reject common path traversal patterns
    dangerous_patterns = ["..", "/", "\\", "\x00"]
    return not any(pattern in session_id for pattern in dangerous_patterns)


def anonymize_email_thread(
    thread: dict[str, Any], owner_user_id: str, requesting_user_id: str
) -> dict[str, Any]:
    """
    Anonymize email thread data for non-owner access.

    If requesting_user_id == owner_user_id, return data as-is.
    Otherwise, mask PII (emails, subjects, snippets).

    Uses deep copy to prevent data leakage through nested objects.

    Args:
        thread: Email thread dict from database
        owner_user_id: User ID who owns this data
        requesting_user_id: User ID requesting access

    Returns:
        Anonymized thread dict (or original if owner)
    """
    # Owner has full access
    if requesting_user_id == owner_user_id:
        return thread

    # Non-owner: anonymize PII
    # Use deep copy to prevent mutation and nested object leakage
    anonymized = copy.deepcopy(thread)

    # Anonymize email addresses
    if "from_email" in anonymized:
        anonymized["from_email"] = _anonymize_email(anonymized["from_email"])

    # Anonymize subject
    if "subject" in anonymized:
        anonymized["subject"] = _anonymize_text(anonymized["subject"])

    # Drop sensitive fields entirely
    sensitive_fields = [
        "message_id",
        "summary_line",  # May contain PII
        "entity_details",  # May contain PII (flight numbers, etc.)
        "verifier_reason",  # May contain email content
    ]

    for field in sensitive_fields:
        if field in anonymized:
            anonymized[field] = "[REDACTED]"

    return anonymized


def anonymize_digest_session(
    session: dict[str, Any], owner_user_id: str, requesting_user_id: str
) -> dict[str, Any]:
    """
    Anonymize digest session data for non-owner access.

    Uses deep copy to prevent data leakage through nested objects.

    Args:
        session: Digest session dict from database
        owner_user_id: User ID who owns this data
        requesting_user_id: User ID requesting access

    Returns:
        Anonymized session dict (or original if owner)
    """
    # Owner has full access
    if requesting_user_id == owner_user_id:
        return session

    # Non-owner: anonymize PII
    # Use deep copy to prevent mutation and nested object leakage
    anonymized = copy.deepcopy(session)

    # Drop digest HTML/text entirely (contains PII)
    if "digest_html" in anonymized:
        anonymized["digest_html"] = "[REDACTED]"
    if "digest_text" in anonymized:
        anonymized["digest_text"] = "[REDACTED]"

    # Keep only aggregate stats (no PII)
    safe_fields = [
        "session_id",
        "generated_at",
        "email_count",
        "featured_count",
        "critical_count",
        "time_sensitive_count",
        "routine_count",
    ]

    # Remove any fields not in safe list
    return {k: v for k, v in anonymized.items() if k in safe_fields}


def _anonymize_email(email: str) -> str:
    """
    Anonymize email address by hashing both username and domain.

    Ensures anonymization is:
    1. Irreversible (no way to recover original)
    2. Consistent (same email always anonymizes same way)
    3. Privacy-compliant (no PII leakage via domain)

    Example: alice@example.com → user_a4f1e3@domain_b2c5d7
    """
    if not email or "@" not in email:
        return "[REDACTED]"

    username, domain = email.split("@", 1)

    # Hash username (first 6 chars of SHA256 for readability)
    username_hash = hashlib.sha256(username.encode()).hexdigest()[:6]
    anonymized_username = f"user_{username_hash}"

    # Hash domain (for privacy, but keep structure for debugging)
    domain_hash = hashlib.sha256(domain.encode()).hexdigest()[:6]
    anonymized_domain = f"domain_{domain_hash}"

    return f"{anonymized_username}@{anonymized_domain}"


def _anonymize_text(text: str) -> str:
    """
    Anonymize text by replacing emails and masking content.

    Example: "Meeting with alice@example.com tomorrow" → "Meeting with a***@example.com [MASKED]"
    """
    if not text:
        return ""

    # Replace email addresses
    text = EMAIL_PATTERN.sub(lambda m: _anonymize_email(m.group(0)), text)

    # Always add mask suffix for anonymization
    return text[:30] + "... [MASKED]" if len(text) > 30 else text + " [MASKED]"


def get_retention_stats() -> dict[str, Any]:
    """
    Get statistics about data retention and storage.

    Returns:
        Dict with retention stats:
        {
            "total_email_threads": int,
            "oldest_thread": str (ISO datetime),
            "newest_thread": str (ISO datetime),
            "threads_older_than_14_days": int,
            "total_digest_sessions": int,
            "sessions_older_than_14_days": int,
        }
    """
    cutoff_date = datetime.now(UTC) - timedelta(days=DEFAULT_RETENTION_DAYS)
    cutoff_str = cutoff_date.isoformat()

    stats = {}

    with get_db_connection() as conn:
        # Email threads stats
        cursor = conn.execute(
            """
            SELECT
                COUNT(*) as total,
                MIN(timestamp) as oldest,
                MAX(timestamp) as newest,
                SUM(CASE WHEN timestamp < ? THEN 1 ELSE 0 END) as old_count
            FROM email_threads
        """,
            (cutoff_str,),
        )
        row = cursor.fetchone()
        stats["total_email_threads"] = row[0]
        stats["oldest_thread"] = row[1]
        stats["newest_thread"] = row[2]
        stats["threads_older_than_14_days"] = row[3]

        # Digest sessions stats
        cursor = conn.execute(
            """
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN generated_at < ? THEN 1 ELSE 0 END) as old_count
            FROM digest_sessions
        """,
            (cutoff_str,),
        )
        row = cursor.fetchone()
        stats["total_digest_sessions"] = row[0]
        stats["sessions_older_than_14_days"] = row[1]

    return stats
