#!/usr/bin/env python3
"""
Fetch diverse emails to fill gaps in golden dataset after deduplication.

Avoids duplicate subjects and ensures good coverage across email types.
"""

import csv
import sys
from datetime import datetime, timedelta
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

sys.path.insert(0, str(Path(__file__).parent.parent))


def get_gmail_service():
    """Get authenticated Gmail API service."""
    creds = Credentials.from_authorized_user_file("credentials/token_gmail_api.json")
    return build("gmail", "v1", credentials=creds)


def get_existing_subjects(dataset_path):
    """Get set of subjects already in dataset."""
    existing = set()
    if dataset_path.exists():
        with open(dataset_path) as f:
            reader = csv.DictReader(f)
            for row in reader:
                existing.add(row.get("subject", "").strip())
    return existing


def fetch_emails_by_query(service, query, max_results, existing_subjects):
    """Fetch emails matching query, avoiding duplicates."""
    emails = []

    try:
        results = (
            service.users()
            .messages()
            .list(
                userId="me",
                q=query,
                maxResults=max_results * 3,  # Fetch extra to account for duplicates
            )
            .execute()
        )

        messages = results.get("messages", [])

        for msg_ref in messages:
            if len(emails) >= max_results:
                break

            msg_id = msg_ref["id"]
            msg = service.users().messages().get(userId="me", id=msg_id, format="full").execute()

            headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
            subject = headers.get("Subject", "").strip()

            # Skip if duplicate subject
            if subject in existing_subjects:
                continue

            existing_subjects.add(subject)

            emails.append(
                {
                    "message_id": msg_id,
                    "thread_id": msg.get("threadId", msg_id),
                    "from_email": headers.get("From", ""),
                    "subject": subject,
                    "snippet": msg.get("snippet", ""),
                    "received_date": headers.get("Date", ""),
                    "email_type": "",
                    "type_confidence": "",
                    "attention": "",
                    "relationship": "",
                    "domains": "",
                    "domain_confidence": "",
                    "importance": "routine",  # Placeholder
                    "importance_reason": "diversity_fetch_placeholder",
                    "decider": "diversity_fetch",
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
                    "timestamp": datetime.now().isoformat(),
                    "source_dataset": "diversity_fetch",
                    "p0_category": "",
                }
            )

    except Exception as e:
        print(f"   ⚠️  Error with query '{query}': {e}")

    return emails


def main():
    input_path = Path("tests/golden_set/golden_dataset_deduplicated.csv")
    output_path = Path("tests/golden_set/golden_dataset_500_diverse.csv")

    if not input_path.exists():
        print(f"❌ Input file not found: {input_path}")
        return

    print("🔍 Fetching diverse emails to reach 500 total...")
    print(f"   Input: {input_path}")

    # Load existing dataset
    with open(input_path) as f:
        reader = csv.DictReader(f)
        existing_emails = list(reader)

    print(f"   Current: {len(existing_emails)} emails")
    needed = 500 - len(existing_emails)
    print(f"   Need: {needed} more emails")

    # Get existing subjects
    existing_subjects = get_existing_subjects(input_path)
    print(f"   Avoiding {len(existing_subjects)} existing subjects")

    # Authenticate
    print("\n🔐 Authenticating with Gmail API...")
    service = get_gmail_service()
    print("✅ Authenticated")

    # Date range for diversity (last 12 months)
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)
    date_str = start_date.strftime("%Y/%m/%d")

    # Diverse queries to fill gaps
    queries = [
        # Events (20 emails)
        (f"subject:(conference OR summit OR webinar) after:{date_str}", 7, "conferences"),
        (f"subject:(reservation OR booking) after:{date_str}", 7, "reservations"),
        (f"subject:(flight OR airline) after:{date_str}", 6, "flights"),
        # Receipts (15 emails)
        (
            f"subject:(receipt OR order) from:(target.com OR walmart.com) after:{date_str}",
            5,
            "retail receipts",
        ),
        (
            f"subject:(receipt OR order) from:(lyft.com OR uber.com) after:{date_str}",
            5,
            "ride receipts",
        ),
        (
            f"subject:purchase from:(apple.com OR google.com) after:{date_str}",
            5,
            "tech purchases",
        ),
        # Bills/Invoices (15 emails)
        (f"subject:(bill OR invoice OR statement) after:{date_str}", 8, "bills"),
        (f"subject:(payment OR autopay) after:{date_str}", 7, "payments"),
        # Newsletters (10 emails)
        (
            f"from:(substack.com OR beehiiv.com OR medium.com) after:{date_str}",
            10,
            "newsletters",
        ),
        # Deliveries (10 emails)
        (
            f"subject:(shipped OR tracking) from:(fedex.com OR ups.com) after:{date_str}",
            5,
            "shipment tracking",
        ),
        (f"subject:(delivered OR delivery) after:{date_str}", 5, "deliveries"),
        # Promotions (10 emails)
        (f"category:promotions subject:(sale OR discount) after:{date_str}", 10, "sales"),
        # Thread updates (8 emails)
        (f"in:sent after:{date_str}", 8, "sent emails"),
    ]

    new_emails = []

    for query, target_count, description in queries:
        if len(new_emails) >= needed:
            break

        print(f"\n📬 Fetching {description} (target: {target_count})...")
        emails = fetch_emails_by_query(service, query, target_count, existing_subjects)
        new_emails.extend(emails)
        print(f"   ✅ Fetched {len(emails)} unique emails (total: {len(new_emails)})")

    # Combine with existing
    all_emails = existing_emails + new_emails[:needed]

    print("\n📊 Final dataset:")
    print(f"   Existing: {len(existing_emails)}")
    print(f"   New: {len(new_emails[:needed])}")
    print(f"   Total: {len(all_emails)}")

    # Write output
    with open(output_path, "w", newline="") as f:
        if all_emails:
            writer = csv.DictWriter(f, fieldnames=all_emails[0].keys())
            writer.writeheader()
            writer.writerows(all_emails)

    print(f"\n✅ Saved to {output_path}")
    print("\n📝 Next steps:")
    print("   1. Replace golden_dataset_500.csv with this new dataset")
    print("   2. Reset labeling progress")
    print("   3. Continue labeling")


if __name__ == "__main__":
    main()
