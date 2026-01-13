"""

from __future__ import annotations

Test Context Digest API Endpoint

Simulates what the extension would send to /api/context-digest
"""

from datetime import datetime, timedelta

import requests


def create_realistic_email_batch():
    """Create realistic email data like extension would send"""
    now = datetime.now()

    return [
        # Flight tomorrow
        {
            "messageId": "flight001",
            "threadId": "thread001",
            "from": "confirmations@united.com",
            "subject": "United Flight 789 Confirmation - Tomorrow at 5:30 PM",
            "snippet": "Your flight UA789 departs tomorrow Oct 27, 2025 at 5:30 PM from SFO to LAX. Confirmation code: ABC123",
            "timestamp": (now - timedelta(hours=2)).isoformat(),
            "classification": {
                "type": "event",
                "type_conf": 0.95,
                "attention": "none",
                "attention_conf": 0.8,
                "relationship": "from_unknown",
                "relationship_conf": 0.7,
                "domains": ["professional"],
            },
        },
        # Bill due
        {
            "messageId": "bill001",
            "threadId": "thread002",
            "from": "billing@pge.com",
            "subject": "Your PG&E bill is due October 30",
            "snippet": "Your electric bill for October is due on October 30, 2025. Amount due: $127.45. Pay online at pge.com",
            "timestamp": (now - timedelta(hours=4)).isoformat(),
            "classification": {
                "type": "notification",
                "type_conf": 0.9,
                "attention": "action_required",
                "attention_conf": 0.95,
                "relationship": "from_unknown",
                "relationship_conf": 0.6,
                "domains": ["finance"],
            },
        },
        # Meeting reminder
        {
            "messageId": "meeting001",
            "threadId": "thread003",
            "from": "calendar-notification@google.com",
            "subject": "Reminder: Team Standup tomorrow at 10 AM",
            "snippet": "This is a reminder that Team Standup is scheduled for tomorrow, October 27 at 10:00 AM",
            "timestamp": (now - timedelta(hours=1)).isoformat(),
            "classification": {
                "type": "event",
                "type_conf": 0.92,
                "attention": "none",
                "attention_conf": 0.7,
                "relationship": "from_unknown",
                "relationship_conf": 0.5,
                "domains": ["professional"],
            },
        },
        # Newsletters (3)
        {
            "messageId": "news001",
            "threadId": "thread004",
            "from": "lenny@lennysnewsletter.com",
            "subject": "Lenny's Newsletter: Building AI products that ship",
            "snippet": "This week I interviewed Chip Huyen about practical AI applications...",
            "timestamp": (now - timedelta(hours=5)).isoformat(),
            "classification": {
                "type": "newsletter",
                "type_conf": 0.98,
                "attention": "none",
                "attention_conf": 0.9,
                "relationship": "from_unknown",
                "relationship_conf": 0.4,
                "domains": ["professional"],
            },
        },
        {
            "messageId": "news002",
            "threadId": "thread005",
            "from": "tldr@tldrnewsletter.com",
            "subject": "TLDR: Top tech news this week",
            "snippet": "Claude 4, new GPT models, and more...",
            "timestamp": (now - timedelta(hours=6)).isoformat(),
            "classification": {
                "type": "newsletter",
                "type_conf": 0.97,
                "attention": "none",
                "attention_conf": 0.9,
                "relationship": "from_unknown",
                "relationship_conf": 0.4,
                "domains": ["professional"],
            },
        },
        # Calendar invites (old)
        {
            "messageId": "cal001",
            "threadId": "thread006",
            "from": "calendar-notification@google.com",
            "subject": "Accepted: 1:1 with Sarah @ Mon Oct 27",
            "snippet": "You accepted this calendar invitation",
            "timestamp": (now - timedelta(hours=8)).isoformat(),
            "classification": {
                "type": "notification",
                "type_conf": 0.88,
                "attention": "none",
                "attention_conf": 0.95,
                "relationship": "from_unknown",
                "relationship_conf": 0.5,
                "domains": [],
            },
        },
        {
            "messageId": "cal002",
            "threadId": "thread007",
            "from": "calendar-notification@google.com",
            "subject": "Updated invitation: Team Meeting",
            "snippet": "Meeting time has been updated",
            "timestamp": (now - timedelta(hours=9)).isoformat(),
            "classification": {
                "type": "notification",
                "type_conf": 0.89,
                "attention": "none",
                "attention_conf": 0.95,
                "relationship": "from_unknown",
                "relationship_conf": 0.5,
                "domains": [],
            },
        },
        # Social
        {
            "messageId": "social001",
            "threadId": "thread008",
            "from": "notifications@linkedin.com",
            "subject": "You have 3 new connections",
            "snippet": "Mike, Sarah, and Alex accepted your connection requests",
            "timestamp": (now - timedelta(hours=10)).isoformat(),
            "classification": {
                "type": "notification",
                "type_conf": 0.91,
                "attention": "none",
                "attention_conf": 0.9,
                "relationship": "from_unknown",
                "relationship_conf": 0.3,
                "domains": ["professional"],
            },
        },
        # Promo
        {
            "messageId": "promo001",
            "threadId": "thread009",
            "from": "deals@target.com",
            "subject": "25% off home decor - ends tonight!",
            "snippet": "Shop our home sale ending tonight at midnight. 25% off everything.",
            "timestamp": (now - timedelta(hours=12)).isoformat(),
            "classification": {
                "type": "promotion",
                "type_conf": 0.96,
                "attention": "none",
                "attention_conf": 0.95,
                "relationship": "from_unknown",
                "relationship_conf": 0.2,
                "domains": ["shopping"],
            },
        },
        # Subscription renewal
        {
            "messageId": "sub001",
            "threadId": "thread010",
            "from": "billing@spotify.com",
            "subject": "Your Spotify Premium subscription has been renewed",
            "snippet": "$9.99 has been charged to your card ending in 1234",
            "timestamp": (now - timedelta(hours=14)).isoformat(),
            "classification": {
                "type": "notification",
                "type_conf": 0.87,
                "attention": "none",
                "attention_conf": 0.8,
                "relationship": "from_unknown",
                "relationship_conf": 0.4,
                "domains": [],
            },
        },
    ]


def test_api_endpoint(url: str = "http://localhost:8000/api/context-digest"):
    """Test the context digest API endpoint"""
    print("=" * 60)
    print("Testing Context Digest API")
    print("=" * 60)

    # Create email batch
    emails = create_realistic_email_batch()

    print(f"\n📧 Created {len(emails)} realistic emails:")
    for i, email in enumerate(emails, 1):
        email_type = email["classification"]["type"]
        print(f"{i:2d}. [{email_type:12s}] {email['subject'][:50]}")

    # Prepare request
    request_data = {"current_data": emails}

    print(f"\n🌐 Sending POST request to {url}...")

    try:
        response = requests.post(
            url, json=request_data, headers={"Content-Type": "application/json"}, timeout=60
        )

        if response.status_code == 200:
            result = response.json()

            print("\n✅ Success!")
            print("=" * 60)

            # Print metadata
            if "metadata" in result:
                meta = result["metadata"]
                print("\n📊 Statistics:")
                print(f"   Word count: {meta.get('word_count')}")
                print(f"   Entities extracted: {meta.get('entities_count')}")
                print(f"   Featured: {meta.get('featured_count')}")
                print(f"   Critical: {meta.get('critical_count')}")
                print(f"   Time-sensitive: {meta.get('time_sensitive_count')}")
                print(f"   Routine: {meta.get('routine_count')}")
                print(f"   Verified: {'✅' if meta.get('verified') else '❌'}")
                print(f"   Fallback: {meta.get('fallback', False)}")

            # Extract and print text from HTML
            html = result.get("html", "")

            # Save HTML
            with open("test_output_api.html", "w") as f:
                f.write(html)

            print("\n✅ HTML saved to: test_output_api.html")
            print(f"\nSubject: {result.get('subject')}")

            print("\n📧 To view the digest:")
            print("   open test_output_api.html")

            return result

        print(f"\n❌ Error: {response.status_code}")
        print(response.text)
        return None

    except requests.exceptions.ConnectionError:
        print("\n❌ Connection Error")
        print("\n⚠️  API server is not running!")
        print("\nTo start the server:")
        print("   uvicorn shopq.api:app --reload")
        print("\nThen run this script again.")
        return None

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
        return None


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test context digest API")
    parser.add_argument(
        "--url", default="http://localhost:8000/api/context-digest", help="API endpoint URL"
    )
    args = parser.parse_args()

    test_api_endpoint(args.url)
