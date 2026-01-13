"""

from __future__ import annotations

Fetch real emails from Gmail and test Context Digest

Uses Gmail API to fetch recent emails, classify them, then generate context digest.
"""

import sys

sys.path.insert(0, "/Users/justinkoufopoulos/Projects/mailq-prototype")

import os
import pickle
from datetime import datetime

from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from mailq.classification.memory_classifier import MemoryClassifier
from mailq.digest.category_manager import CategoryManager
from mailq.digest.context_digest import ContextDigest

# Gmail API scopes
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def get_gmail_service():
    """Authenticate and return Gmail service"""
    creds = None
    token_path = "token.pickle"

    # Load existing credentials
    if os.path.exists(token_path):
        with open(token_path, "rb") as token:
            creds = pickle.load(token)

    # If no valid credentials, authenticate
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # Need credentials.json from Google Cloud Console
            if not os.path.exists("credentials.json"):
                print("\n❌ Missing credentials.json")
                print("\nTo get Gmail API access:")
                print("1. Go to https://console.cloud.google.com/")
                print("2. Enable Gmail API")
                print("3. Create OAuth 2.0 credentials")
                print("4. Download as credentials.json")
                print("5. Place in project root")
                return None

            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)

        # Save credentials
        with open(token_path, "wb") as token:
            pickle.dump(creds, token)

    return build("gmail", "v1", credentials=creds)


def fetch_recent_emails(service, max_results: int = 20):
    """Fetch recent emails from Gmail"""
    try:
        # Fetch messages from last 24 hours
        query = "newer_than:1d"

        results = (
            service.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
        )

        messages = results.get("messages", [])

        if not messages:
            print("\n⚠️  No recent emails found in last 24 hours")
            print("Trying last 7 days...")

            # Try 7 days
            results = (
                service.users()
                .messages()
                .list(userId="me", q="newer_than:7d", maxResults=max_results)
                .execute()
            )
            messages = results.get("messages", [])

        print(f"\n📧 Found {len(messages)} emails")

        # Fetch full email details
        emails = []
        for msg in messages:
            msg_id = msg["id"]
            msg_data = (
                service.users().messages().get(userId="me", id=msg_id, format="full").execute()
            )

            # Extract headers
            headers = {h["name"]: h["value"] for h in msg_data["payload"]["headers"]}

            # Extract snippet
            snippet = msg_data.get("snippet", "")

            email = {
                "id": msg_id,
                "threadId": msg_data.get("threadId", ""),
                "from": headers.get("From", ""),
                "subject": headers.get("Subject", ""),
                "snippet": snippet,
                "timestamp": datetime.fromtimestamp(
                    int(msg_data["internalDate"]) / 1000
                ).isoformat(),
                "labels": msg_data.get("labelIds", []),
            }
            emails.append(email)

        return emails

    except Exception as e:
        print(f"❌ Error fetching emails: {e}")
        return []


def classify_emails(emails):
    """Classify emails using MailQ classifier"""
    print(f"\n🏷️  Classifying {len(emails)} emails...")

    classifier = MemoryClassifier(CategoryManager())

    classified = []
    for email in emails:
        try:
            result = classifier.classify_email(
                subject=email["subject"], snippet=email["snippet"], sender=email["from"]
            )

            email["classification"] = {
                "type": result.get("type", "notification"),
                "type_con": result.get("type_conf", 0.0),
                "domains": result.get("domains", []),
                "attention": result.get("attention", "none"),
                "attention_con": result.get("attention_conf", 0.0),
                "relationship": result.get("relationship", "from_unknown"),
                "relationship_con": result.get("relationship_conf", 0.0),
            }
            classified.append(email)

        except Exception as e:
            print(f"⚠️  Error classifying: {email['subject'][:50]} - {e}")
            continue

    print(f"✅ Classified {len(classified)} emails")
    return classified


def main():
    """Main function"""
    print("=" * 60)
    print("Test Context Digest with Real Gmail Data")
    print("=" * 60)

    # Get Gmail service
    print("\n🔐 Authenticating with Gmail...")
    service = get_gmail_service()

    if not service:
        return

    print("✅ Gmail authenticated")

    # Fetch emails
    emails = fetch_recent_emails(service, max_results=20)

    if not emails:
        print("\n❌ No emails found")
        return

    # Show sample
    print("\n📧 Sample emails:")
    for i, email in enumerate(emails[:5], 1):
        print(f"{i}. {email['subject'][:60]}")

    # Classify emails
    classified = classify_emails(emails)

    if not classified:
        print("\n❌ No emails classified")
        return

    # Show classification breakdown
    print("\n📊 Classification breakdown:")
    types = {}
    for email in classified:
        email_type = email["classification"]["type"]
        types[email_type] = types.get(email_type, 0) + 1

    for email_type, count in sorted(types.items(), key=lambda x: x[1], reverse=True):
        print(f"   - {email_type}: {count}")

    # Convert to context digest format
    digest_emails = []
    for email in classified:
        classification = email["classification"]
        digest_email = {
            "id": email["id"],
            "thread_id": email["threadId"],
            "subject": email["subject"],
            "snippet": email["snippet"],
            "from_email": email["from"],
            "from_name": email["from"].split("<")[0].strip()
            if "<" in email["from"]
            else email["from"].split("@")[0],
            "type": classification["type"],
            "attention": classification["attention"],
            "domains": classification["domains"],
            "relationship": classification["relationship"],
            "timestamp": email["timestamp"],
        }
        digest_emails.append(digest_email)

    # Generate context digest
    print(f"\n🌟 Generating Context Digest from {len(digest_emails)} real emails...")
    print("=" * 60)

    digest = ContextDigest(verbose=True)
    result = digest.generate(digest_emails)

    # Print results
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)

    print("\n📊 Statistics:")
    print(f"   Total emails: {len(digest_emails)}")
    print(f"   Word count: {result['word_count']}")
    print(f"   Entities extracted: {result['entities_count']}")
    print(f"   Featured: {result['featured_count']}")
    print(f"   Critical: {result.get('critical_count', 0)}")
    print(f"   Time-sensitive: {result.get('time_sensitive_count', 0)}")
    print(f"   Routine: {result.get('routine_count', 0)}")
    print(f"   Verified: {'✅' if result['verified'] else '❌'}")
    print(f"   Fallback: {result.get('fallback', False)}")

    if result.get("noise_breakdown"):
        print("\n📊 Noise breakdown:")
        for category, count in result["noise_breakdown"].items():
            print(f"   - {category}: {count}")

    print("\n📧 Generated Digest:")
    print("=" * 60)
    print(result["text"])
    print("=" * 60)

    # Save HTML
    output_path = "test_output_real_gmail.html"
    with open(output_path, "w") as f:
        f.write(result["html"])

    print(f"\n✅ HTML saved to: {output_path}")
    print(f"\nTo view: open {output_path}")


if __name__ == "__main__":
    main()
