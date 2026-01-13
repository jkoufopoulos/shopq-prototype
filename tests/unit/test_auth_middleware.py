"""Unit tests for authentication middleware

Tests cover:
- Missing authorization header
- Invalid authorization schemes
- Incorrect API keys
- Correct API key authentication
- Development mode bypass
- Timing attack resistance
"""

from __future__ import annotations

import os

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from shopq.api.middleware.auth import APIKeyAuth


def create_test_app(api_key: str | None = None):
    """Create test FastAPI app with protected endpoint"""
    # Set environment before creating auth instance
    if api_key is not None:
        os.environ["SHOPQ_ADMIN_API_KEY"] = api_key
    elif "SHOPQ_ADMIN_API_KEY" in os.environ:
        del os.environ["SHOPQ_ADMIN_API_KEY"]

    # Create fresh auth instance that reads current environment
    auth_instance = APIKeyAuth()

    test_app = FastAPI()

    @test_app.get("/protected")
    async def protected(_authenticated: bool = Depends(auth_instance.verify_api_key)):
        return {"status": "ok"}

    return test_app


def test_auth_rejects_missing_header():
    """Test that requests without Authorization header are rejected"""
    app = create_test_app("test-key-123")
    client = TestClient(app)
    response = client.get("/protected")

    assert response.status_code == 401
    assert "Missing authorization header" in response.json()["detail"]
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_auth_rejects_invalid_scheme():
    """Test that non-Bearer schemes are rejected"""
    app = create_test_app("test-key-123")
    client = TestClient(app)
    response = client.get("/protected", headers={"Authorization": "Basic abc123"})

    assert response.status_code == 401
    assert "Invalid authorization header format" in response.json()["detail"]


def test_auth_rejects_malformed_header():
    """Test that malformed Authorization headers are rejected"""
    app = create_test_app("test-key-123")
    client = TestClient(app)
    response = client.get("/protected", headers={"Authorization": "InvalidFormat"})

    assert response.status_code == 401
    assert "Invalid authorization header format" in response.json()["detail"]


def test_auth_rejects_wrong_key():
    """Test that incorrect API keys are rejected"""
    app = create_test_app("correct-key")
    client = TestClient(app)
    response = client.get("/protected", headers={"Authorization": "Bearer wrong-key"})

    assert response.status_code == 403
    assert "Invalid API key" in response.json()["detail"]


def test_auth_accepts_correct_key():
    """Test that correct API key grants access"""
    app = create_test_app("correct-key")
    client = TestClient(app)
    response = client.get("/protected", headers={"Authorization": "Bearer correct-key"})

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_auth_bypass_when_no_key_configured():
    """Test that auth is bypassed when SHOPQ_ADMIN_API_KEY is not set"""
    app = create_test_app(None)  # No API key
    client = TestClient(app)

    # Should allow access without auth header (development mode)
    response = client.get("/protected")
    assert response.status_code == 200


def test_auth_case_sensitive_bearer():
    """Test that 'Bearer' scheme is case-insensitive"""
    app = create_test_app("test-key")
    client = TestClient(app)

    # lowercase 'bearer' should work
    response = client.get("/protected", headers={"Authorization": "bearer test-key"})
    assert response.status_code == 200

    # UPPERCASE 'BEARER' should work
    response = client.get("/protected", headers={"Authorization": "BEARER test-key"})
    assert response.status_code == 200


def test_timing_attack_resistance():
    """Test that API key comparison uses secrets.compare_digest

    This test verifies that we're using timing-safe comparison.
    We can't directly test timing, but we can verify the function is imported.
    """
    from shopq.api.middleware import auth

    # Verify secrets module is imported
    assert hasattr(auth, "secrets")

    # Verify compare_digest is used in the verify_api_key method
    import inspect

    source = inspect.getsource(auth.APIKeyAuth.verify_api_key)
    assert "secrets.compare_digest" in source
    assert "token != self.api_key" not in source


def test_auth_with_whitespace_in_key():
    """Test that keys with whitespace are handled correctly"""
    app = create_test_app("key-with-spaces")
    client = TestClient(app)

    # Extra spaces in Authorization header should be normalized by split()
    response = client.get("/protected", headers={"Authorization": "Bearer  key-with-spaces"})
    # split() with no args handles multiple whitespace gracefully
    assert response.status_code == 200


def test_auth_empty_key():
    """Test behavior with empty API key"""
    app = create_test_app("test-key")
    client = TestClient(app)
    response = client.get("/protected", headers={"Authorization": "Bearer "})

    assert response.status_code == 401  # split() will fail with trailing space


def test_multiple_requests_same_key():
    """Test that same key works for multiple requests"""
    app = create_test_app("test-key")
    client = TestClient(app)

    # Make multiple requests with same key
    for _ in range(5):
        response = client.get("/protected", headers={"Authorization": "Bearer test-key"})
        assert response.status_code == 200
