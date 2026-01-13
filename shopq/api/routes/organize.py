"""
Email classification logic for /api/organize endpoint

Uses refactored pipeline (Phase 0-6).
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from datetime import datetime
from typing import Any, NotRequired, TypedDict

from shopq.classification.pipeline_wrapper import classify_batch_refactored
from shopq.observability.confidence import LABEL_CONFIDENCE_MIN, TYPE_CONFIDENCE_MIN
from shopq.observability.logging import get_logger
from shopq.observability.telemetry import log_event
from shopq.observability.tracking import EmailThreadTracker
from shopq.runtime.thresholds import ConfidenceLogger

logger = get_logger(__name__)

# Centralized confidence thresholds
MIN_TYPE_CONF = TYPE_CONFIDENCE_MIN
MIN_LABEL_CONF = LABEL_CONFIDENCE_MIN

# Initialize confidence logger
confidence_logger = ConfidenceLogger()

# Initialize email thread tracker for observability
_tracker: EmailThreadTracker | None = None


def _get_tracker() -> EmailThreadTracker:
    """Lazy-initialize the email thread tracker."""
    global _tracker
    if _tracker is None:
        _tracker = EmailThreadTracker()
    return _tracker


def _get_field(obj: Any, field: str) -> Any:
    """Get field from object or dict."""
    if hasattr(obj, field):
        return getattr(obj, field)
    if hasattr(obj, "get"):
        return obj.get(field)
    return None


class OrganizeStats(TypedDict):
    total: int
    high_confidence: int
    low_confidence: int
    filtered_labels: int
    by_decider: dict[str, int]
    by_type: dict[str, int]
    uncategorized: int
    elapsed_ms: NotRequired[int]


def classify_batch(
    classifier: Any,  # noqa: ARG001 - kept for API compatibility
    emails: list[dict[str, Any]],
    user_prefs: dict[str, Any],  # noqa: ARG001 - kept for API compatibility
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Classify a batch of emails using the refactored pipeline.

    Args:
        classifier: Unused, kept for API compatibility
        emails: List of EmailInput objects
        user_prefs: Unused, kept for API compatibility

    Returns:
        (results, stats) - Classification results and statistics

    Side Effects:
        - Writes classification results to email_threads table via EmailThreadTracker
    """
    logger.info("classify_batch called with %d emails", len(emails))
    log_event("api.organize.start", total=len(emails))
    start_time = time.time()

    # Generate session ID for this organize batch
    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Use refactored pipeline
    logger.info("Starting classify_batch_refactored...")
    results = classify_batch_refactored(emails)
    logger.info("classify_batch_refactored completed with %d results", len(results))

    # Track each classification for observability
    tracker = _get_tracker()
    for i, result in enumerate(results):
        if i >= len(emails):
            break
        email = emails[i]
        try:
            # Extract email fields (handle both dict and object)
            thread_id = _get_field(email, "threadId") or _get_field(email, "id") or ""
            message_id = _get_field(email, "id") or ""
            from_email = _get_field(email, "from") or ""
            subject = _get_field(email, "subject") or ""
            received_date = _get_field(email, "date") or _get_field(email, "internalDate") or ""

            tracker.track_classification(
                thread_id=thread_id,
                message_id=message_id,
                from_email=from_email,
                subject=subject,
                received_date=received_date,
                classification=result,
                importance=result.get("importance", "routine"),
                importance_reason=result.get("reason", ""),
                session_id=session_id,
            )
        except Exception as e:
            logger.warning("Failed to track classification for email %d: %s", i, e)

    # Build stats
    by_decider: dict[str, int] = {}
    by_type: dict[str, int] = {}

    stats = OrganizeStats(
        {
            "total": len(emails),
            "high_confidence": sum(1 for r in results if r.get("type_conf", 0) >= MIN_TYPE_CONF),
            "low_confidence": sum(1 for r in results if r.get("type_conf", 0) < MIN_TYPE_CONF),
            "filtered_labels": 0,
            "by_decider": by_decider,
            "by_type": by_type,
            "uncategorized": sum(
                1 for r in results if r.get("type") == "notification" and not r.get("domains")
            ),
        }
    )

    # Count by decider and type
    for result in results:
        decider = result.get("decider", "unknown")
        stats["by_decider"][decider] = stats["by_decider"].get(decider, 0) + 1
        type_val = result.get("type", "unknown")
        stats["by_type"][type_val] = stats["by_type"].get(type_val, 0) + 1

    elapsed_ms = int((time.time() - start_time) * 1000)
    stats["elapsed_ms"] = elapsed_ms

    # Estimate costs for monitoring
    llm_deciders = {"gemini", "llm", "vertex", "openai"}
    llm_count = sum(
        count for decider, count in stats["by_decider"].items() if decider.lower() in llm_deciders
    )
    estimated_cost_usd = llm_count * 0.001

    log_event(
        "api.organize.success",
        total=len(results),
        elapsed_ms=elapsed_ms,
        deciders=stats["by_decider"],
        high_confidence=stats["high_confidence"],
        low_confidence=stats["low_confidence"],
        llm_count=llm_count,
        estimated_cost_usd=estimated_cost_usd,
    )

    # Cost alert
    if estimated_cost_usd > 0.10:
        log_event(
            "api.organize.cost_alert",
            severity="warning",
            llm_count=llm_count,
            estimated_cost_usd=estimated_cost_usd,
            threshold_usd=0.10,
        )

    # Log confidence scores
    for i, result in enumerate(results):
        email = emails[i] if i < len(emails) else {}
        is_low_conf = result.get("type_conf", 0) < MIN_TYPE_CONF
        try:
            email_id = (
                getattr(email, "id", None) or email.get("id")
                if hasattr(email, "get")
                else getattr(email, "id", None)
            )
            subject = (
                getattr(email, "subject", "")
                if hasattr(email, "subject")
                else email.get("subject", "")
                if hasattr(email, "get")
                else ""
            )
            confidence_logger.log_classification(
                result=result,
                email_id=email_id,
                subject=subject,
                filtered_labels=0,
                notes="low_confidence" if is_low_conf else None,
            )
        except Exception as e:
            log_event("api.organize.confidence_logger_failure", error=str(e))

    _log_summary(stats)
    return results, dict(stats)


def _log_summary(stats: Mapping[str, Any]):
    """Log classification summary"""
    log_event(
        "api.organize.summary",
        total=stats.get("total"),
        elapsed_ms=stats.get("elapsed_ms"),
        high_confidence=stats.get("high_confidence"),
        low_confidence=stats.get("low_confidence"),
        uncategorized=stats.get("uncategorized"),
        filtered_labels=stats.get("filtered_labels"),
        by_decider=stats.get("by_decider"),
        top_types=sorted(stats.get("by_type", {}).items(), key=lambda x: -x[1])[:5],
    )
