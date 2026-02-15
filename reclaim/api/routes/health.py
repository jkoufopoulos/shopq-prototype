"""Health check endpoint for Reclaim API.

Provides a liveness probe for Cloud Run monitoring.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter

from reclaim.config import APP_VERSION

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
