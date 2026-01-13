"""Shared API utilities.

This module contains common utilities used across multiple API routes.
Centralizing these prevents code duplication and ensures consistent behavior.
"""

from __future__ import annotations

from fastapi import Request


def get_client_ip(request: Request) -> str:
    """Extract client IP for audit logging.

    Checks headers set by proxies (X-Forwarded-For, X-Real-IP)
    before falling back to direct connection IP.

    Args:
        request: FastAPI request object

    Returns:
        Client IP address as string

    Side Effects:
        None (pure function - only reads request headers)
    """
    # Check X-Forwarded-For (behind proxy/load balancer)
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()

    # Check X-Real-IP
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip

    # Fall back to direct connection IP
    return request.client.host if request.client else "unknown"
