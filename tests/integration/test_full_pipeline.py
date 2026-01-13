"""End-to-end pipeline tests"""

from __future__ import annotations

import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "mailq"))


def test_complete_email_organization_flow():
    """Test the complete flow: Email Data → API → AI → Results"""

    print("🧪 Testing complete email organization pipeline...")

    # 1. Test AI components work
    try:
        from shopq.classification.memory_classifier import MemoryClassifier
        from shopq.classification.rules_engine import RulesEngine

        MemoryClassifier()
        RulesEngine()
        print("✅ AI components initialized")
    except Exception as e:
        print(f"❌ AI components failed: {e}")
        return False

    # 2. Prepare test email data
    test_emails = [
        {
            "subject": "Weekly team sync",
            "snippet": "Reminder about our Monday meeting",
            "from": "manager@company.com",
        },
        {
            "subject": "Your Amazon order has shipped",
            "snippet": "Track your package here",
            "from": "shipment-tracking@amazon.com",
        },
        {
            "subject": "LinkedIn: You appeared in 12 searches",
            "snippet": "See who's viewing your profile",
            "from": "notifications@linkedin.com",
        },
    ]
    print(f"📧 Testing with {len(test_emails)} sample emails")

    # 3. Test API endpoint with real data
    import requests

    try:
        response = requests.post(
            "http://localhost:8000/api/organize",
            json={"emails": test_emails},  # ✅ Correct payload format
            headers={"Content-Type": "application/json"},
        )

        if response.status_code != 200:
            print(f"❌ API returned status {response.status_code}")
            print(f"   Response: {response.text}")
            return False

        print("✅ API endpoint responding")

    except requests.exceptions.ConnectionError:
        print("❌ API endpoint failed: Connection refused (is the server running?)")
        print("   Start server with: cd mailq && python api.py")
        return False
    except Exception as e:
        print(f"❌ API endpoint failed: {e}")
        return False

    # 4. Test results format and content
    try:
        result = response.json()

        # Check response structure
        assert "results" in result, "Missing 'results' in response"
        assert isinstance(result["results"], list), "'results' should be a list"
        assert len(result["results"]) == len(test_emails), (
            f"Expected {len(test_emails)} results, got {len(result['results'])}"
        )

        print("✅ Response structure valid")

        # Check each classified email
        categories_found = set()
        for i, classified in enumerate(result["results"]):
            assert "category" in classified, f"Email {i} missing 'category'"
            assert "confidence" in classified, f"Email {i} missing 'confidence'"
            assert "source" in classified, f"Email {i} missing 'source'"

            categories_found.add(classified["category"])

            print(f"   • {test_emails[i]['subject'][:40]}...")
            print(
                "     → "
                f"{classified['category']} ({classified['confidence']}%) "
                f"[{classified['source']}]"
            )

        print("\n✅ Full pipeline test passed!")
        print(f"   Processed: {len(result['results'])} emails")
        print(f"   Categories found: {', '.join(sorted(categories_found))}")

        return True

    except AssertionError as e:
        print(f"❌ Results validation failed: {e}")
        print(f"   Response: {result}")
        return False
    except Exception as e:
        print(f"❌ Results parsing failed: {e}")
        return False


if __name__ == "__main__":
    success = test_complete_email_organization_flow()
    sys.exit(0 if success else 1)
