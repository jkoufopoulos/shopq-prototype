#!/usr/bin/env python3
"""
Build golden dataset from real Gmail emails for Phase 0 of classification refactor.

This script pulls ~500 recent emails from your Gmail account (using your ShopQ labels
as ground truth for importance), extracts the fields needed for classification, and
creates a CSV golden dataset.

Required columns per CLASSIFICATION_REFACTOR_PLAN.md Phase 0:
- message_id, thread_id
- from_email, sender_domain
- subject, snippet/body_preview
- received_date, timezone
- email_type (from extension LLM classification)
- attention (from extension LLM classification)
- domains (from extension LLM classification)
- importance (GROUND TRUTH from ShopQ labels)
- current_labels (actual Gmail labels for validation)

Usage:
    python scripts/build_golden_dataset.py --output tests/golden_set/real_emails.csv
"""

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def extract_domain(email_address: str) -> str:
    """Extract domain from email address."""
    if not email_address or "@" not in email_address:
        return ""
    return email_address.split("@")[-1].lower()


def map_labels_to_importance(labels: list[str]) -> str:
    """
    Map Gmail labels to importance based on ShopQ sections.

    Current ShopQ sections (from digest):
    - CRITICAL: Critical priority emails
    - TODAY: Time-sensitive for today
    - COMING UP: Events/deadlines in next 7 days
    - WORTH KNOWING: Routine but useful
    - EVERYTHING ELSE: Low priority/noise
    """
    labels_lower = [label.lower() for label in labels]

    # Check for ShopQ labels first
    if any("mailq" in label for label in labels_lower):
        # Critical indicators
        if any(
            "critical" in label or "urgent" in label or "fraud" in label for label in labels_lower
        ):
            return "critical"
        # Time-sensitive indicators
        if any(
            "today" in label or "coming" in label or "deadline" in label for label in labels_lower
        ):
            return "time_sensitive"
        # Routine
        if any("worth" in label or "routine" in label for label in labels_lower):
            return "routine"

    # Fallback: use Gmail's IMPORTANT label as signal
    if "IMPORTANT" in labels:
        return "time_sensitive"

    # Default
    return "routine"


def extract_fields_from_csv_row(row: dict) -> dict:
    """
    Extract and normalize fields from existing CSV export format.

    Input CSV has columns: thread_id, subject, from_email, received_date, email_type,
    type_confidence, importance, importance_reason, decider, etc.
    """
    # Parse sender domain
    sender_domain = extract_domain(row.get("from_email", ""))

    # Parse timestamp
    received_date = row.get("received_date", "")
    try:
        dt = datetime.fromisoformat(received_date.replace("Z", "+00:00"))
        timestamp_utc = dt.isoformat()
        timezone_str = dt.strftime("%Z") or "UTC"
    except Exception:
        timestamp_utc = received_date
        timezone_str = "unknown"

    return {
        "message_id": row.get("thread_id", ""),  # Using thread_id as message_id
        "thread_id": row.get("thread_id", ""),
        "from_email": row.get("from_email", ""),
        "sender_domain": sender_domain,
        "subject": row.get("subject", ""),
        "snippet": "",  # Not in CSV exports - would need to pull from Gmail
        "received_date": timestamp_utc,
        "timezone": timezone_str,
        "email_type": row.get("email_type", ""),
        "type_confidence": row.get("type_confidence", ""),
        "attention": "",  # Not in CSV exports
        "domains": "",  # Not in CSV exports
        "importance": row.get("importance", "routine"),
        "importance_reason": row.get("importance_reason", ""),
        "decider": row.get("decider", ""),
        "current_labels": "",  # Not in CSV exports
        "entity_extracted": row.get("entity_extracted", ""),
        "entity_type": row.get("entity_type", ""),
    }


def aggregate_csv_exports(exports_dir: Path, max_emails: int = 500) -> list[dict]:
    """
    Aggregate email data from existing CSV exports.

    Returns list of email dicts with normalized fields.
    """
    csv_files = sorted(exports_dir.glob("shopq_session_*.csv"), reverse=True)

    if not csv_files:
        print(f"❌ No CSV files found in {exports_dir}")
        return []

    print(f"📁 Found {len(csv_files)} CSV export files")

    all_emails = []
    seen_threads = set()

    for csv_file in csv_files:
        if len(all_emails) >= max_emails:
            break

        print(f"  Reading {csv_file.name}...")
        try:
            with open(csv_file, encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    thread_id = row.get("thread_id", "")
                    if not thread_id or thread_id in seen_threads:
                        continue

                    seen_threads.add(thread_id)
                    email_data = extract_fields_from_csv_row(row)
                    all_emails.append(email_data)

                    if len(all_emails) >= max_emails:
                        break
        except Exception as e:
            print(f"  ⚠️  Error reading {csv_file.name}: {e}")
            continue

    print(f"✅ Collected {len(all_emails)} unique emails")
    return all_emails


def analyze_dataset(emails: list[dict]) -> dict:
    """Analyze dataset balance and coverage."""
    importance_counts = {}
    email_type_counts = {}
    domains_seen = set()

    for email in emails:
        importance = email.get("importance", "unknown")
        importance_counts[importance] = importance_counts.get(importance, 0) + 1

        email_type = email.get("email_type", "unknown")
        email_type_counts[email_type] = email_type_counts.get(email_type, 0) + 1

        domain = email.get("sender_domain", "")
        if domain:
            domains_seen.add(domain)

    total = len(emails)
    analysis = {
        "total_emails": total,
        "importance_distribution": importance_counts,
        "email_type_distribution": email_type_counts,
        "unique_domains": len(domains_seen),
        "balance_check": {},
    }

    # Check if any class exceeds 60% (requirement from migration plan)
    for importance, count in importance_counts.items():
        pct = (count / total * 100) if total > 0 else 0
        analysis["balance_check"][importance] = {
            "count": count,
            "percentage": round(pct, 1),
            "balanced": pct <= 60,
        }

    return analysis


def write_golden_dataset(emails: list[dict], output_path: Path):
    """Write golden dataset CSV."""
    if not emails:
        print("❌ No emails to write")
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Define column order
    columns = [
        "message_id",
        "thread_id",
        "from_email",
        "sender_domain",
        "subject",
        "snippet",
        "received_date",
        "timezone",
        "email_type",
        "type_confidence",
        "attention",
        "domains",
        "importance",
        "importance_reason",
        "decider",
        "current_labels",
        "entity_extracted",
        "entity_type",
    ]

    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(emails)

    print(f"✅ Wrote {len(emails)} emails to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Build golden dataset from existing CSV exports")
    parser.add_argument(
        "--exports-dir",
        type=Path,
        default=Path("exports"),
        help="Directory containing shopq_session_*.csv files",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("tests/golden_set/real_emails.csv"),
        help="Output CSV path",
    )
    parser.add_argument(
        "--max-emails", type=int, default=500, help="Maximum number of emails to include"
    )

    args = parser.parse_args()

    print("🚀 Building golden dataset from CSV exports...")
    print(f"   Source: {args.exports_dir}")
    print(f"   Output: {args.output}")
    print(f"   Max emails: {args.max_emails}")
    print()

    # Aggregate emails from CSV exports
    emails = aggregate_csv_exports(args.exports_dir, args.max_emails)

    if not emails:
        print("❌ No emails collected. Check that CSV exports exist.")
        sys.exit(1)

    # Analyze dataset
    print("\n📊 Dataset Analysis:")
    analysis = analyze_dataset(emails)
    print(f"  Total emails: {analysis['total_emails']}")
    print(f"  Unique domains: {analysis['unique_domains']}")
    print("\n  Importance distribution:")
    for importance, stats in analysis["balance_check"].items():
        balanced_icon = "✅" if stats["balanced"] else "⚠️ "
        print(f"    {balanced_icon} {importance}: {stats['count']} ({stats['percentage']}%)")

    print("\n  Email type distribution:")
    for email_type, count in analysis["email_type_distribution"].items():
        pct = (count / analysis["total_emails"] * 100) if analysis["total_emails"] > 0 else 0
        print(f"    {email_type}: {count} ({pct:.1f}%)")

    # Check Phase 0 requirements
    print("\n✅ Phase 0 Requirements Check:")
    status = "✅" if analysis["total_emails"] >= 500 else "❌"
    print(f"  {status} Emails >= 500: {analysis['total_emails']}")

    all_balanced = all(stats["balanced"] for stats in analysis["balance_check"].values())
    print(f"  {'✅' if all_balanced else '⚠️ '} No class > 60%: {all_balanced}")

    # Write dataset
    print()
    write_golden_dataset(emails, args.output)

    # Write analysis metadata
    metadata_path = args.output.parent / "real_emails_metadata.json"
    with open(metadata_path, "w") as f:
        json.dump(analysis, f, indent=2)
    print(f"✅ Wrote analysis to {metadata_path}")

    print("\n✅ Golden dataset created!")
    print("\n📝 Next steps:")
    print(f"   1. Review {args.output} for data quality")
    print("   2. If dataset needs more emails, pull more from Gmail API")
    print("   3. Proceed with Phase 0 validation")


if __name__ == "__main__":
    main()
