#!/usr/bin/env python3
"""
Pull emails from Gmail API to supplement golden dataset.

Fetches emails with MailQ labels, deduplicates against existing dataset,
and extracts fields needed for Phase 0 validation.
"""

import argparse
import csv
import pickle
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def get_gmail_service():
    """Authenticate and return Gmail API service."""
    creds = None

    # Look for existing token
    token_paths = [
        Path("credentials/token.json"),
        Path.home() / ".credentials" / "gmail_token.pickle",
    ]

    token_path = None
    for path in token_paths:
        if path.exists():
            token_path = path
            break

    # Try loading existing token (JSON format from extension)
    if token_path and token_path.suffix == ".json":
        try:
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        except Exception as e:
            print(f"⚠️  Could not load token from {token_path}: {e}")
            creds = None
    elif token_path and token_path.suffix == ".pickle":
        try:
            with open(token_path, "rb") as token:
                creds = pickle.load(token)
        except Exception as e:
            print(f"⚠️  Could not load token from {token_path}: {e}")
            creds = None

    # Refresh or get new credentials
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("🔄 Refreshing expired token...")
            creds.refresh(Request())
        else:
            # Look for credentials.json
            creds_paths = [
                Path("credentials/credentials.json"),
                Path("credentials.json"),
                Path.home() / ".credentials" / "credentials.json",
            ]

            creds_file = None
            for path in creds_paths:
                if path.exists():
                    creds_file = str(path)
                    print(f"📄 Using credentials from: {creds_file}")
                    break

            if not creds_file:
                raise FileNotFoundError(
                    "credentials.json not found. Download from Google Cloud Console and place in:\n"
                    "  ./credentials/credentials.json\n"
                    "  ./credentials.json\n"
                    "  ~/.credentials/credentials.json"
                )

            flow = InstalledAppFlow.from_client_secrets_file(creds_file, SCOPES)
            creds = flow.run_local_server(port=0)

        # Save token
        save_path = Path("credentials/token_gmail_api.json")
        save_path.parent.mkdir(parents=True, exist_ok=True)
        with open(save_path, "w") as token:
            token.write(creds.to_json())
        print(f"✅ Saved credentials to {save_path}")

    return build("gmail", "v1", credentials=creds)


def map_labels_to_importance(labels: list) -> str:
    """Map Gmail labels to MailQ importance."""
    label_lower = [label.lower() for label in labels]

    # Check for MailQ labels
    if any("mailq/critical" in label for label in label_lower) or any(
        "mailq/today" in label for label in label_lower
    ):
        return "critical"
    if any("mailq/coming up" in label for label in label_lower):
        return "time_sensitive"
    if any("mailq/worth knowing" in label for label in label_lower):
        return "routine"

    return None


def get_existing_message_ids(dataset_path: Path) -> set[str]:
    """Get set of message IDs already in dataset."""
    existing_ids = set()

    if dataset_path.exists():
        with open(dataset_path) as f:
            reader = csv.DictReader(f)
            for row in reader:
                existing_ids.add(row["message_id"])

    return existing_ids


def fetch_gmail_emails(service, max_emails: int, exclude_ids: set[str]):
    """Fetch emails from Gmail with MailQ labels."""
    emails = []

    # Query for emails with MailQ labels
    queries = [
        "label:MailQ/Critical",
        "label:MailQ/Today",
        'label:"MailQ/Coming Up"',
        'label:"MailQ/Worth Knowing"',
    ]

    seen_ids = set()

    for query in queries:
        print(f"📬 Searching: {query}")

        try:
            results = (
                service.users()
                .messages()
                .list(
                    userId="me",
                    q=query,
                    maxResults=500,  # Get plenty to account for deduplication
                )
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
                labels = msg.get("labelIds", [])

                # Map to importance
                importance = map_labels_to_importance(labels)
                if not importance:
                    continue

                emails.append(
                    {
                        "message_id": msg_id,
                        "thread_id": msg.get("threadId", msg_id),
                        "from_email": headers.get("From", ""),
                        "subject": headers.get("Subject", ""),
                        "received_date": headers.get("Date", ""),
                        "email_type": "notification",  # Default, will be classified later
                        "type_confidence": "",
                        "attention": "",
                        "relationship": "",
                        "domains": "",
                        "domain_confidence": "",
                        "importance": importance,
                        "importance_reason": f"gmail_label_{query.split(':')[-1]}",
                        "decider": "gmail_label",
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
            print(f"⚠️  Error fetching {query}: {e}")
            continue

    return emails


def main():
    parser = argparse.ArgumentParser(description="Pull emails from Gmail API for golden dataset")
    parser.add_argument(
        "--existing-dataset",
        type=Path,
        default=Path("tests/golden_set/golden_dataset_cleaned.csv"),
        help="Path to existing dataset (to avoid duplicates)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("tests/golden_set/gmail_emails.csv"),
        help="Output CSV path",
    )
    parser.add_argument(
        "--max-emails", type=int, default=500, help="Maximum number of emails to pull"
    )

    args = parser.parse_args()

    print("🚀 Pulling emails from Gmail API...")
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
    emails = fetch_gmail_emails(service, args.max_emails, existing_ids)

    if not emails:
        print("❌ No new emails fetched!")
        return

    print(f"\n✅ Fetched {len(emails)} new emails")

    # Show distribution
    from collections import Counter

    importance_dist = Counter(e["importance"] for e in emails)
    print("\n📊 Importance distribution:")
    for imp, count in importance_dist.items():
        pct = count / len(emails) * 100
        print(f"   {imp}: {count} ({pct:.1f}%)")

    # Write output
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8", newline="") as f:
        if emails:
            writer = csv.DictWriter(f, fieldnames=emails[0].keys())
            writer.writeheader()
            writer.writerows(emails)

    print(f"\n✅ Wrote {len(emails)} emails to {args.output}")
    print("\n📝 Next step: Merge with existing dataset to create final golden set")


if __name__ == "__main__":
    main()
