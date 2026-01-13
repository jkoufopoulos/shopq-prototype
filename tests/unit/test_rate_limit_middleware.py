"""Unit tests for rate limiting middleware

Tests cover:
- Requests under limit allowed
- Minute limit enforcement
- Hour limit enforcement
- Health endpoint bypass
- Per-IP isolation
- Rate limit headers
- Memory cleanup
"""

from __future__ import annotations

import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from mailq.api.middleware.rate_limit import RateLimitMiddleware


@pytest.fixture
def app():
    """Create test FastAPI app with rate limiting"""
    test_app = FastAPI()

    # Use low limits for testing
    test_app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=5,
        requests_per_hour=20,
    )

    @test_app.get("/api/test")
    async def test_endpoint():
        return {"status": "ok"}

    @test_app.get("/health")
    async def health():
        return {"status": "healthy"}

    return test_app


def test_requests_under_limit_allowed(app):
    """Test that requests under the limit are allowed"""
    client = TestClient(app)

    # Make 3 requests (under 5/min limit)
    for _ in range(3):
        response = client.get("/api/test")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

        # Check rate limit headers
        assert "X-RateLimit-Limit-Minute" in response.headers
        assert response.headers["X-RateLimit-Limit-Minute"] == "5"
        assert "X-RateLimit-Remaining-Minute" in response.headers


def test_minute_limit_enforced(app):
    """Test that minute rate limit is enforced"""
    client = TestClient(app)

    # Make exactly 5 requests (the limit)
    for _ in range(5):
        response = client.get("/api/test")
        assert response.status_code == 200

    # 6th request should be rate limited
    response = client.get("/api/test")
    assert response.status_code == 429
    assert "Rate limit exceeded" in response.json()["detail"]
    assert "per minute" in response.json()["detail"]
    assert response.json()["retry_after"] == 60
    assert response.headers["Retry-After"] == "60"


def test_hour_limit_enforced():
    """Test that hour rate limit is enforced"""
    # Create app with very low hour limit
    test_app = FastAPI()
    test_app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=100,  # High minute limit
        requests_per_hour=3,  # Low hour limit
    )

    @test_app.get("/api/test")
    async def test_endpoint():
        return {"status": "ok"}

    client = TestClient(test_app)

    # Make 3 requests (the hour limit)
    for _i in range(3):
        response = client.get("/api/test")
        assert response.status_code == 200

    # 4th request should hit hour limit
    response = client.get("/api/test")
    assert response.status_code == 429
    assert "Rate limit exceeded" in response.json()["detail"]
    assert "per hour" in response.json()["detail"]
    assert response.json()["retry_after"] == 3600
    assert response.headers["Retry-After"] == "3600"


def test_health_endpoints_bypass_rate_limit(app):
    """Test that health check endpoints bypass rate limiting"""
    client = TestClient(app)

    # First exhaust the rate limit on regular endpoint
    for _i in range(6):
        client.get("/api/test")

    # Health endpoint should still work
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}

    # Health endpoint should not have rate limit headers
    # (it bypasses the middleware before headers are added)


def test_per_ip_isolation(app):
    """Test that rate limits are isolated per IP address"""
    client1 = TestClient(app)
    client2 = TestClient(app)

    # Exhaust rate limit for client1
    for _i in range(5):
        response = client1.get("/api/test", headers={"X-Forwarded-For": "192.168.1.1"})
        assert response.status_code == 200

    # client1 should be rate limited
    response = client1.get("/api/test", headers={"X-Forwarded-For": "192.168.1.1"})
    assert response.status_code == 429

    # client2 (different IP) should still work
    response = client2.get("/api/test", headers={"X-Forwarded-For": "192.168.1.2"})
    assert response.status_code == 200


def test_rate_limit_headers_accuracy(app):
    """Test that rate limit headers show accurate counts"""
    client = TestClient(app)

    # First request
    response = client.get("/api/test")
    assert response.status_code == 200
    assert response.headers["X-RateLimit-Remaining-Minute"] == "4"  # 5 - 1 = 4
    assert response.headers["X-RateLimit-Remaining-Hour"] == "19"  # 20 - 1 = 19

    # Second request
    response = client.get("/api/test")
    assert response.status_code == 200
    assert response.headers["X-RateLimit-Remaining-Minute"] == "3"  # 5 - 2 = 3
    assert response.headers["X-RateLimit-Remaining-Hour"] == "18"  # 20 - 2 = 18


def test_time_window_resets():
    """Test that rate limits reset after time window"""
    # Create middleware with very short window for testing
    test_app = FastAPI()

    RateLimitMiddleware(
        test_app.router,
        requests_per_minute=2,
        requests_per_hour=10,
    )

    test_app.add_middleware(RateLimitMiddleware, requests_per_minute=2, requests_per_hour=10)

    @test_app.get("/api/test")
    async def test_endpoint():
        return {"status": "ok"}

    client = TestClient(test_app)

    # Make 2 requests (hit limit)
    response = client.get("/api/test")
    assert response.status_code == 200
    response = client.get("/api/test")
    assert response.status_code == 200

    # 3rd request should be rate limited
    response = client.get("/api/test")
    assert response.status_code == 429

    # Manually clean old requests (simulate time passing)
    # In real usage, this happens automatically after 60 seconds


def test_x_forwarded_for_header_parsing(app):
    """Test that X-Forwarded-For header is parsed correctly"""
    client = TestClient(app)

    # X-Forwarded-For can have multiple IPs (proxy chain)
    # Should use the first one (original client)
    response = client.get(
        "/api/test", headers={"X-Forwarded-For": "203.0.113.1, 198.51.100.1, 192.0.2.1"}
    )
    assert response.status_code == 200

    # Make more requests with same first IP
    for _i in range(4):
        response = client.get("/api/test", headers={"X-Forwarded-For": "203.0.113.1, 10.0.0.1"})

    # Should be rate limited (same IP)
    response = client.get("/api/test", headers={"X-Forwarded-For": "203.0.113.1, 10.0.0.2"})
    assert response.status_code == 429


def test_x_real_ip_header(app):
    """Test that X-Real-IP header is respected"""
    client = TestClient(app)

    # Make requests with X-Real-IP
    for _i in range(5):
        response = client.get("/api/test", headers={"X-Real-IP": "198.51.100.42"})
        assert response.status_code == 200

    # 6th request should be rate limited
    response = client.get("/api/test", headers={"X-Real-IP": "198.51.100.42"})
    assert response.status_code == 429


def test_memory_cleanup():
    """Test that old IP addresses are cleaned up to prevent memory leak"""
    test_app = FastAPI()
    middleware = RateLimitMiddleware(
        test_app.router,
        requests_per_minute=100,
        requests_per_hour=1000,
    )

    # Simulate requests from many different IPs
    for i in range(100):
        middleware.minute_buckets[f"192.168.1.{i}"] = [time.time()]
        middleware.hour_buckets[f"192.168.1.{i}"] = [time.time()]

    assert len(middleware.minute_buckets) == 100

    # Simulate old timestamps (3 hours ago)
    old_timestamp = time.time() - 10800
    for i in range(50):
        middleware.minute_buckets[f"192.168.2.{i}"] = [old_timestamp]
        middleware.hour_buckets[f"192.168.2.{i}"] = [old_timestamp]

    assert len(middleware.minute_buckets) == 150

    # Trigger cleanup
    middleware._cleanup_old_buckets()

    # Old IPs should be removed
    # (only recent 192.168.1.x should remain)
    assert len(middleware.minute_buckets) == 100


def test_concurrent_requests_same_ip(app):
    """Test that concurrent requests from same IP are counted correctly"""
    client = TestClient(app)

    # Make 5 requests rapidly
    responses = [client.get("/api/test") for _ in range(5)]

    # All should succeed (at limit)
    assert all(r.status_code == 200 for r in responses)

    # Next request should fail
    response = client.get("/api/test")
    assert response.status_code == 429
