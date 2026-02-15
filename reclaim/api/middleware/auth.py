"""Authentication middleware for Reclaim API"""

from __future__ import annotations

import os
import secrets

from fastapi import Header, HTTPException, status


class APIKeyAuth:
    """
    Simple API key authentication for admin endpoints.

    API key should be set in RECLAIM_ADMIN_API_KEY environment variable.
    For production, use more robust auth (OAuth, JWT, etc.).
    """

    def __init__(self):
        self.api_key = os.getenv("RECLAIM_ADMIN_API_KEY", os.getenv("SHOPQ_ADMIN_API_KEY"))
        if not self.api_key:
            # Generate a warning but don't fail - auth is optional for development
            import logging

            logging.warning("RECLAIM_ADMIN_API_KEY not set - admin endpoints are unprotected!")

    def verify_api_key(self, authorization: str | None = Header(None)) -> bool:
        """
        Verify API key from Authorization header.

        Expected format: "Bearer {api_key}"
        """
        # If no API key is configured, allow access (development mode)
        if not self.api_key:
            return True

        # Check if authorization header is present
        if not authorization:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing authorization header",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Parse Bearer token
        try:
            scheme, token = authorization.split()
            if scheme.lower() != "bearer":
                raise ValueError("Invalid authentication scheme")
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authorization header format. Expected: Bearer {api_key}",
                headers={"WWW-Authenticate": "Bearer"},
            ) from e

        # Verify token matches configured API key (timing-safe comparison)
        # Using secrets.compare_digest() prevents timing attacks where an attacker
        # could extract the key character-by-character by measuring response times
        if not secrets.compare_digest(token, self.api_key):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid API key",
            )

        return True


# Global auth instance
auth = APIKeyAuth()


def require_admin_auth(authorization: str | None = Header(None)) -> bool:
    """
    Dependency for endpoints that require admin authentication.

    Usage:
        @app.post("/api/admin/endpoint")
        async def admin_endpoint(authenticated: bool = Depends(require_admin_auth)):
            ...
    """
    return auth.verify_api_key(authorization)
