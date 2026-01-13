"""

from __future__ import annotations

Test Mode API - Endpoints for development and testing

Provides utilities to:
- Clear all ShopQ labels from emails
- Reset learned patterns and corrections
- Disable feedback/learning during testing
"""

import os
from typing import Any

from fastapi import APIRouter, HTTPException

from shopq.infrastructure.database import db_transaction

router = APIRouter(prefix="/api/test", tags=["testing"])


# Check if test mode is enabled
def is_test_mode_enabled() -> bool:
    """
    Check if test mode is enabled via:
    1. Feature gate (runtime, preferred)
    2. TEST_MODE environment variable (legacy)
    """
    from shopq.runtime.gates import feature_gates

    # Check feature gate first (runtime toggleable)
    if feature_gates.is_enabled("test_mode"):
        return True

    # Fall back to environment variable (requires restart)
    return os.getenv("TEST_MODE", "false").lower() == "true"


@router.get("/mode")
async def get_test_mode() -> dict[str, Any]:
    """Check if test mode is enabled"""
    enabled = is_test_mode_enabled()
    return {
        "test_mode_enabled": enabled,
        "message": "Test mode is enabled - feedback/learning disabled"
        if enabled
        else "Test mode is disabled - normal operation",
    }


@router.post("/reset")
async def reset_learning() -> dict[str, Any]:
    """
    Clear all learned patterns and corrections.
    Use this to reset the learning system during testing.

    WARNING: This deletes all user corrections and learned patterns!
    Only use in development/testing.

    Side Effects:
        - Deletes from corrections, learned_patterns, feedback, pending_rules tables in shopq.db
        - Commits deletions immediately via db_transaction
    """
    if not is_test_mode_enabled():
        raise HTTPException(
            status_code=403,
            detail="Test mode not enabled. Set TEST_MODE=true to use this endpoint.",
        )

    try:
        with db_transaction() as conn:
            cursor = conn.cursor()

            # Clear corrections
            cursor.execute("DELETE FROM corrections")
            corrections_deleted = cursor.rowcount

            # Clear learned patterns
            cursor.execute("DELETE FROM learned_patterns")
            patterns_deleted = cursor.rowcount

            # Clear feedback
            cursor.execute("DELETE FROM feedback")
            feedback_deleted = cursor.rowcount

            # Clear pending rules
            cursor.execute("DELETE FROM pending_rules")
            pending_deleted = cursor.rowcount

        return {
            "success": True,
            "message": "Learning system reset successfully",
            "deleted": {
                "corrections": corrections_deleted,
                "learned_patterns": patterns_deleted,
                "feedback": feedback_deleted,
                "pending_rules": pending_deleted,
            },
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reset learning: {e!s}") from e


@router.get("/stats")
async def get_test_stats() -> dict[str, Any]:
    """
    Get statistics about the current state of the learning system.
    Useful for verifying reset worked.
    """
    try:
        with db_transaction() as conn:
            cursor = conn.cursor()

            # Count corrections
            cursor.execute("SELECT COUNT(*) FROM corrections")
            corrections_count = cursor.fetchone()[0]

            # Count learned patterns
            cursor.execute("SELECT COUNT(*) FROM learned_patterns")
            patterns_count = cursor.fetchone()[0]

            # Count feedback
            cursor.execute("SELECT COUNT(*) FROM feedback")
            feedback_count = cursor.fetchone()[0]

            # Count pending rules
            cursor.execute("SELECT COUNT(*) FROM pending_rules")
            pending_count = cursor.fetchone()[0]

            # Count rules
            cursor.execute("SELECT COUNT(*) FROM rules")
            rules_count = cursor.fetchone()[0]

        return {
            "test_mode_enabled": is_test_mode_enabled(),
            "database_stats": {
                "corrections": corrections_count,
                "learned_patterns": patterns_count,
                "feedback": feedback_count,
                "pending_rules": pending_count,
                "rules": rules_count,
            },
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {e!s}") from e


@router.post("/disable-feedback")
async def disable_feedback() -> dict[str, Any]:
    """
    Temporarily disable feedback collection.
    Sets an in-memory flag that prevents the extension from recording corrections.
    """
    if not is_test_mode_enabled():
        raise HTTPException(
            status_code=403,
            detail="Test mode not enabled. Set TEST_MODE=true to use this endpoint.",
        )

    # Store in environment for this session
    os.environ["FEEDBACK_DISABLED"] = "true"

    return {"success": True, "message": "Feedback collection disabled for this session"}


@router.post("/enable-feedback")
async def enable_feedback() -> dict[str, Any]:
    """Re-enable feedback collection"""
    os.environ["FEEDBACK_DISABLED"] = "false"

    return {"success": True, "message": "Feedback collection re-enabled"}


@router.get("/feedback-status")
async def get_feedback_status() -> dict[str, Any]:
    """Check if feedback collection is enabled"""
    disabled = os.getenv("FEEDBACK_DISABLED", "false").lower() == "true"

    return {
        "feedback_enabled": not disabled,
        "test_mode_enabled": is_test_mode_enabled(),
    }
