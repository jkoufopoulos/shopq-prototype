#!/usr/bin/env python3
"""
Export inbox emails to CSV for manual categorization review.

Usage:
    python scripts/export_inbox_for_review.py

Outputs:
    inbox_review.csv - All inbox emails with columns for manual categorization
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def get_gmail_service():
    """Get authenticated Gmail API service"""
    import pickle

    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

    creds = None
    token_path = Path.home() / ".config" / "mailq" / "token.pickle"

    # Load existing credentials
    if token_path.exists():
        with open(token_path, "rb") as token:
            creds = pickle.load(token)

    # If no valid credentials, authenticate
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # Try to use credentials.json from project root
            creds_file = Path(__file__).parent.parent / "credentials.json"
            if not creds_file.exists():
                print("❌ credentials.json not found!")
                print("Please download OAuth credentials from Google Cloud Console")
                sys.exit(1)

            flow = InstalledAppFlow.from_client_secrets_file(str(creds_file), SCOPES)
            creds = flow.run_local_server(port=0)

        # Save credentials
        token_path.parent.mkdir(parents=True, exist_ok=True)
        with open(token_path, "wb") as token:
            pickle.dump(creds, token)

    return build("gmail", "v1", credentials=creds)


def fetch_inbox_emails(service, max_results=100):
    """Fetch emails from inbox (excluding MailQ labeled emails)"""
    print(f"📬 Fetching up to {max_results} emails from inbox...")

    # Query: in inbox, not labeled by MailQ
    mailq_labels = [
        "MailQ/Receipts",
        "MailQ/Shopping",
        "MailQ/Messages",
        "MailQ/Work",
        "MailQ/Newsletters",
        "MailQ/Notifications",
        "MailQ/Events",
        "MailQ/Finance",
        "MailQ/Action-Required",
        "MailQ/Digest",
        "MailQ/Professional",
        "MailQ/Personal",
    ]
    exclude_labels = " ".join([f"-label:{label}" for label in mailq_labels])
    query = f"in:inbox {exclude_labels}"

    print(f"🔍 Query: {query}\n")

    emails = []
    page_token = None

    while len(emails) < max_results:
        # Fetch threads
        results = (
            service.users()
            .threads()
            .list(
                userId="me",
                q=query,
                maxResults=min(100, max_results - len(emails)),
                pageToken=page_token,
            )
            .execute()
        )

        threads = results.get("threads", [])
        if not threads:
            break

        print(f"📨 Found {len(threads)} threads in this batch...")

        # Fetch full thread details
        for thread in threads:
            thread_id = thread["id"]
            thread_data = (
                service.users()
                .threads()
                .get(
                    userId="me",
                    id=thread_id,
                    format="metadata",
                    metadataHeaders=["From", "Subject", "Date"],
                )
                .execute()
            )

            # Get first message in thread
            messages = thread_data.get("messages", [])
            if not messages:
                continue

            msg = messages[0]  # First message
            headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}

            # Get snippet from message (not thread)
            snippet = msg.get("snippet", "")

            emails.append(
                {
                    "thread_id": thread_id,
                    "message_id": msg["id"],
                    "from": headers.get("From", ""),
                    "subject": headers.get("Subject", ""),
                    "date": headers.get("Date", ""),
                    "snippet": snippet[:200],  # First 200 chars
                }
            )

            if len(emails) % 10 == 0:
                print(f"  ✓ Processed {len(emails)} emails...")

        # Check for next page
        page_token = results.get("nextPageToken")
        if not page_token:
            break

    print(f"\n✅ Fetched {len(emails)} emails\n")
    return emails


def export_to_csv(emails, output_path):
    """Export emails to CSV with categorization columns"""
    print(f"💾 Exporting to {output_path}...")

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        fieldnames = [
            "thread_id",
            "message_id",
            "from",
            "subject",
            "date",
            "snippet",
            # User categorization columns
            "should_feature",  # YES/NO - Should this be in the digest?
            "importance",  # CRITICAL/TIME_SENSITIVE/ROUTINE - Your classification
            "category",  # bill/fraud_alert/flight/event/receipt/promo/etc
            "reasoning",  # Why you categorized it this way
            "notes",  # Any additional notes
        ]

        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for email in emails:
            row = {
                "thread_id": email["thread_id"],
                "message_id": email["message_id"],
                "from": email["from"],
                "subject": email["subject"],
                "date": email["date"],
                "snippet": email["snippet"],
                # Empty columns for user to fill
                "should_feature": "",
                "importance": "",
                "category": "",
                "reasoning": "",
                "notes": "",
            }
            writer.writerow(row)

    print(f"✅ Exported {len(emails)} emails to CSV\n")
    print("📝 Instructions:")
    print("  1. Open inbox_review.csv in a spreadsheet app")
    print("  2. For each email, fill in:")
    print("     - should_feature: YES (show in digest) or NO (routine/noise)")
    print("     - importance: CRITICAL, TIME_SENSITIVE, or ROUTINE")
    print("     - category: bill, flight, event, receipt, promo, etc.")
    print("     - reasoning: Why you categorized it this way")
    print("     - notes: Any additional thoughts")
    print("\n💡 This will help us understand what YOU think the digest should look like!")


def main():
    output_path = Path(__file__).parent.parent / "inbox_review.csv"

    try:
        # Get Gmail service
        service = get_gmail_service()

        # Fetch emails
        emails = fetch_inbox_emails(service, max_results=100)

        if not emails:
            print("⚠️  No emails found in inbox (or all are already labeled)")
            return

        # Export to CSV
        export_to_csv(emails, output_path)

        print("\n🎉 Done! Review the file and fill in your categorization:")
        print(f"   {output_path}")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
