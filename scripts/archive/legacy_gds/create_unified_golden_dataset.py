#!/usr/bin/env python3
"""
Create unified golden dataset by combining synthetic and real emails.

This merges:
1. 240 synthetic emails (perfect balance, complete fields)
2. 298 real emails (actual Gmail data with ShopQ labels)

Total: 538 emails for Phase 0 golden dataset
"""

import csv
import json
from collections import Counter
from pathlib import Path


def load_synthetic_emails():
    """Load synthetic emails from messages.jsonl and labels.json."""
    messages_path = Path("tests/golden_set/messages.jsonl")
    labels_path = Path("tests/golden_set/labels.json")

    messages = []
    with open(messages_path) as f:
        for line in f:
            messages.append(json.loads(line))

    with open(labels_path) as f:
        labels = json.load(f)

    # Convert to unified format
    emails = []
    for msg in messages:
        msg_id = msg["id"]
        importance = labels.get(msg_id, {}).get("importance", "routine")

        emails.append(
            {
                "message_id": msg["id"],
                "thread_id": msg["thread_id"],
                "from_email": msg["from"],
                "sender_domain": msg["from"].split("@")[-1] if "@" in msg["from"] else "",
                "subject": msg["subject"],
                "snippet": msg["snippet"],
                "received_date": msg["timestamp"],
                "timezone": "UTC",
                "email_type": msg["type"],
                "type_confidence": "1.0",  # Synthetic data is deterministic
                "attention": msg["attention"],
                "domains": ",".join(msg["domains"]) if msg["domains"] else "",
                "importance": importance,
                "importance_reason": f"synthetic_{msg['type']}",
                "decider": "synthetic",
                "current_labels": "",
                "entity_extracted": "0",
                "entity_type": "",
                "source": "synthetic",
            }
        )

    return emails


def load_real_emails():
    """Load real emails from deduplicated database CSV."""
    real_path = Path("tests/golden_set/golden_dataset_from_db.csv")

    emails = []
    with open(real_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            row["source"] = "real"
            emails.append(row)

    return emails


def analyze_combined(emails):
    """Analyze combined dataset."""
    total = len(emails)

    importance_counts = Counter(e["importance"] for e in emails)
    email_type_counts = Counter(e["email_type"] for e in emails)
    source_counts = Counter(e["source"] for e in emails)

    analysis = {
        "total_emails": total,
        "importance_distribution": dict(importance_counts),
        "email_type_distribution": dict(email_type_counts),
        "source_distribution": dict(source_counts),
        "balance_check": {},
    }

    # Check balance
    for importance, count in importance_counts.items():
        pct = (count / total * 100) if total > 0 else 0
        analysis["balance_check"][importance] = {
            "count": count,
            "percentage": round(pct, 1),
            "balanced": pct <= 60,
        }

    return analysis


def write_unified_dataset(emails, output_path):
    """Write unified golden dataset."""
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
        "source",
    ]

    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(emails)

    print(f"✅ Wrote {len(emails)} emails to {output_path}")


def main():
    print("🚀 Creating unified golden dataset...")
    print()

    # Load datasets
    print("📂 Loading synthetic emails...")
    synthetic = load_synthetic_emails()
    print(f"   Loaded {len(synthetic)} synthetic emails")

    print("📂 Loading real emails...")
    real = load_real_emails()
    print(f"   Loaded {len(real)} real emails")

    # Combine
    all_emails = synthetic + real
    print(f"\n✅ Combined: {len(all_emails)} total emails")

    # Analyze
    print("\n📊 Dataset Analysis:")
    analysis = analyze_combined(all_emails)

    print(f"  Total: {analysis['total_emails']}")
    print("\n  Sources:")
    for source, count in analysis["source_distribution"].items():
        pct = count / analysis["total_emails"] * 100
        print(f"    {source}: {count} ({pct:.1f}%)")

    print("\n  Importance distribution:")
    for importance, stats in analysis["balance_check"].items():
        balanced_icon = "✅" if stats["balanced"] else "⚠️ "
        print(f"    {balanced_icon} {importance}: {stats['count']} ({stats['percentage']}%)")

    print("\n  Email type distribution:")
    for email_type, count in analysis["email_type_distribution"].items():
        pct = count / analysis["total_emails"] * 100
        print(f"    {email_type}: {count} ({pct:.1f}%)")

    # Check Phase 0 requirements
    print("\n✅ Phase 0 Requirements Check:")
    status = "✅" if analysis["total_emails"] >= 500 else "❌"
    print(f"  {status} Emails >= 500: {analysis['total_emails']}")

    all_balanced = all(stats["balanced"] for stats in analysis["balance_check"].values())
    print(f"  {'✅' if all_balanced else '⚠️ '} No class > 60%: {all_balanced}")

    # Check field completeness
    complete_fields = 0
    for email in all_emails:
        if email.get("from_email") and email.get("subject") and email.get("importance"):
            complete_fields += 1

    completeness_pct = (complete_fields / len(all_emails) * 100) if all_emails else 0
    status = "✅" if completeness_pct >= 90 else "⚠️ "
    print(f"  {status} Field completeness: {completeness_pct:.1f}%")

    # Write output
    print()
    output_path = Path("tests/golden_set/golden_dataset.csv")
    write_unified_dataset(all_emails, output_path)

    # Write metadata
    metadata_path = Path("tests/golden_set/golden_dataset_metadata.json")
    with open(metadata_path, "w") as f:
        json.dump(analysis, f, indent=2)
    print(f"✅ Wrote metadata to {metadata_path}")

    print("\n✅ Unified golden dataset created!")
    print("\n📝 Files created:")
    print(f"   - {output_path}")
    print(f"   - {metadata_path}")
    print("\n🎯 Ready for Phase 0 validation!")


if __name__ == "__main__":
    main()
