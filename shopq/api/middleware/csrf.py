"""
CSRF Protection Middleware for ShopQ API.

SEC-006: Validates Origin header on state-changing requests to prevent
cross-site request forgery attacks.

Note: Since the API uses Bearer token authentication (not cookies), traditional
CSRF attacks are less effective. This middleware provides defense-in-depth by
ensuring requests come from expected origins.
"""

from __future__ import annotations

import os
from typing import Callable

from fastapi import HTTPException, Request, Response, status
from starlette.middleware.base import BaseHTTPMiddleware

from shopq.observability.logging import get_logger

logger = get_logger(__name__)

# SEC-007: Whitelist specific extension IDs to prevent malicious extensions
# Set SHOPQ_EXTENSION_IDS as comma-separated list of allowed extension IDs
# In development, unpacked extensions have dynamic IDs, so we allow configuration
ALLOWED_EXTENSION_IDS = set(
    filter(None, os.getenv("SHOPQ_EXTENSION_IDS", "").split(","))
)

# Methods that modify state and require CSRF protection
STATE_CHANGING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# Paths that are exempt from CSRF checks (e.g., webhooks, public endpoints)
CSRF_EXEMPT_PATHS = {
    "/",
    "/api/health",
    "/api/health/live",
    "/api/health/ready",
}


class CSRFMiddleware(BaseHTTPMiddleware):
    """
    Middleware to validate Origin header on state-changing requests.

    This provides defense-in-depth against CSRF attacks even though
    the API uses Bearer token authentication.
    """

    def __init__(self, app, allowed_origins: list[str] | None = None):
        super().__init__(app)
        self.allowed_origins = set(allowed_origins or [])

        # Add default allowed origins
        self.allowed_origins.update([
            "https://mail.google.com",
        ])

        # In development, allow localhost
        if os.getenv("SHOPQ_ENV", "development") == "development":
            self.allowed_origins.update([
                "http://localhost:3000",
                "http://localhost:8000",
                "http://127.0.0.1:3000",
                "http://127.0.0.1:8000",
            ])

        logger.info("CSRF middleware initialized with %d allowed origins", len(self.allowed_origins))

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip CSRF check for safe methods
        if request.method not in STATE_CHANGING_METHODS:
            return await call_next(request)

        # Skip CSRF check for exempt paths
        if request.url.path in CSRF_EXEMPT_PATHS:
            return await call_next(request)

        # Get Origin header
        origin = request.headers.get("origin")
        referer = request.headers.get("referer")

        # Chrome extensions set Origin to chrome-extension://[id]
        # SEC-007: Only accept whitelisted extension IDs (or all in dev mode if none configured)
        if origin and origin.startswith("chrome-extension://"):
            ext_id = origin.replace("chrome-extension://", "").split("/")[0]

            # If no extension IDs configured, allow all in development only
            if not ALLOWED_EXTENSION_IDS:
                if os.getenv("SHOPQ_ENV", "development") == "development":
                    logger.debug("Allowing extension %s (dev mode, no whitelist)", ext_id)
                    return await call_next(request)
                else:
                    logger.warning("Rejected extension %s (no whitelist configured in production)", ext_id)
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Extension not authorized (configure SHOPQ_EXTENSION_IDS)",
                    )

            # Check against whitelist
            if ext_id in ALLOWED_EXTENSION_IDS:
                return await call_next(request)
            else:
                logger.warning("Rejected unknown extension ID: %s", ext_id)
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Extension not authorized",
                )

        # Validate Origin against allowed list
        if origin and origin in self.allowed_origins:
            return await call_next(request)

        # If no Origin, check Referer as fallback (some browsers don't send Origin)
        if not origin and referer:
            # Extract origin from referer
            try:
                from urllib.parse import urlparse
                parsed = urlparse(referer)
                referer_origin = f"{parsed.scheme}://{parsed.netloc}"

                if referer_origin.startswith("chrome-extension://"):
                    # SEC-007: Apply same whitelist check for referer
                    ext_id = referer_origin.replace("chrome-extension://", "").split("/")[0]
                    if not ALLOWED_EXTENSION_IDS and os.getenv("SHOPQ_ENV", "development") == "development":
                        return await call_next(request)
                    if ext_id in ALLOWED_EXTENSION_IDS:
                        return await call_next(request)
                    # Fall through to rejection if not in whitelist

                if referer_origin in self.allowed_origins:
                    return await call_next(request)
            except Exception:
                pass  # If parsing fails, reject the request

        # Log the rejection (but don't leak sensitive info)
        logger.warning(
            "CSRF check failed: method=%s path=%s origin=%s",
            request.method,
            request.url.path,
            origin[:50] if origin else "None",
        )

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Request origin not allowed",
        )
