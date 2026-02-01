"""Health check endpoints for ShopQ API.

Provides health status endpoints for monitoring and observability:
- /health - Basic service health
- /health/db - Database connection pool health
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> dict[str, Any]:
    """Health check endpoint.

    Side Effects:
        None (pure function - builds local dict only)
    """
    return {
        "status": "healthy",
        "service": "ShopQ API",
        "version": "2.0.0-mvp",
        "timestamp": datetime.now(UTC).isoformat(),
    }


@router.get("/health/db")
async def database_health() -> dict[str, Any]:
    """
    Database health check endpoint.

    Returns connection pool health metrics for monitoring.
    Alerts if pool usage exceeds 80%.

    Side Effects:
        None (reads in-memory pool statistics only)
    """
    from shopq.infrastructure.database import get_pool_stats

    stats = get_pool_stats()
    usage_percent = stats["usage_percent"]

    return {
        "status": "degraded" if usage_percent > 80 else "healthy",
        "pool": stats,
        "warning": "Pool usage high" if usage_percent > 80 else None,
    }
