"""
API Integration Tests for MailQ Backend

Run with: uv run pytest tests/test_api_integration.py -v
"""

import os

import pytest
import requests

# Use production URL by default, can override with env var
API_BASE_URL = os.getenv("MAILQ_API_URL", "https://mailq-api-488078904670.us-central1.run.app")


class TestHealthEndpoints:
    """Test basic health and config endpoints."""

    def test_health_endpoint(self):
        """Health endpoint should return 200."""
        response = requests.get(f"{API_BASE_URL}/health", timeout=10)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    def test_config_endpoint(self):
        """Config endpoint should return confidence thresholds."""
        response = requests.get(f"{API_BASE_URL}/api/config/confidence", timeout=10)
        assert response.status_code == 200
        data = response.json()
        assert "thresholds" in data

    def test_test_mode_endpoint(self):
        """Test mode endpoint should return status."""
        response = requests.get(f"{API_BASE_URL}/api/test/mode", timeout=10)
        assert response.status_code == 200
        data = response.json()
        assert "test_mode_enabled" in data


class TestOrganizeEndpoint:
    """Test the /api/organize classification endpoint."""

    def test_organize_single_email(self):
        """Classify a single email - should return within 60 seconds."""
        payload = {
            "emails": [
                {
                    "thread_id": "test_integration_123",
                    "sender": "newsletter@example.com",
                    "subject": "Weekly Newsletter",
                    "body": "Hello, here is your weekly update with the latest news.",
                }
            ]
        }

        response = requests.post(f"{API_BASE_URL}/api/organize", json=payload, timeout=60)

        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )
        data = response.json()

        # Verify response structure
        assert "results" in data
        assert "model_version" in data
        assert len(data["results"]) == 1

        result = data["results"][0]
        assert "type" in result
        assert "type_conf" in result
        assert "decider" in result
        assert "labels" in result

        # Verify classification makes sense for newsletter
        assert result["type"] in ["newsletter", "notification", "promotion"]
        assert result["type_conf"] >= 0.5

    def test_organize_multiple_emails(self):
        """Classify multiple emails - batch of 3."""
        payload = {
            "emails": [
                {
                    "thread_id": "test_multi_1",
                    "sender": "calendar@google.com",
                    "subject": "Event: Team Meeting Tomorrow",
                    "body": "You have a meeting scheduled for tomorrow at 2pm.",
                },
                {
                    "thread_id": "test_multi_2",
                    "sender": "noreply@amazon.com",
                    "subject": "Your order has shipped",
                    "body": "Your order #123-456 has been shipped and will arrive Tuesday.",
                },
                {
                    "thread_id": "test_multi_3",
                    "sender": "friend@gmail.com",
                    "subject": "Hey, are you free this weekend?",
                    "body": "Want to grab coffee on Saturday?",
                },
            ]
        }

        response = requests.post(
            f"{API_BASE_URL}/api/organize",
            json=payload,
            timeout=120,  # Allow more time for multiple emails
        )

        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )
        data = response.json()

        assert len(data["results"]) == 3

        # Each result should have required fields
        for result in data["results"]:
            assert "type" in result
            assert "type_conf" in result
            assert "decider" in result

    def test_organize_empty_batch(self):
        """Empty email batch returns 422 - at least one email required."""
        payload = {"emails": []}

        response = requests.post(f"{API_BASE_URL}/api/organize", json=payload, timeout=30)

        # API requires at least one email - empty batch is invalid
        assert response.status_code == 422

    def test_organize_invalid_payload(self):
        """Invalid payload should return 422."""
        payload = {"not_emails": "invalid"}

        response = requests.post(f"{API_BASE_URL}/api/organize", json=payload, timeout=30)

        # FastAPI returns 422 for validation errors
        assert response.status_code == 422


class TestRateLimiting:
    """Test rate limiting behavior."""

    def test_rate_limit_headers_present(self):
        """Rate limit headers should be present in response."""
        payload = {
            "emails": [
                {
                    "thread_id": "test_ratelimit",
                    "sender": "test@test.com",
                    "subject": "Test",
                    "body": "Test body",
                }
            ]
        }

        response = requests.post(f"{API_BASE_URL}/api/organize", json=payload, timeout=60)

        # Check rate limit headers are present
        assert "X-RateLimit-Limit-Minute" in response.headers
        assert "X-RateLimit-Remaining-Minute" in response.headers


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
