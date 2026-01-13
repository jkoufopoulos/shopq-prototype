#!/usr/bin/env python3
"""
Pull historical emails from Gmail and run ShopQ classification on them.

This pulls ~500 diverse emails, runs ShopQ's importance classifier,
then stratifies to fill coverage gaps for the golden dataset.

Target coverage gaps (need ~279 more after P0's 73):
- Events: +57
- Deadlines: +50
- Thread conversations: +53
- Bills/autopay: +40
- Receipts: +48
- Newsletters: +30
- Promotions: +40
- Deliveries: +40

Total: ~358, we'll pull 500 and stratify sample
"""

import argparse
import csv
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# Add project root to path to import ShopQ modules
sys.path.insert(0, str(Path(__file__).parent.parent))


def get_gmail_service():
    """Get authenticated Gmail API service."""
    creds = Credentials.from_authorized_user_file("credentials/token_gmail_api.json")
    return build("gmail", "v1", credentials=creds)


def get_existing_message_ids(dataset_paths: list[Path]) -> set[str]:
    """Get set of message IDs already in datasets."""
    existing_ids = set()
    for dataset_path in dataset_paths:
        if dataset_path.exists():
            with open(dataset_path) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    existing_ids.add(row["message_id"])
    return existing_ids


def fetch_diverse_emails(service, exclude_ids: set[str], total_target: int) -> list[dict]:
    """
    Fetch diverse historical emails using targeted queries.

    Aims to get good coverage of:
    - Events, deadlines, deliveries, bills, receipts, newsletters, promos, threads
    """
    emails = []
    seen_ids = set()

    # Calculate date range (last 6 months for diversity)
    end_date = datetime.now()
    start_date = end_date - timedelta(days=180)
    date_str = start_date.strftime("%Y/%m/%d")

    # Diverse query patterns targeting coverage gaps
    queries = [
        # Events (target: +57)
        f"label:ShopQ/Events after:{date_str}",
        f"subject:meeting after:{date_str}",
        f"subject:invite after:{date_str}",
        f"subject:(calendar OR event) after:{date_str}",
        # Receipts (target: +48)
        f"label:ShopQ/Receipts after:{date_str}",
        f"subject:(receipt OR order OR purchase) after:{date_str}",
        f"from:(amazon.com OR uber.com OR doordash.com) after:{date_str}",
        # Bills/Finance (target: +40)
        f"label:ShopQ/Finance after:{date_str}",
        f"subject:(bill OR invoice OR statement OR payment) after:{date_str}",
        f"subject:(autopay OR auto-pay) after:{date_str}",
        # Deliveries/Shipments (target: +40)
        f"subject:(delivery OR shipment OR tracking OR arriving) after:{date_str}",
        f'subject:"out for delivery" after:{date_str}',
        f'subject:"package" after:{date_str}',
        # Newsletters (target: +30)
        f"label:ShopQ/Newsletters after:{date_str}",
        f"from:substack.com after:{date_str}",
        f"from:beehiiv.com after:{date_str}",
        # Promotions (target: +40)
        f"label:ShopQ/Promotions after:{date_str}",
        f"category:promotions after:{date_str}",
        f'subject:(sale OR discount OR "% off") after:{date_str}',
        # Deadlines/Action Required (target: +50)
        f"label:ShopQ/Action-Required after:{date_str}",
        f'subject:(deadline OR "due date" OR expires OR expiring) after:{date_str}',
        f'subject:("action required" OR "attention needed") after:{date_str}',
        # Thread conversations (target: +53)
        f"in:sent after:{date_str}",  # Your sent emails = threads
        f"label:ShopQ/Messages after:{date_str}",
    ]

    print(f"📬 Fetching diverse historical emails (target: {total_target})")

    for query in queries:
        if len(emails) >= total_target:
            break

        try:
            print(f"\n   Query: {query}")
            results = (
                service.users()
                .messages()
                .list(
                    userId="me",
                    q=query,
                    maxResults=50,  # Limit per query to get diversity
                )
                .execute()
            )

            messages = results.get("messages", [])
            print(f"   Found {len(messages)} messages")

            fetched_this_query = 0

            for msg_ref in messages:
                if len(emails) >= total_target:
                    break

                msg_id = msg_ref["id"]

                # Skip if already in dataset or already seen
                if msg_id in exclude_ids or msg_id in seen_ids:
                    continue

                seen_ids.add(msg_id)

                # Fetch full message
                msg = (
                    service.users().messages().get(userId="me", id=msg_id, format="full").execute()
                )

                # Extract headers
                headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}

                subject = headers.get("Subject", "")
                from_email = headers.get("From", "")
                date = headers.get("Date", "")
                thread_id = msg.get("threadId", msg_id)
                snippet = msg.get("snippet", "")

                # Store for ShopQ classification
                emails.append(
                    {
                        "message_id": msg_id,
                        "thread_id": thread_id,
                        "from_email": from_email,
                        "subject": subject,
                        "snippet": snippet,
                        "received_date": date,
                        "gmail_labels": msg.get("labelIds", []),
                        "raw_payload": msg.get("payload", {}),
                    }
                )

                fetched_this_query += 1

            print(f"   ✅ Added {fetched_this_query} new emails (total: {len(emails)})")

        except Exception as e:
            print(f"   ⚠️  Error with query '{query}': {e}")
            continue

    return emails


def run_shopq_classification(emails: list[dict]) -> list[dict]:
    """
    Run ShopQ's importance classifier on emails.

    Returns emails with importance labels added.
    """
    print(f"\n🤖 Running ShopQ classification on {len(emails)} emails...")
    print("   (This would call ShopQ's classifier - for now using placeholder)")

    # TODO: Actually call ShopQ classification pipeline
    # For now, return emails with placeholder classifications
    # You'll need to wire this up to your actual classification logic

    classified = []
    for email in emails:
        # Placeholder: you'd actually call:
        # result = classify_email(email['subject'], email['snippet'], ...)

        email.update(
            {
                "email_type": "notification",  # TODO: from classifier
                "type_confidence": "0.85",
                "attention": "",
                "relationship": "",
                "domains": "",
                "domain_confidence": "",
                "importance": "routine",  # TODO: from classifier
                "importance_reason": "shopq_classifier_placeholder",
                "decider": "shopq_historical",
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
            }
        )

        # Remove temporary fields
        email.pop("gmail_labels", None)
        email.pop("raw_payload", None)

        classified.append(email)

    print(f"   ✅ Classified {len(classified)} emails")
    return classified


def main():
    parser = argparse.ArgumentParser(description="Classify historical Gmail emails with ShopQ")
    parser.add_argument(
        "--existing-datasets",
        nargs="+",
        type=Path,
        default=[
            Path("tests/golden_set/golden_dataset.csv"),
            Path("tests/golden_set/p0_critical_cases.csv"),
        ],
        help="Existing datasets to avoid duplicates",
    )
    parser.add_argument(
        "--output", type=Path, default=Path("tests/golden_set/historical_classified.csv")
    )
    parser.add_argument(
        "--target", type=int, default=500, help="Target number of emails to fetch and classify"
    )

    args = parser.parse_args()

    print("🚀 Fetching and classifying historical emails with ShopQ...")
    print(f"   Target: {args.target} emails")
    print()

    # Get existing IDs from all datasets
    print("📂 Loading existing datasets to avoid duplicates...")
    existing_ids = get_existing_message_ids(args.existing_datasets)
    print(f"   Found {len(existing_ids)} existing message IDs")
    print()

    # Authenticate
    print("🔐 Authenticating with Gmail API...")
    service = get_gmail_service()
    print("✅ Authenticated")
    print()

    # Fetch diverse emails
    emails = fetch_diverse_emails(service, existing_ids, args.target)

    if not emails:
        print("\n❌ No emails fetched!")
        return

    print(f"\n✅ Fetched {len(emails)} diverse historical emails")

    # Run ShopQ classification
    classified_emails = run_shopq_classification(emails)

    # Show preview distribution
    importance_dist = Counter(e["importance"] for e in classified_emails)
    Counter(e["email_type"] for e in classified_emails)

    print("\n📊 Importance distribution (placeholder):")
    for imp in ["routine", "time_sensitive", "critical"]:
        count = importance_dist.get(imp, 0)
        pct = (count / len(classified_emails) * 100) if classified_emails else 0
        print(f"   {imp}: {count} ({pct:.1f}%)")

    # Write output
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8", newline="") as f:
        if classified_emails:
            writer = csv.DictWriter(f, fieldnames=classified_emails[0].keys())
            writer.writeheader()
            writer.writerows(classified_emails)

    print(f"\n✅ Wrote {len(classified_emails)} classified emails to {args.output}")
    print("\n⚠️  NOTE: Classifications are currently placeholders!")
    print("   TODO: Wire up actual ShopQ classifier to run_shopq_classification()")
    print("\n📝 Next step: Stratify sample to fill coverage gaps")


if __name__ == "__main__":
    main()
