#!/usr/bin/env python3
"""
Merge CSV exports into golden dataset, deduplicating against existing emails.
"""

import argparse
import csv
from collections import Counter
from glob import glob
from pathlib import Path


def get_existing_thread_ids(dataset_path: Path) -> set:
    """Get set of thread IDs already in dataset."""
    existing_ids = set()

    if dataset_path.exists():
        with open(dataset_path) as f:
            reader = csv.DictReader(f)
            for row in reader:
                existing_ids.add(row["thread_id"])

    return existing_ids


def load_csv_exports(exports_dir: Path, exclude_thread_ids: set, max_emails: int):
    """Load emails from CSV exports, excluding duplicates."""
    emails = []
    seen_threads = set()

    # Get all CSV files
    csv_files = sorted(glob(str(exports_dir / "mailq_session_*.csv")))
    print(f"📂 Found {len(csv_files)} CSV export files")

    for csv_file in csv_files:
        try:
            with open(csv_file) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    thread_id = row.get("thread_id", row.get("ThreadID", ""))

                    # Skip if no thread_id or already seen
                    if not thread_id:
                        continue
                    if thread_id in exclude_thread_ids or thread_id in seen_threads:
                        continue

                    # Get importance from current_labels
                    labels = row.get("current_labels", row.get("CurrentLabels", ""))
                    importance = map_labels_to_importance(labels)

                    if not importance:
                        continue

                    seen_threads.add(thread_id)

                    # Add to dataset
                    emails.append(
                        {
                            "message_id": row.get("message_id", row.get("MessageID", thread_id)),
                            "thread_id": thread_id,
                            "from_email": row.get("from_email", row.get("From", "")),
                            "subject": row.get("subject", row.get("Subject", "")),
                            "received_date": row.get("received_date", row.get("ReceivedDate", "")),
                            "email_type": row.get(
                                "email_type", row.get("EmailType", "notification")
                            ),
                            "type_confidence": row.get("type_confidence", ""),
                            "attention": row.get("attention", ""),
                            "relationship": row.get("relationship", ""),
                            "domains": row.get("domains", ""),
                            "domain_confidence": row.get("domain_confidence", ""),
                            "importance": importance,
                            "importance_reason": f"csv_export_label_{labels}",
                            "decider": "csv_export",
                            "verifier_used": row.get("verifier_used", ""),
                            "verifier_verdict": row.get("verifier_verdict", ""),
                            "verifier_reason": row.get("verifier_reason", ""),
                            "entity_extracted": row.get("entity_extracted", ""),
                            "entity_type": row.get("entity_type", ""),
                            "entity_confidence": row.get("entity_confidence", ""),
                            "entity_details": row.get("entity_details", ""),
                            "in_digest": row.get("in_digest", ""),
                            "in_featured": row.get("in_featured", ""),
                            "in_orphaned": row.get("in_orphaned", ""),
                            "in_noise": row.get("in_noise", ""),
                            "noise_category": row.get("noise_category", ""),
                            "summary_line": row.get("summary_line", ""),
                            "summary_linked": row.get("summary_linked", ""),
                            "session_id": row.get("session_id", ""),
                            "timestamp": row.get("timestamp", ""),
                        }
                    )

                    if len(emails) >= max_emails:
                        print(f"✅ Reached target of {max_emails} new emails")
                        return emails

        except Exception as e:
            print(f"⚠️  Error reading {csv_file}: {e}")
            continue

    return emails


def map_labels_to_importance(labels: str) -> str:
    """Map Gmail labels to MailQ importance."""
    if not labels:
        return None

    labels_lower = labels.lower()

    if "mailq/critical" in labels_lower or "mailq/today" in labels_lower:
        return "critical"
    if "mailq/coming up" in labels_lower:
        return "time_sensitive"
    if "mailq/worth knowing" in labels_lower:
        return "routine"

    return None


def main():
    parser = argparse.ArgumentParser(description="Merge CSV exports to golden dataset")
    parser.add_argument(
        "--exports-dir",
        type=Path,
        default=Path("exports"),
        help="Directory containing mailq_session_*.csv files",
    )
    parser.add_argument(
        "--existing-dataset",
        type=Path,
        default=Path("tests/golden_set/golden_dataset_cleaned.csv"),
        help="Existing golden dataset (to avoid duplicates)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("tests/golden_set/csv_export_emails.csv"),
        help="Output CSV path for new emails",
    )
    parser.add_argument(
        "--max-emails", type=int, default=400, help="Maximum number of new emails to add"
    )

    args = parser.parse_args()

    print("🚀 Merging CSV exports into golden dataset...")
    print(f"   Exports directory: {args.exports_dir}")
    print(f"   Existing dataset: {args.existing_dataset}")
    print(f"   Output: {args.output}")
    print(f"   Max new emails: {args.max_emails}")
    print()

    # Get existing thread IDs
    print("📂 Loading existing dataset to avoid duplicates...")
    existing_threads = get_existing_thread_ids(args.existing_dataset)
    print(f"   Found {len(existing_threads)} existing threads")
    print()

    # Load CSV exports
    print("📥 Loading CSV exports...")
    new_emails = load_csv_exports(args.exports_dir, existing_threads, args.max_emails)

    if not new_emails:
        print("❌ No new emails found with MailQ importance labels!")
        return

    print(f"\n✅ Found {len(new_emails)} new emails")

    # Show distribution
    importance_dist = Counter(e["importance"] for e in new_emails)
    print("\n📊 Importance distribution:")
    for imp, count in sorted(importance_dist.items()):
        pct = count / len(new_emails) * 100
        print(f"   {imp}: {count} ({pct:.1f}%)")

    # Write output
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8", newline="") as f:
        if new_emails:
            writer = csv.DictWriter(f, fieldnames=new_emails[0].keys())
            writer.writeheader()
            writer.writerows(new_emails)

    print(f"\n✅ Wrote {len(new_emails)} new emails to {args.output}")
    print("\n📝 Next step: Merge with existing dataset to create final golden set")


if __name__ == "__main__":
    main()
