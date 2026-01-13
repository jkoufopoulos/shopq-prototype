"""

from __future__ import annotations

Location Service - Get user's location from IP address

Uses ipapi.co free tier for IP geolocation.
Free tier: 1,000 requests/day, no API key required.

This is used to add local weather greeting to daily digest.
"""

from datetime import datetime, timedelta
from typing import Any

import requests

from mailq.observability.logging import get_logger

# Simple time-based cache (don't cache failures)
_location_cache: dict[str, Any] | None = None
_cache_time: datetime | None = None
_CACHE_DURATION = timedelta(hours=1)
logger = get_logger(__name__)


def get_user_location() -> dict[str, Any] | None:
    """
    Get user's location from IP address.

    Returns:
        {'city': 'Brooklyn', 'region': 'New York', 'country': 'US'}
        or None if API fails

    Side Effects:
        - Makes HTTP request to ipapi.co API for geolocation
        - Modifies global _location_cache and _cache_time on success
        - Logs warnings on API failures
    """
    global _location_cache, _cache_time

    # Check cache (only cache successes, not failures)
    if _location_cache and _cache_time and datetime.now() - _cache_time < _CACHE_DURATION:
        return _location_cache

    try:
        response = requests.get(
            "https://ipapi.co/json/",
            timeout=3,  # 3s timeout
        )
        response.raise_for_status()
        data = response.json()

        location = {
            "city": data.get("city"),
            "region": data.get("region"),
            "country": data.get("country_name"),
        }

        # Cache successful response
        _location_cache = location
        _cache_time = datetime.now()

        return location
    except Exception as e:
        logger.warning("IP geolocation failed: %s", e)

        # If we hit rate limits or any error, use fallback location
        # This prevents weather from completely failing
        if not _location_cache:
            logger.warning("Using fallback location (New York) due to geolocation failure")
            fallback = {
                "city": "New York",
                "region": "New York",
                "country": "United States",
            }
            # Cache fallback briefly (5 minutes) to avoid repeated failed API calls
            _location_cache = fallback
            _cache_time = datetime.now()
            return fallback

        # If we have a previous cache, return it even if old
        logger.warning("Returning stale cached location (geolocation API unavailable)")
        return _location_cache


def get_user_city() -> str | None:
    """
    Get user's city name from IP address.

    Returns:
        City name (e.g., "Brooklyn") or None
    """
    location = get_user_location()
    return location["city"] if location else None
