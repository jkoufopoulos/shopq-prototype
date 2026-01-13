"""
Session Reporting for Email Thread Tracking.

Provides debug reporting and CSV export functionality.
Extracted from tracking.py to reduce file size.
"""

from __future__ import annotations

import csv
from typing import TYPE_CHECKING

from shopq.observability.logging import get_logger

if TYPE_CHECKING:
    from shopq.observability.tracking import EmailThreadTracker

logger = get_logger(__name__)


def print_session_report(tracker: EmailThreadTracker, session_id: str) -> None:
    """
    Print comprehensive session report (only in DEBUG mode).

    Args:
        tracker: EmailThreadTracker instance to fetch data from
        session_id: Session identifier

    Side Effects:
        - Calls tracker.get_session_summary() and tracker.get_session_threads()
        - Writes multiple log entries to logger if verbose mode enabled
    """
    if not tracker.verbose:
        return  # Skip report in production mode

    summary = tracker.get_session_summary(session_id)
    threads = tracker.get_session_threads(session_id)

    logger.info("\n%s", "=" * 80)
    logger.info("📊 EMAIL TRACKING REPORT - Session: %s", session_id)
    logger.info("%s", "=" * 80)

    logger.info("\n📈 OVERALL STATISTICS")
    logger.info("  Total threads processed: %s", summary["total_threads"])
    logger.info("  Critical: %s", summary["importance"]["critical"])
    logger.info("  Time-sensitive: %s", summary["importance"]["time_sensitive"])
    logger.info("  Routine: %s", summary["importance"]["routine"])
    logger.info(
        "  Entities extracted: %s/%s",
        summary["entities_extracted"],
        summary["total_threads"],
    )
    logger.info(
        "  Verifier used: %s/%s",
        summary["verified_count"],
        summary["total_threads"],
    )

    logger.info("\n🎯 DIGEST BREAKDOWN")
    logger.info("  Featured: %s", summary["digest_breakdown"]["featured"])
    logger.info("  Orphaned: %s", summary["digest_breakdown"]["orphaned"])
    logger.info("  Noise: %s", summary["digest_breakdown"]["noise"])
    logger.info(
        "  Coverage valid: %s",
        "✅" if summary["digest_coverage_valid"] else "❌",
    )

    # Importance reasons
    logger.info("\n💡 IMPORTANCE REASONS")
    importance_reasons: dict[str, int] = {}
    for thread in threads:
        reason = thread["importance_reason"] or "no reason given"
        importance = thread["importance"]
        key = f"{importance}: {reason}"
        importance_reasons[key] = importance_reasons.get(key, 0) + 1

    for reason, count in sorted(importance_reasons.items(), key=lambda x: x[1], reverse=True):
        logger.info("  %sx - %s", count, reason)

    # Entity extraction failures
    no_entity_critical = [
        t
        for t in threads
        if not t["entity_extracted"] and t["importance"] in ["critical", "time_sensitive"]
    ]
    if no_entity_critical:
        logger.warning(
            "\n⚠️  ENTITY EXTRACTION FAILURES (%s important emails)",
            len(no_entity_critical),
        )
        for thread in no_entity_critical[:5]:  # Show first 5
            logger.warning(
                "  - %s: %s",
                thread["importance"],
                thread["subject"][:60],
            )

    # Unlinked summaries
    unlinked = tracker.get_unlinked_summaries(session_id)
    if unlinked:
        logger.error("\n❌ UNLINKED SUMMARY LINES (%s lines)", len(unlinked))
        for item in unlinked[:5]:  # Show first 5
            logger.error("  - %s", item["subject"][:60])
            logger.error("    Summary: %s", item["summary_line"][:80])

    logger.info("\n%s\n", "=" * 80)


def export_csv(tracker: EmailThreadTracker, session_id: str, output_path: str) -> None:
    """
    Export session data to CSV for analysis.

    Args:
        tracker: EmailThreadTracker instance to fetch data from
        session_id: Session identifier
        output_path: Path to write CSV file

    Side Effects:
        - Writes CSV file to output_path
        - Calls tracker.get_session_threads() to fetch data
        - Logs to logger on success/warning
    """
    threads = tracker.get_session_threads(session_id)

    if not threads:
        logger.warning("No threads found for session %s", session_id)
        return

    fieldnames = [
        "thread_id",
        "subject",
        "from_email",
        "received_date",
        "email_type",
        "type_confidence",
        "importance",
        "importance_reason",
        "decider",
        "verifier_used",
        "verifier_verdict",
        "entity_extracted",
        "entity_type",
        "entity_confidence",
        "in_featured",
        "in_orphaned",
        "in_noise",
        "noise_category",
        "summary_line",
        "summary_linked",
    ]

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(threads)

    logger.info("Exported %s threads to %s", len(threads), output_path)


def sync_to_gcs(
    tracker: EmailThreadTracker,  # noqa: ARG001 - kept for API consistency
    session_id: str,
    digest_html: str | None = None,
) -> bool:
    """
    Sync tracking data to GCS for persistent storage.

    Uploads:
    - SQLite database file (contains all tracking data)
    - Digest HTML (if provided)

    This enables quality monitoring across Cloud Run container restarts.

    Args:
        tracker: EmailThreadTracker instance (not used but kept for API consistency)
        session_id: Session identifier
        digest_html: Optional digest HTML content

    Returns:
        True if sync succeeded, False otherwise

    Side Effects:
        - Uploads files to Google Cloud Storage
        - Logs to logger on success/warning/error
    """
    try:
        from shopq.infrastructure.database import get_db_path
        from shopq.storage.cloud import get_storage_client

        storage_client = get_storage_client()

        # Upload SQLite database
        db_uploaded = storage_client.upload_session_db(session_id, str(get_db_path()))  # type: ignore[no-untyped-call]

        # Upload digest HTML if provided
        html_uploaded = True
        if digest_html:
            html_uploaded = storage_client.upload_digest_html(session_id, digest_html)

        success = db_uploaded and html_uploaded
        if success:
            logger.info(
                "Synced session %s to GCS (db=%s, html=%s)",
                session_id,
                db_uploaded,
                html_uploaded,
            )
        else:
            logger.warning(
                "Partial GCS sync for %s (db=%s, html=%s)",
                session_id,
                db_uploaded,
                html_uploaded,
            )

        return success

    except Exception as e:
        logger.error("Failed to sync %s to GCS: %s", session_id, e)
        return False
