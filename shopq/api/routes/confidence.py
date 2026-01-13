"""Confidence monitoring endpoints for ShopQ API.

Provides endpoints for monitoring classification confidence:
- /api/config/confidence - Get confidence thresholds
- /api/confidence/stats - Get confidence statistics
- /api/confidence/low - Get low-confidence classifications
- /api/confidence/trend - Get confidence trends over time
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from shopq.runtime.thresholds import ConfidenceLogger

router = APIRouter(prefix="/api", tags=["confidence"])


@router.get("/config/confidence")
async def get_confidence_thresholds() -> dict[str, Any]:
    """
    Get centralized confidence thresholds for frontend use.

    Returns all confidence-related thresholds from shopq/config/confidence.py
    so frontend can use consistent values instead of hard-coding them.

    Side Effects:
        None (pure function - reads config constants only)
    """
    from shopq.observability.confidence import get_all_thresholds

    return {"version": "1.0.0", "thresholds": get_all_thresholds()}


@router.get("/confidence/stats")
async def get_confidence_stats(days: int = 7) -> dict[str, Any]:
    """
    Get confidence statistics for monitoring.

    Query params:
        days: Number of days to analyze (default 7)

    Returns:
        Aggregated confidence statistics including:
        - Average confidence by decider
        - Low confidence rate
        - Filtered labels count

    Side Effects:
        - Reads from confidence_logs table in shopq.db
    """
    logger = ConfidenceLogger()
    return logger.get_confidence_stats(days=days)


@router.get("/confidence/low")
async def get_low_confidence_classifications(limit: int = 100) -> list[dict[str, Any]]:
    """
    Get recent low-confidence classifications for review.

    Query params:
        limit: Max number of results (default 100)

    Returns:
        List of recent low-confidence classifications

    Side Effects:
        - Reads from confidence_logs table in shopq.db
    """
    logger = ConfidenceLogger()
    return logger.get_low_confidence_classifications(limit=limit)


@router.get("/confidence/trend")
async def get_confidence_trend(days: int = 30) -> list[dict[str, Any]]:
    """
    Get confidence trend over time for monitoring.

    Query params:
        days: Number of days to analyze (default 30)

    Returns:
        Time-series data of confidence scores

    Side Effects:
        - Reads from confidence_logs table in shopq.db
    """
    logger = ConfidenceLogger()
    return logger.get_confidence_trend(days=days)
