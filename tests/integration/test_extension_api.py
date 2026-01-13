"""Test Extension ↔ API communication"""

from __future__ import annotations

import pytest
import requests


@pytest.mark.skip(reason="Requires live API server - run manually")
def test_extension_to_api_communication():
    """Test that extension can communicate with API"""

    print("🧪 Testing Extension ↔ API communication...")

    # Test the exact endpoint the extension calls
    try:
        response = requests.post(
            "http://localhost:8000/api/organize",
            json={"action": "organize_all"},
            headers={"Content-Type": "application/json"},
        )

        if response.status_code == 200:
            result = response.json()
            print("✅ Extension → API communication working")
            print(f"   Response: {result}")
            return True
        print(f"❌ API returned status: {response.status_code}")
        return False

    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to API - make sure server is running:")
        print("   cd mailq && python api.py")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False


@pytest.mark.skip(reason="Requires live API server - run manually")
def test_cors_headers():
    """Test that API has proper CORS headers for extension"""
    try:
        response = requests.options("http://localhost:8000/api/organize")
        headers = response.headers

        # Check for CORS headers
        if "access-control-allow-origin" in headers:
            print("✅ CORS headers present")
            return True
        print("❌ CORS headers missing - extension may be blocked")
        return False

    except Exception as e:
        print(f"❌ CORS test failed: {e}")
        return False


if __name__ == "__main__":
    test_extension_to_api_communication()
    test_cors_headers()
