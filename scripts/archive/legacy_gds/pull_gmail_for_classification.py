#!/usr/bin/env python3
"""
Pull emails from Gmail with MailQ labels for manual importance labeling.

Since your labels are email_type based (Events, Receipts, etc.) not importance-based,
we'll pull emails and you can manually review/label them for the golden dataset.
"""

import argparse
import csv
import sqlite3
from collections import Counter
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


def get_gmail_service():
    """Get authenticated Gmail API service."""
    creds = Credentials.from_authorized_user_file("credentials/token_gmail_api.json")
    return build("gmail", "v1", credentials=creds)


def get_existing_message_ids(dataset_path: Path) -> set[str]:
    """Get set of message IDs already in dataset."""
    existing_ids = set()

    if dataset_path.exists():
        with open(dataset_path) as f:
            reader = csv.DictReader(f)
            for row in reader:
                existing_ids.add(row["message_id"])

    return existing_ids


def get_db_importance_for_thread(db_path: Path, thread_id: str) -> str:
    """Check if thread exists in database and get its importance."""
    if not db_path.exists():
        return None

    conn = sqlite3.connect(db_path)
    cursor = conn.execute(
        "SELECT importance FROM email_threads WHERE thread_id = ? LIMIT 1", (thread_id,)
    )
    row = cursor.fetchone()
    conn.close()

    if row and row[0] in ("routine", "time_sensitive", "critical"):
        return row[0]
    return None


def fetch_gmail_emails(service, exclude_ids: set[str], db_path: Path, max_emails: int):
    """Fetch emails from Gmail with MailQ labels."""
    emails = []
    seen_ids = set()

    # Pull from MailQ email type labels
    mailq_labels = [
        "MailQ/Events",
        "MailQ/Receipts",
        "MailQ/Notifications",
        "MailQ/Finance",
        "MailQ/Messages",
        "MailQ/Action-Required",
    ]

    for label in mailq_labels:
        print(f"📬 Searching: {label}")

        try:
            results = (
                service.users()
                .messages()
                .list(userId="me", q=f"label:{label}", maxResults=200)
                .execute()
            )

            messages = results.get("messages", [])
            print(f"   Found {len(messages)} messages")

            for msg_ref in messages:
                msg_id = msg_ref["id"]

                # Skip if already in dataset or already seen
                if msg_id in exclude_ids or msg_id in seen_ids:
                    continue

                seen_ids.add(msg_id)

                # Fetch full message
                msg = (
                    service.users()
                    .messages()
                    .get(
                        userId="me",
                        id=msg_id,
                        format="metadata",
                        metadataHeaders=["From", "Subject", "Date"],
                    )
                    .execute()
                )

                # Extract fields
                headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
                thread_id = msg.get("threadId", msg_id)

                # Check if we have importance from database
                importance = get_db_importance_for_thread(db_path, thread_id)

                if not importance:
                    # Skip emails we haven't classified yet
                    continue

                # Extract email type from label
                email_type = label.split("/")[-1].lower()
                if email_type == "action-required":
                    email_type = "notification"

                emails.append(
                    {
                        "message_id": msg_id,
                        "thread_id": thread_id,
                        "from_email": headers.get("From", ""),
                        "subject": headers.get("Subject", ""),
                        "received_date": headers.get("Date", ""),
                        "email_type": email_type,
                        "type_confidence": "",
                        "attention": "",
                        "relationship": "",
                        "domains": "",
                        "domain_confidence": "",
                        "importance": importance,
                        "importance_reason": f"db_lookup_thread_{thread_id}",
                        "decider": "mailq_db",
                        "verifier_used": "",
                        "verifier_verdict": "",
                        "verifier_reason": "",
                        "entity_extracted": "",
                        "entity_type": "",
                        "entity_confidence": "",
                        "entity_details": "",
                        "in_digest": "",
                        "in_featured": "",
                        "in_orphaned": "",
                        "in_noise": "",
                        "noise_category": "",
                        "summary_line": "",
                        "summary_linked": "",
                        "session_id": "",
                        "timestamp": "",
                    }
                )

                if len(emails) >= max_emails:
                    print(f"✅ Reached target of {max_emails} emails")
                    return emails

        except Exception as e:
            print(f"⚠️  Error fetching {label}: {e}")
            continue

    return emails


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--existing-dataset", type=Path, default=Path("tests/golden_set/golden_dataset_cleaned.csv")
    )
    parser.add_argument("--db", type=Path, default=Path("data/mailq_tracking.db"))
    parser.add_argument("--output", type=Path, default=Path("tests/golden_set/gmail_emails.csv"))
    parser.add_argument("--max-emails", type=int, default=400)

    args = parser.parse_args()

    print("🚀 Pulling emails from Gmail API...")
    print(f"   Database: {args.db}")
    print(f"   Existing dataset: {args.existing_dataset}")
    print(f"   Output: {args.output}")
    print(f"   Max emails: {args.max_emails}")
    print()

    # Get existing IDs
    print("📂 Loading existing dataset to avoid duplicates...")
    existing_ids = get_existing_message_ids(args.existing_dataset)
    print(f"   Found {len(existing_ids)} existing message IDs")
    print()

    # Authenticate
    print("🔐 Authenticating with Gmail API...")
    service = get_gmail_service()
    print("✅ Authenticated")
    print()

    # Fetch emails
    emails = fetch_gmail_emails(service, existing_ids, args.db, args.max_emails)

    if not emails:
        print("❌ No new emails fetched!")
        print("\n💡 This likely means:")
        print("   - All emails with MailQ labels are already in the dataset")
        print("   - OR emails with labels haven't been classified in the database yet")
        return

    print(f"\n✅ Fetched {len(emails)} new emails")

    # Show distribution
    importance_dist = Counter(e["importance"] for e in emails)
    print("\n📊 Importance distribution:")
    for imp in ["routine", "time_sensitive", "critical"]:
        count = importance_dist.get(imp, 0)
        pct = (count / len(emails) * 100) if emails else 0
        print(f"   {imp}: {count} ({pct:.1f}%)")

    # Write output
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8", newline="") as f:
        if emails:
            writer = csv.DictWriter(f, fieldnames=emails[0].keys())
            writer.writeheader()
            writer.writerows(emails)

    print(f"\n✅ Wrote {len(emails)} emails to {args.output}")


if __name__ == "__main__":
    main()
