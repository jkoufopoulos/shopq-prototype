"""

from __future__ import annotations

Debug endpoints for monitoring classification batches and digest generation
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Query

router = APIRouter(prefix="/api/debug", tags=["debug"])

# Global state for last batch (injected by main app)
last_batch_store: dict = {"timestamp": None, "results": [], "stats": {}}

# Global state for last digest generation (injected by context digest generation)
last_digest_store: dict = {
    "timestamp": None,
    "total_ranked": 0,
    "filtered_remaining": 0,
    "featured": [],
    "all_entities": [],
    "importance_groups": {},
    "all_emails": [],
    "noise_breakdown": {},
}


def set_last_batch(batch: dict[str, Any]) -> None:
    """Update last batch (called from main app)

    Side Effects:
        - Modifies global variable `last_batch_store` (in-memory state)
    """
    global last_batch_store
    last_batch_store = batch


def set_last_digest(digest_data: dict[str, Any]) -> None:
    """Update last digest data (called from context digest generation)

    Side Effects:
        - Modifies global variable `last_digest_store` (in-memory state)
    """
    global last_digest_store
    last_digest_store = {"timestamp": datetime.now().isoformat(), **digest_data}


@router.get("/last-batch")
async def get_last_batch() -> dict[str, Any]:
    """
    Get detailed results from the last classification batch.
    Useful for debugging without checking logs.

    Side Effects:
        None (reads from in-memory last_batch_store only)
    """
    if not last_batch_store["timestamp"]:
        return {"error": "No classifications yet", "message": "Run /api/organize first"}

    return last_batch_store


@router.get("/last-batch/summary")
async def get_last_batch_summary() -> dict[str, Any]:
    """Get a formatted summary of the last batch

    Side Effects:
        None (pure function - builds local data structures only)
    """
    if not last_batch_store["timestamp"]:
        return {"error": "No classifications yet"}

    batch = last_batch_store

    # Group by label
    label_counts: dict[str, int] = {}
    for result in batch["results"]:
        for label in result["labels"]:
            label_counts[label] = label_counts.get(label, 0) + 1

    # Format output
    return {
        "timestamp": batch["timestamp"],
        "total_emails": batch["stats"]["total"],
        "elapsed_ms": batch["elapsed_ms"],
        "confidence": {
            "high": (
                f"{batch['stats']['high_confidence']} ("
                f"{batch['stats']['high_confidence'] / batch['stats']['total'] * 100:.1f}%)"
            ),
            "low": (
                f"{batch['stats']['low_confidence']} ("
                f"{batch['stats']['low_confidence'] / batch['stats']['total'] * 100:.1f}%)"
            ),
        },
        "uncategorized": (
            f"{batch['stats']['uncategorized']} ("
            f"{batch['stats']['uncategorized'] / batch['stats']['total'] * 100:.1f}%)"
        ),
        "labels_applied": sorted(label_counts.items(), key=lambda x: -x[1]),
        "by_decider": batch["stats"]["by_decider"],
        "by_type": dict(sorted(batch["stats"]["by_type"].items(), key=lambda x: -x[1])[:10]),
    }


@router.get("/last-batch/detailed")
async def get_last_batch_detailed() -> dict[str, Any]:
    """Get full detailed results in a readable format

    Side Effects:
        None (pure function - builds local data structures only)
    """
    if not last_batch_store["timestamp"]:
        return {"error": "No classifications yet"}

    batch = last_batch_store

    # Format each email nicely
    formatted = []
    for i, result in enumerate(batch["results"], 1):
        formatted.append(
            {
                "number": i,
                "from": result["from"],
                "labels": result["labels"],
                "confidence": f"{result['confidence']:.2f}",
                "decider": result["decider"],
            }
        )

    return {
        "timestamp": batch["timestamp"],
        "total": batch["stats"]["total"],
        "elapsed_ms": batch["elapsed_ms"],
        "emails": formatted,
        "stats": batch["stats"],
    }


# ============================================================================
# DIGEST DEBUG ENDPOINTS
# ============================================================================


@router.get("/featured-selection")
async def get_featured_selection() -> dict[str, Any]:
    """
    Introspect Stage1→Stage2→Stage3 pipeline and show why items were featured.

    Shows:
    - Total entities ranked
    - Filtered remaining after selection
    - Featured entities with scores and reasons
    - Top 15 candidates for comparison

    Side Effects:
        None (pure function - builds local data structures only)
    """
    if not last_digest_store["timestamp"]:
        return {
            "error": "No digest generated yet",
            "message": "Generate a digest first using the extension",
        }

    # Extract featured entities with scores
    featured = []
    for entity in last_digest_store.get("featured", []):
        featured.append(
            {
                "id": getattr(entity, "source_email_id", "unknown"),
                "threadId": getattr(entity, "source_email_id", "unknown"),
                "subject": _get_entity_title(entity),
                "from": "N/A",  # Entities don't have 'from' field directly
                "attention_score": 1.0
                if entity.importance == "critical"
                else 0.7
                if entity.importance == "time_sensitive"
                else 0.3,
                "contextual_score": getattr(entity, "priority_score", 0.0),
                "labels": [f"MailQ-{entity.importance.title()}"],
                "reason": f"{entity.importance} importance, confidence={entity.confidence:.2f}",
            }
        )

    # Get all entities as candidates
    all_entities = last_digest_store.get("all_entities", [])
    top15_candidates = []
    for entity in sorted(
        all_entities, key=lambda e: getattr(e, "priority_score", 0.0), reverse=True
    )[:15]:
        top15_candidates.append(
            {
                "id": getattr(entity, "source_email_id", "unknown"),
                "subject": _get_entity_title(entity),
                "attention_score": 1.0
                if entity.importance == "critical"
                else 0.7
                if entity.importance == "time_sensitive"
                else 0.3,
                "contextual_score": getattr(entity, "priority_score", None),
            }
        )

    return {
        "total_ranked": len(all_entities),
        "filtered_remaining": len(all_entities) - len(featured),
        "featured": featured,
        "top15_candidates": top15_candidates,
    }


@router.get("/category-summary")
async def get_category_summary(newer_than_days: int = Query(default=1)) -> dict[str, Any]:
    """
    Show which emails fell into each category bucket used by the bottom summaries.

    Groups emails by importance classification and provides Gmail search queries.

    Side Effects:
        None (reads from in-memory last_digest_store only)
    """
    if not last_digest_store["timestamp"]:
        return {
            "error": "No digest generated yet",
            "message": "Generate a digest first",
        }

    importance_groups = last_digest_store.get("importance_groups", {})

    categories = []
    for importance_level, emails in importance_groups.items():
        sample_subjects = [email.get("subject", "No subject")[:80] for email in emails[:5]]
        sample_threadIds = [email.get("thread_id", email.get("id", "")) for email in emails[:5]]

        # Build Gmail search query
        label_name = f"MailQ-{importance_level.title()}"
        gmail_query = f"label:{label_name} in:anywhere newer_than:{newer_than_days}d"

        categories.append(
            {
                "key": importance_level,
                "count": len(emails),
                "sample_subjects": sample_subjects,
                "sample_threadIds": sample_threadIds,
                "gmail_search_query": gmail_query,
            }
        )

    return {"categories": categories}


@router.get("/label-counts")
async def get_label_counts(
    labels: list[str] = Query(  # noqa: B008
        default=["MailQ-Everything-Else"],  # noqa: B008
    ),
    newer_than_days: int = Query(default=1),
) -> dict[str, Any]:
    """
    Compare digest summary counts vs live Gmail counts for the bottom links.

    NOTE: This endpoint returns computed counts only. For live Gmail API counts,
    you would need to integrate with the Gmail API (requires OAuth token from extension).

    Side Effects:
        None (reads from in-memory last_digest_store only)
    """
    if not last_digest_store["timestamp"]:
        return {
            "error": "No digest generated yet",
            "message": "Generate a digest first",
        }

    # Count emails by label from the last digest data
    all_emails = last_digest_store.get("all_emails", [])

    gmail_counts = []
    digest_reported_total = 0

    for label in labels:
        # Build Gmail search query
        query = f"label:{label} in:anywhere newer_than:{newer_than_days}d"

        # Count in local data (proxy for digest reported count)
        # This is a simplification - in reality we'd need the actual label data
        count = len([e for e in all_emails if label in e.get("labels", [])])

        gmail_counts.append({"label": label, "query": query, "count": count})

        digest_reported_total += count

    # Note: discrepancy = 0 since we're using the same data source
    # In a real implementation, this would query Gmail API for live counts

    return {
        "computed_at": datetime.now().isoformat(),
        "gmail_counts": gmail_counts,
        "digest_reported_total": digest_reported_total,
        "discrepancy": 0,
        "note": "Live Gmail API integration required for accurate discrepancy detection",
    }


@router.get("/missed-featured")
async def get_missed_featured(k: int = Query(default=15)) -> dict[str, Any]:
    """
    Reveal high-scoring emails that were NOT selected for Featured (false negatives).

    Shows entities that scored high but didn't make the cut, with reasons why.

    Side Effects:
        None (reads from in-memory last_digest_store only)
    """
    if not last_digest_store["timestamp"]:
        return {
            "error": "No digest generated yet",
            "message": "Generate a digest first",
        }

    all_entities = last_digest_store.get("all_entities", [])
    featured = last_digest_store.get("featured", [])
    featured_ids = set([getattr(e, "source_email_id", "") for e in featured])

    # Find cutoff score (lowest featured entity score)
    if featured:
        cutoff_contextual_score = min([getattr(e, "priority_score", 0.0) for e in featured])
    else:
        cutoff_contextual_score = 0.0

    # Find high-scoring entities that were missed
    missed = []
    for entity in sorted(
        all_entities, key=lambda e: getattr(e, "priority_score", 0.0), reverse=True
    )[:k]:
        email_id = getattr(entity, "source_email_id", "")
        if email_id not in featured_ids:
            # Determine why it was excluded
            reason_excluded = "diversity_balance"
            if entity.importance == "routine":
                reason_excluded = "hard_filter:routine_importance"
            elif getattr(entity, "priority_score", 0.0) < cutoff_contextual_score:
                reason_excluded = "below_cutoff_score"

            missed.append(
                {
                    "id": email_id,
                    "subject": _get_entity_title(entity),
                    "contextual_score": getattr(entity, "priority_score", 0.0),
                    "reason_excluded": reason_excluded,
                }
            )

    return {
        "cutoff_contextual_score": cutoff_contextual_score,
        "featured_ids": list(featured_ids),
        "missed": missed,
    }


@router.get("/digest-snapshot")
async def get_digest_snapshot(batch_id: str | None = Query(default=None)) -> dict[str, Any]:
    """
    Single payload containing everything needed to audit a given digest run.

    Combines featured selection, category summary, and label counts in one response.

    Side Effects:
        None (reads from in-memory last_digest_store only, calls other read-only endpoints)
    """
    if not last_digest_store["timestamp"]:
        return {
            "error": "No digest generated yet",
            "message": "Generate a digest first",
        }

    # Get featured selection data
    featured_data = await get_featured_selection()

    # Get category summary data
    category_data = await get_category_summary()

    # Get label counts data
    label_counts_data = await get_label_counts()

    # Build comprehensive snapshot
    return {
        "header": {
            "day": datetime.now().strftime("%A, %B %d, %Y"),
            "generated_at": last_digest_store["timestamp"],
            "batch_id": batch_id or f"digest_{last_digest_store['timestamp']}",
        },
        "featured": featured_data.get("featured", []),
        "bottom_links": {
            "reported_counts": {
                "critical": len(last_digest_store.get("importance_groups", {}).get("critical", [])),
                "time_sensitive": len(
                    last_digest_store.get("importance_groups", {}).get("time_sensitive", [])
                ),
                "routine": len(last_digest_store.get("importance_groups", {}).get("routine", [])),
            },
            "live_counts": label_counts_data.get("gmail_counts", []),
            "discrepancy": label_counts_data.get("discrepancy", 0),
        },
        "categories": category_data.get("categories", []),
        "notes": [
            f"Total emails processed: {len(last_digest_store.get('all_emails', []))}",
            f"Entities extracted: {len(last_digest_store.get('all_entities', []))}",
            f"Featured entities: {len(last_digest_store.get('featured', []))}",
            f"Noise breakdown: {last_digest_store.get('noise_breakdown', {})}",
        ],
    }


def _get_entity_title(entity) -> str:
    """Extract a readable title from an entity

    Side Effects:
        None (pure function - only reads entity attributes)
    """
    if hasattr(entity, "title"):
        return entity.title
    if hasattr(entity, "flight_number"):
        return f"Flight {entity.flight_number}"
    if hasattr(entity, "action"):
        return entity.action
    if hasattr(entity, "amount"):
        return f"Payment: ${entity.amount}"
    return f"{entity.__class__.__name__}"


# ============================================================================
# FEATURE FLAGS DEBUG ENDPOINTS
# ============================================================================


@router.get("/feature-flags")
async def get_feature_flags() -> dict[str, Any]:
    """
    Get status of all feature flags and their configuration.

    Shows:
    - Flag name and description
    - Current rollout percentage
    - Explicit override status (if any)
    - Whether flag is enabled for a given user_id (if provided)

    Side Effects:
        None (reads feature flag configuration from environment variables)
    """
    from mailq.runtime.flags import get_feature_flags

    flags = get_feature_flags()
    all_flags = flags.get_all_flags()

    result = []
    for flag_name, config in all_flags.items():
        flag_status = {
            "name": flag_name,
            "description": config.get("description", "No description"),
            "rollout_percentage": config.get("rollout_percentage", 0),
            "explicit_override": config.get("enabled"),  # None, True, or False
            "status": "enabled_all"
            if config.get("enabled") is True
            else "disabled_all"
            if config.get("enabled") is False
            else "percentage_based",
        }
        result.append(flag_status)

    return {
        "timestamp": datetime.now().isoformat(),
        "flags": result,
        "note": "Use ?user_id=xxx to test flag status for a specific user",
    }


@router.get("/feature-flags/{flag_name}")
async def check_feature_flag(
    flag_name: str, user_id: str | None = Query(default=None)
) -> dict[str, Any]:
    """
    Check if a specific feature flag is enabled for a given user.

    Args:
        flag_name: Name of the feature flag (e.g., "DIGEST_V2")
        user_id: Optional user identifier for consistent targeting

    Returns:
        Flag status and whether it's enabled for the given user

    Side Effects:
        None (reads feature flag configuration from environment variables)
    """
    from mailq.runtime.flags import get_feature_flags

    flags = get_feature_flags()

    # Check if flag exists
    all_flags = flags.get_all_flags()
    if flag_name not in all_flags:
        return {
            "error": f"Flag '{flag_name}' not found",
            "available_flags": list(all_flags.keys()),
        }

    config = all_flags[flag_name]

    # Check if enabled for user
    is_enabled = flags.is_enabled(flag_name, user_id=user_id)

    return {
        "flag_name": flag_name,
        "description": config.get("description", "No description"),
        "user_id": user_id,
        "is_enabled": is_enabled,
        "configuration": {
            "rollout_percentage": config.get("rollout_percentage", 0),
            "explicit_override": config.get("enabled"),
        },
        "decision_reason": _get_flag_decision_reason(config, user_id, is_enabled),
    }


def _get_flag_decision_reason(config: dict, user_id: str | None, is_enabled: bool) -> str:
    """Get human-readable reason for flag decision"""
    if config.get("enabled") is True:
        return "Explicitly enabled (FORCE_*=true)"
    if config.get("enabled") is False:
        return "Explicitly disabled (FORCE_*=false)"
    if config.get("rollout_percentage", 0) == 0:
        return "0% rollout"
    if config.get("rollout_percentage", 0) >= 100:
        return "100% rollout"
    if user_id:
        if is_enabled:
            return f"User hash falls within {config.get('rollout_percentage')}% rollout"
        return f"User hash falls outside {config.get('rollout_percentage')}% rollout"
    pct = config.get("rollout_percentage")
    return f"No user_id provided, defaulting to disabled for {pct}% rollout"


# A/B Testing endpoints moved to debug_ab_testing.py
