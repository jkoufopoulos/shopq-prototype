"""
Authentication utilities for FastAPI.

For MVP: Returns 'default' user_id (single-user mode)
For production: Validates OAuth tokens and extracts user email
"""

from __future__ import annotations

import os
from functools import lru_cache

import requests
from fastapi import Header, HTTPException

from shopq.observability.logging import get_logger

logger = get_logger(__name__)


def get_current_user_id(authorization: str | None = Header(None)) -> str:
    """
    Extract user_id from Authorization header.

    For MVP (AUTH_REQUIRED=false): Returns 'default' if no auth header
    For production (AUTH_REQUIRED=true): Validates OAuth token and extracts user_id

    Args:
        authorization: Authorization header value (format: "Bearer <token>")

    Returns:
        user_id (email address for authenticated users, 'default' for MVP)

    Raises:
        HTTPException: 401 if AUTH_REQUIRED=true and token is missing/invalid

    Example:
        @app.post("/api/classify")
        async def classify(user_id: str = Depends(get_current_user_id)):
            # user_id is extracted from token or 'default' in MVP mode
            ...
    """
    # MVP mode: No auth required (backward compatible)
    if os.getenv("AUTH_REQUIRED", "false").lower() != "true":
        return "default"

    # Production mode: Validate token
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Authorization header required. Use: Authorization: Bearer <token>",
        )

    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401, detail="Invalid authorization format. Expected: Bearer <token>"
        )

    token = authorization.replace("Bearer ", "")

    # Validate OAuth token with Google
    user_id = validate_google_oauth_token(token)

    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return user_id


@lru_cache(maxsize=1000)
def validate_google_oauth_token(token: str) -> str | None:
    """
    Validate Google OAuth token and extract user email.

    Uses Google's tokeninfo endpoint to verify:
    1. Token is valid
    2. Token has required Gmail scopes
    3. Token is not expired

    Args:
        token: OAuth access token from chrome.identity.getAuthToken()

    Returns:
        User email if valid, None if invalid

    Cache:
        Results cached with LRU (1000 tokens max)
        Cache cleared on function reload
        TODO: Add TTL-based cache invalidation

    Reference:
        https://developers.google.com/identity/protocols/oauth2/web-server#tokeninfo
        Side Effects:
            Makes API calls
    """
    try:
        response = requests.get(
            "https://www.googleapis.com/oauth2/v3/tokeninfo",
            params={"access_token": token},
            timeout=5,
        )

        if response.status_code != 200:
            return None

        token_info = response.json()

        # Verify token has required Gmail scope
        required_scope = "https://www.googleapis.com/auth/gmail.readonly"
        scopes = token_info.get("scope", "")

        if required_scope not in scopes:
            logger.warning("Token missing required scope: %s", required_scope)
            return None

        email = token_info.get("email")
        if not email:
            logger.warning("Token has no email claim")
            return None

        logger.info("Token validated for user: %s", email)
        return email

    except requests.exceptions.Timeout:
        logger.warning("Token validation timeout (Google tokeninfo API)")
        return None
    except requests.exceptions.RequestException as e:
        logger.error("Token validation error: %s", e)
        return None


def clear_token_cache() -> None:
    """
    Clear the token validation cache.

    Use this when:
    - Suspecting stale cached tokens
    - After security incident
    - During testing

    Example:
        from shopq.infrastructure.auth import clear_token_cache
        clear_token_cache()
        Side Effects:
            None (pure function)
    """
    validate_google_oauth_token.cache_clear()
    logger.info("Token cache cleared")


# For testing: Mock authentication
def _mock_get_current_user_id(user_id: str = "test_user@example.com"):
    """
    Mock authentication for testing.

    DO NOT use in production!

    Example:
        # In test setup
        import shopq.api as api_module
        api_module.get_current_user_id = lambda: "test_user@example.com"
    """
    return lambda _authorization=None: user_id  # noqa: ARG005
