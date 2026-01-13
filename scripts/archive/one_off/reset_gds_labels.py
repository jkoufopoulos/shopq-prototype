#!/usr/bin/env python3
"""
Reset GDS to unlabeled state - keep only core email fields

This strips all labels (email_type, importance, client_label, etc.)
and keeps only: message_id, thread_id, from_email, subject, snippet, received_date

Usage:
    uv run python scripts/reset_gds_labels.py \
        --input tests/golden_set/gds-2.0-with-client-labels.csv \
        --output tests/golden_set/gds-2.0-unlabeled.csv
"""

import csv
import sys
from pathlib import Path


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Reset GDS to unlabeled state")
    parser.add_argument("--input", required=True, help="Input GDS CSV with labels")
    parser.add_argument("--output", required=True, help="Output unlabeled GDS CSV")
    args = parser.parse_args()

    input_path = Path(args.input).expanduser()
    output_path = Path(args.output).expanduser()

    if not input_path.exists():
        print(f"❌ Input file not found: {input_path}")
        sys.exit(1)

    print(f"📖 Reading {input_path}...")

    # Read all emails
    with open(input_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        emails = list(reader)

    print(f"   Total emails: {len(emails)}")

    # Keep only core fields
    core_fields = ["message_id", "thread_id", "from_email", "subject", "snippet", "received_date"]

    # Create unlabeled emails with only core fields
    unlabeled_emails = []
    for email in emails:
        unlabeled = {field: email.get(field, "") for field in core_fields}
        unlabeled_emails.append(unlabeled)

    # Write unlabeled CSV
    print(f"\n💾 Writing unlabeled emails to {output_path}...")
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=core_fields)
        writer.writeheader()
        writer.writerows(unlabeled_emails)

    print("\n✅ GDS reset complete!")
    print(f"   Output: {output_path}")
    print(f"   Emails: {len(unlabeled_emails)}")
    print(f"   Fields: {', '.join(core_fields)}")
    print("\nReady for fresh manual labeling!")


if __name__ == "__main__":
    main()
