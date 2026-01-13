from __future__ import annotations

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import pandas as pd
import requests


class TestAPIIntegration:
    def setup_method(self):
        self.base_url = "http://localhost:8000"
        # Load REAL data from your CSV
        csv_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "data",
            "100_emails",
            "email_eval_dataset.csv",
        )

        if os.path.exists(csv_path):
            df = pd.read_csv(csv_path)
            # Take first 5 emails for testing
            self.test_emails = []
            for _, row in df.head(5).iterrows():
                self.test_emails.append(
                    {
                        "subject": row["subject"],
                        "snippet": row["snippet"],
                        "from": row.get("from", "unknown@example.com"),
                    }
                )
            print(f"✅ Loaded {len(self.test_emails)} real emails from dataset")
        else:
            # Fallback to sample data
            self.test_emails = [
                {
                    "subject": "Team meeting tomorrow",
                    "snippet": "Reminder about our weekly team meeting",
                    "from": "colleague@company.com",
                }
            ]
            print("⚠️  Using sample data (real dataset not found)")

    def test_organize_endpoint(self):
        print("\n🧪 Testing /api/organize with real email data...")

        try:
            response = requests.post(
                f"{self.base_url}/api/organize",
                json={"emails": self.test_emails},
                headers={"Content-Type": "application/json"},
            )

            if response.status_code == 200:
                result = response.json()
                print("✅ Organization successful!")
                print(f"   Processed: {len(result.get('results', []))} emails")

                # Show first result
                if result.get("results"):
                    first = result["results"][0]
                    subject = first.get("subject")
                    category = first.get("category")
                    confidence = first.get("confidence")
                    print(f"   Example: '{subject}' → {category} ({confidence}%)")
            else:
                print(f"❌ Organization failed: Status {response.status_code}")
                print(f"   Response: {response.text}")

        except requests.exceptions.ConnectionError:
            print("❌ API server not running - start with: python shopq/api.py")
        except Exception as e:
            print(f"❌ Unexpected error: {e}")


if __name__ == "__main__":
    test = TestAPIIntegration()
    test.setup_method()
    test.test_organize_endpoint()
