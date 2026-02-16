"""Health check endpoint for Reclaim API.

Provides a liveness probe for Cloud Run monitoring.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> dict[str, Any]:
    """Health check endpoint for Cloud Run liveness probes."""
    return {"status": "healthy"}
