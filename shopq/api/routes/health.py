"""Health check and debug endpoints for Reclaim API.

Provides health status endpoints for monitoring and observability:
- /health - Service health including LLM credential presence
- /health/db - Database connection pool health
- /debug/stats - Aggregate system statistics (no PII)
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter

from shopq.config import APP_VERSION

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> dict[str, Any]:
    """Health check endpoint.

    Returns service status, version, and credential readiness for
    Vertex AI / Gemini (does not make an API call, only checks presence).
    """
    has_api_key = bool(os.getenv("GOOGLE_API_KEY"))
    has_project = bool(os.getenv("GOOGLE_CLOUD_PROJECT"))
    llm_ready = has_api_key or has_project

    return {
        "status": "healthy",
        "service": "Reclaim API",
        "version": APP_VERSION,
        "timestamp": datetime.now(UTC).isoformat(),
        "llm": {
            "ready": llm_ready,
            "google_api_key": has_api_key,
            "google_cloud_project": has_project,
        },
    }


@router.get("/health/db")
async def database_health() -> dict[str, Any]:
    """
    Database health check endpoint.

    Returns connection pool health metrics for monitoring.
    Alerts if pool usage exceeds 80%.
    """
    from shopq.infrastructure.database import get_pool_stats

    stats = get_pool_stats()
    usage_percent = stats["usage_percent"]

    return {
        "status": "degraded" if usage_percent > 80 else "healthy",
        "pool": stats,
        "warning": "Pool usage high" if usage_percent > 80 else None,
    }


@router.get("/debug/stats")
async def debug_stats() -> dict[str, Any]:
    """Aggregate system statistics for debugging. Contains no PII."""
    from shopq.infrastructure.database import get_db_connection, get_pool_stats
    from shopq.infrastructure.llm_budget import get_daily_usage_report

    # Global return card counts by status
    with get_db_connection() as conn:
        cursor = conn.execute(
            "SELECT status, COUNT(*) as count FROM return_cards GROUP BY status"
        )
        returns_by_status = {row["status"]: row["count"] for row in cursor.fetchall()}

        cursor = conn.execute("SELECT COUNT(*) FROM return_cards")
        total_returns = cursor.fetchone()[0]

    return {
        "returns": {
            "total": total_returns,
            "by_status": returns_by_status,
        },
        "llm": get_daily_usage_report(),
        "database": get_pool_stats(),
        "timestamp": datetime.now(UTC).isoformat(),
    }
