"""
User authentication middleware for ShopQ API.

Verifies Google OAuth tokens from the Chrome extension and extracts user identity.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import httpx
from cachetools import TTLCache
from fastapi import HTTPException, Request, status

from shopq.observability.logging import get_logger

logger = get_logger(__name__)

# Google's token info endpoint
GOOGLE_TOKEN_INFO_URL = "https://oauth2.googleapis.com/tokeninfo"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

# Cache configuration (SEC-004: Add TTL to prevent stale/revoked tokens)
_CACHE_MAX_SIZE = 1000
_CACHE_TTL_SECONDS = 600  # 10 minutes - shorter than Google's 1 hour token expiry


@dataclass
class AuthenticatedUser:
    """Represents an authenticated user from Google OAuth."""

    id: str  # Google's unique user ID
    email: str
    name: str | None = None
    picture: str | None = None

    def __str__(self) -> str:
        return f"User({self.id}, {self.email})"


# Cache for validated tokens with TTL (SEC-004)
# Tokens auto-expire after 10 minutes to handle revoked tokens
# In production, consider Redis for multi-instance deployments
_token_cache: TTLCache[str, AuthenticatedUser] = TTLCache(
    maxsize=_CACHE_MAX_SIZE, ttl=_CACHE_TTL_SECONDS
)


async def verify_google_token(token: str) -> AuthenticatedUser:
    """
    Verify a Google OAuth token and return user info.

    Args:
        token: The OAuth access token from Chrome identity API

    Returns:
        AuthenticatedUser with user's Google ID and email

    Raises:
        HTTPException: If token is invalid or expired
    """
    # Check cache first
    if token in _token_cache:
        return _token_cache[token]

    async with httpx.AsyncClient() as client:
        # First, validate the token
        try:
            token_response = await client.get(
                GOOGLE_TOKEN_INFO_URL,
                params={"access_token": token},
                timeout=10.0,
            )
        except httpx.TimeoutException:
            logger.warning("Token validation timed out")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication service unavailable",
            ) from None
        except httpx.RequestError as e:
            logger.error("Token validation request failed: %s", e)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication service unavailable",
            ) from e

        if token_response.status_code != 200:
            logger.warning("Invalid token: %s", token_response.text)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        token_info = token_response.json()

        # SEC-005: Verify the token was issued for our app (MANDATORY in production)
        expected_client_id = os.getenv("GOOGLE_OAUTH_CLIENT_ID")
        is_production = os.getenv("SHOPQ_ENV", "development") == "production"

        if not expected_client_id and is_production:
            logger.error("GOOGLE_OAUTH_CLIENT_ID not configured in production!")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Server misconfiguration: OAuth client ID not set",
            )

        if expected_client_id:
            # The audience must match exactly - substring match is insecure (SEC-005)
            aud = token_info.get("aud", "")
            if aud != expected_client_id:
                logger.warning("Token audience mismatch: expected=%s, got=%s", expected_client_id, aud)
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token not issued for this application",
                    headers={"WWW-Authenticate": "Bearer"},
                )
        else:
            # Development mode without client ID configured - log warning
            logger.warning("GOOGLE_OAUTH_CLIENT_ID not set - skipping audience validation (dev mode only)")

        # Get user info
        try:
            userinfo_response = await client.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {token}"},
                timeout=10.0,
            )
        except (httpx.TimeoutException, httpx.RequestError) as e:
            logger.error("Failed to get user info: %s", e)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Failed to retrieve user information",
            ) from e

        if userinfo_response.status_code != 200:
            logger.warning("Failed to get user info: %s", userinfo_response.text)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Failed to retrieve user information",
                headers={"WWW-Authenticate": "Bearer"},
            )

        userinfo = userinfo_response.json()

        user = AuthenticatedUser(
            id=userinfo["id"],
            email=userinfo.get("email", ""),
            name=userinfo.get("name"),
            picture=userinfo.get("picture"),
        )

        # Cache the result (TTLCache handles size limit and expiry automatically)
        _token_cache[token] = user

        logger.info("Authenticated user: %s (cache size: %d)", user, len(_token_cache))
        return user


def _extract_bearer_token(authorization: str | None) -> str:
    """Extract token from Authorization header."""
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format. Expected: Bearer <token>",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return parts[1]


async def get_current_user(request: Request) -> AuthenticatedUser:
    """
    FastAPI dependency to get the current authenticated user.

    Usage:
        @router.get("/endpoint")
        async def endpoint(user: AuthenticatedUser = Depends(get_current_user)):
            # user.id contains the Google user ID
            # user.email contains the user's email
            ...
    """
    authorization = request.headers.get("Authorization")
    token = _extract_bearer_token(authorization)
    return await verify_google_token(token)


async def get_optional_user(request: Request) -> AuthenticatedUser | None:
    """
    FastAPI dependency for optional authentication.

    Returns None if no auth header provided, otherwise validates and returns user.
    Useful for endpoints that work with or without authentication.
    """
    authorization = request.headers.get("Authorization")
    if not authorization:
        return None

    try:
        token = _extract_bearer_token(authorization)
        return await verify_google_token(token)
    except HTTPException:
        return None


def clear_token_cache() -> None:
    """Clear the token cache. Useful for testing."""
    _token_cache.clear()
