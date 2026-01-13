#!/usr/bin/env python3
"""
Apply AI-suggested labels from gds2_AI_LABELED.csv back to GDS-2.0

This script:
1. Reads the AI-labeled review CSV
2. Matches by message_id to the GDS-2.0 dataset
3. Updates email_type and importance fields
4. Preserves hand-labeled data (doesn't overwrite manual labels)
5. Writes updated GDS-2.0 CSV

Usage:
    python scripts/apply_ai_labels_to_gds2.py \
        --labeled ~/Desktop/gds2_AI_LABELED.csv \
        --gds tests/golden_set/gds-2.0.csv \
        --output tests/golden_set/gds-2.0-labeled.csv
"""

import csv
import sys
from pathlib import Path


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Apply AI labels to GDS-2.0")
    parser.add_argument("--labeled", required=True, help="AI-labeled CSV file")
    parser.add_argument("--gds", required=True, help="Original GDS-2.0 CSV")
    parser.add_argument("--output", required=True, help="Output GDS-2.0 with labels")
    args = parser.parse_args()

    labeled_path = Path(args.labeled).expanduser()
    gds_path = Path(args.gds).expanduser()
    output_path = Path(args.output).expanduser()

    if not labeled_path.exists():
        print(f"❌ Labeled file not found: {labeled_path}")
        sys.exit(1)

    if not gds_path.exists():
        print(f"❌ GDS file not found: {gds_path}")
        sys.exit(1)

    # Read AI-labeled data
    print(f"📖 Reading AI labels from: {labeled_path}")
    labels_by_message_id = {}
    with open(labeled_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            message_id = row["message_id"]
            labels_by_message_id[message_id] = {
                "email_type": row["YOUR_type"],
                "importance": row["YOUR_importance"],
                "ai_confidence": row["AI_confidence"],
                "ai_reasoning": row["AI_reasoning"],
            }

    print(f"   Loaded {len(labels_by_message_id)} AI labels")

    # Read GDS-2.0
    print(f"📖 Reading GDS-2.0 from: {gds_path}")
    with open(gds_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        gds_rows = list(reader)
        fieldnames = reader.fieldnames

    print(f"   Loaded {len(gds_rows)} emails from GDS-2.0")

    # Apply labels
    updated_count = 0
    skipped_count = 0

    for row in gds_rows:
        message_id = row["message_id"]

        if message_id in labels_by_message_id:
            # Check if already hand-labeled (decider = manual)
            if row["decider"] == "manual":
                skipped_count += 1
                continue

            # Apply AI labels
            label = labels_by_message_id[message_id]
            row["email_type"] = label["email_type"]
            row["importance"] = label["importance"]
            row["decider"] = "ai_labeler"
            row["importance_reason"] = label["ai_reasoning"]
            updated_count += 1

    # Write updated GDS-2.0
    print(f"💾 Writing updated GDS-2.0 to: {output_path}")
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(gds_rows)

    print("\n✅ GDS-2.0 labeling complete!")
    print(f"   Updated: {updated_count} emails")
    print(f"   Skipped (hand-labeled): {skipped_count} emails")
    print(f"   Total: {len(gds_rows)} emails")

    # Statistics
    print("\n📊 Final GDS-2.0 Statistics:")

    type_counts = {}
    importance_counts = {}
    decider_counts = {}

    for row in gds_rows:
        email_type = row.get("email_type", "")
        importance = row.get("importance", "")
        decider = row.get("decider", "")

        if email_type:
            type_counts[email_type] = type_counts.get(email_type, 0) + 1
        if importance:
            importance_counts[importance] = importance_counts.get(importance, 0) + 1
        if decider:
            decider_counts[decider] = decider_counts.get(decider, 0) + 1

    print("\n   Email Types:")
    for email_type, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        pct = count / len(gds_rows) * 100
        print(f"      {email_type:15} {count:3} ({pct:5.1f}%)")

    print("\n   Importance:")
    for importance, count in sorted(importance_counts.items(), key=lambda x: -x[1]):
        pct = count / len(gds_rows) * 100
        print(f"      {importance:15} {count:3} ({pct:5.1f}%)")

    print("\n   Label Source (decider):")
    for decider, count in sorted(decider_counts.items(), key=lambda x: -x[1]):
        pct = count / len(gds_rows) * 100
        print(f"      {decider:20} {count:3} ({pct:5.1f}%)")


if __name__ == "__main__":
    main()
