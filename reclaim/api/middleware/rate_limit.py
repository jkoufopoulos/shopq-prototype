"""Rate limiting middleware for Reclaim API

Provides request-based rate limiting to prevent abuse.

Security features:
- IP spoofing protection (only trusts X-Forwarded-For from Cloud Run)
- Memory leak prevention via periodic bucket cleanup
"""

from __future__ import annotations

import ipaddress
import os
import secrets
import time
from collections.abc import Callable
from typing import Any

from cachetools import TTLCache
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from reclaim.config import (
    CHROME_EXTENSION_ORIGIN,
    RATE_LIMIT_MAX_IPS,
    RATE_LIMIT_RPH,
    RATE_LIMIT_RPM,
)
from reclaim.observability.telemetry import log_event


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limiting middleware.

    Limits requests per IP address to prevent:
    - Request flooding (60 req/min, 1000 req/hour)

    For production, consider using Redis-backed rate limiting for multi-instance deployments.
    """

    def __init__(
        self,
        app: Any,
        requests_per_minute: int = RATE_LIMIT_RPM,
        requests_per_hour: int = RATE_LIMIT_RPH,
    ) -> None:
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.requests_per_hour = requests_per_hour

        # EXT-002: Use TTLCache to prevent unbounded memory growth
        _max_ips = RATE_LIMIT_MAX_IPS

        # Request tracking: {ip: [timestamp, ...]}
        # TTLCache auto-evicts entries after ttl seconds
        self.minute_buckets: TTLCache[str, list[float]] = TTLCache(maxsize=_max_ips, ttl=120)
        self.hour_buckets: TTLCache[str, list[float]] = TTLCache(maxsize=_max_ips, ttl=7200)

        # Cloud Run sets this header - only trust X-Forwarded-For when present
        self._trusted_proxy_header = "X-Cloud-Trace-Context"

    def _is_valid_ip(self, ip_str: str) -> bool:
        """Validate that a string is a valid IPv4 or IPv6 address.

        SEC-010: Prevents rate limit bypass via malformed X-Forwarded-For headers.
        """
        try:
            ipaddress.ip_address(ip_str)
            return True
        except ValueError:
            return False

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP with spoofing protection.

        Security: Only trusts X-Forwarded-For when request comes from Cloud Run
        (indicated by X-Cloud-Trace-Context header). Direct connections use
        the socket IP to prevent IP spoofing attacks.

        SEC-010: Validates IP format to prevent bypass via malformed headers.
        """
        # In production (Cloud Run), trust X-Forwarded-For only if Cloud Trace header present
        is_from_trusted_proxy = self._trusted_proxy_header in request.headers

        if is_from_trusted_proxy:
            # Cloud Run adds the real client IP as first entry in X-Forwarded-For
            forwarded = request.headers.get("X-Forwarded-For")
            if forwarded:
                ip = forwarded.split(",")[0].strip()
                # SEC-010: Validate IP format before trusting
                if self._is_valid_ip(ip):
                    return ip
                # Fall through to socket IP if invalid

        # Development mode: allow X-Forwarded-For for testing behind local proxies
        if os.getenv("RECLAIM_ENV", os.getenv("SHOPQ_ENV", "development")) == "development":
            forwarded = request.headers.get("X-Forwarded-For")
            if forwarded:
                ip = forwarded.split(",")[0].strip()
                if self._is_valid_ip(ip):
                    return ip

            real_ip = request.headers.get("X-Real-IP")
            if real_ip and self._is_valid_ip(real_ip):
                return real_ip

        # Default: use direct connection IP (cannot be spoofed)
        return request.client.host if request.client else "unknown"

    def _clean_old_requests(self, bucket: list[float], max_age_seconds: int) -> list[float]:
        """Remove requests older than max_age_seconds"""
        now = time.time()
        return [ts for ts in bucket if now - ts < max_age_seconds]

    def _cleanup_old_buckets(self) -> None:
        """Periodically remove old IPs to prevent memory leak

        Removes IP addresses that haven't made requests in the last 2 hours.
        This prevents unbounded memory growth as new IPs are seen.
        """
        now = time.time()
        max_idle_time = 7200  # 2 hours

        # EXT-002: With TTLCache, entries auto-expire, but we still do manual cleanup
        # for entries that haven't been accessed recently
        ips_to_remove = []
        for ip in list(self.minute_buckets.keys()):
            bucket = self.minute_buckets.get(ip, [])
            if not bucket or now - max(bucket) > max_idle_time:
                ips_to_remove.append(ip)

        # Remove idle IPs
        for ip in ips_to_remove:
            self.minute_buckets.pop(ip, None)
            self.hour_buckets.pop(ip, None)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Check rate limits before processing request."""

        # Skip rate limiting for health checks
        if request.url.path in ["/health", "/health/db", "/"]:
            return await call_next(request)

        # Periodically cleanup old IPs (1% chance per request to avoid overhead)
        # This prevents memory leak as new IPs are seen over time
        # SEC-018: Use cryptographically secure random to prevent predictable cleanup timing
        if secrets.randbelow(100) == 0:
            self._cleanup_old_buckets()

        client_ip = self._get_client_ip(request)
        now = time.time()

        # Clean old requests (TTLCache handles expiry, but we still clean within-window old entries)
        self.minute_buckets[client_ip] = self._clean_old_requests(
            self.minute_buckets.get(client_ip, []), 60
        )
        self.hour_buckets[client_ip] = self._clean_old_requests(
            self.hour_buckets.get(client_ip, []), 3600
        )

        # CORS headers for rate limit responses (bypass CORS middleware)
        origin = request.headers.get("origin", "")
        cors_headers = {}
        if origin in [
            "https://mail.google.com",
            CHROME_EXTENSION_ORIGIN,
        ]:
            cors_headers = {
                "Access-Control-Allow-Origin": origin,
                "Access-Control-Allow-Credentials": "true",
            }

        # Check minute limit
        minute_requests = len(self.minute_buckets.get(client_ip, []))
        if minute_requests >= self.requests_per_minute:
            log_event(
                "api.rate_limit.request_exceeded",
                ip=client_ip,
                limit="minute",
                count=minute_requests,
            )
            return JSONResponse(
                status_code=429,
                content={
                    "detail": (
                        f"Rate limit exceeded. Maximum "
                        f"{self.requests_per_minute} requests per minute."
                    ),
                    "retry_after": 60,
                },
                headers={"Retry-After": "60", **cors_headers},
            )

        # Check hour limit
        hour_requests = len(self.hour_buckets.get(client_ip, []))
        if hour_requests >= self.requests_per_hour:
            log_event(
                "api.rate_limit.request_exceeded",
                ip=client_ip,
                limit="hour",
                count=hour_requests,
            )
            return JSONResponse(
                status_code=429,
                content={
                    "detail": (
                        f"Rate limit exceeded. Maximum {self.requests_per_hour} requests per hour."
                    ),
                    "retry_after": 3600,
                },
                headers={"Retry-After": "3600", **cors_headers},
            )

        # Record this request (initialize bucket if needed for TTLCache)
        minute_bucket = self.minute_buckets.get(client_ip, [])
        minute_bucket.append(now)
        self.minute_buckets[client_ip] = minute_bucket

        hour_bucket = self.hour_buckets.get(client_ip, [])
        hour_bucket.append(now)
        self.hour_buckets[client_ip] = hour_bucket

        # Process request
        response = await call_next(request)

        # Add rate limit headers
        response.headers["X-RateLimit-Limit-Minute"] = str(self.requests_per_minute)
        response.headers["X-RateLimit-Remaining-Minute"] = str(
            self.requests_per_minute - minute_requests - 1
        )
        response.headers["X-RateLimit-Limit-Hour"] = str(self.requests_per_hour)
        response.headers["X-RateLimit-Remaining-Hour"] = str(
            self.requests_per_hour - hour_requests - 1
        )

        return response
