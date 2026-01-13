"""Test extension with live API"""

from __future__ import annotations

import pytest
import requests


@pytest.mark.skip(reason="Requires live API server - run manually with: uvicorn mailq.api.app:app")
def test_extension_api():
    """Simulate what the extension sends to API"""

    # Sample unread emails (like extension would send)
    test_emails = [
        {
            "from": "deals@amazon.com",
            "subject": "50% off electronics today!",
            "snippet": "Limited time offer on laptops and tablets",
        },
        {
            "from": "notifications@github.com",
            "subject": "New pull request on mailq-prototype",
            "snippet": "Alice opened a PR for #123",
        },
        {
            "from": "calendar@google.com",
            "subject": "Meeting reminder: Team Standup",
            "snippet": "Starts in 15 minutes",
        },
    ]

    print("🧪 Testing extension → API flow\n")
    print(f"📧 Sending {len(test_emails)} unread emails...\n")

    # Send to API
    response = requests.post(
        "http://localhost:8000/api/organize", json={"emails": test_emails}, timeout=30
    )

    assert response.status_code == 200, f"API returned {response.status_code}"

    data = response.json()
    results = data["results"]

    print("✅ API Response:\n")
    for i, (email, result) in enumerate(zip(test_emails, results, strict=False), 1):
        print(f"{i}. {email['subject'][:50]}...")
        print(f"   From: {email['from']}")
        print(f"   → {result['category']} ({result['confidence']}%) [{result['source']}]")
        print()

    print("✅ Extension integration test passed!")


if __name__ == "__main__":
    test_extension_api()
