"""Security headers middleware for Reclaim API

Adds security headers to all responses to protect against common web attacks:
- Content-Security-Policy (XSS protection)
- X-Frame-Options (clickjacking protection)
- X-Content-Type-Options (MIME sniffing protection)
- Strict-Transport-Security (HTTPS enforcement)
- Referrer-Policy (referrer control)
"""

from __future__ import annotations

import os
from collections.abc import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses

    This middleware implements defense-in-depth by adding multiple layers
    of security headers that browsers use to protect against common attacks.
    """

    def __init__(self, app):
        super().__init__(app)
        self.is_production = os.getenv("RECLAIM_ENV", os.getenv("SHOPQ_ENV")) == "production"

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Add security headers to response"""
        response = await call_next(request)

        # Content Security Policy - Prevents XSS attacks
        # Restrict what resources can be loaded and from where
        # Note: 'unsafe-inline' for styles is kept because dashboard uses inline CSS.
        # Scripts do NOT use unsafe-inline - no inline JS is used.
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self' data:; "
            "connect-src 'self';"
        )

        # X-Frame-Options - Prevents clickjacking attacks
        # Don't allow this site to be embedded in iframes
        response.headers["X-Frame-Options"] = "DENY"

        # X-Content-Type-Options - Prevents MIME sniffing
        # Browsers should not try to detect content type, use declared type
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Referrer-Policy - Control what referrer information is sent
        # Only send origin (not full URL) when navigating cross-origin
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Strict-Transport-Security - Enforce HTTPS (production only)
        # Tell browsers to always use HTTPS for this site
        if self.is_production:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        # Permissions-Policy - Control browser features
        # Disable features we don't need to reduce attack surface
        response.headers["Permissions-Policy"] = (
            "geolocation=(), microphone=(), camera=(), "
            "payment=(), usb=(), magnetometer=(), gyroscope=()"
        )

        return response
