#!/usr/bin/env python3
"""
Generate comprehensive GDS-2.0 labeling report

Creates a report folder with:
1. gds-2.0-labeled.csv - All 500 emails with AI labels
2. needs_manual_review.csv - Emails that need manual verification
3. labeling_summary.md - Statistics and analysis
4. confidence_breakdown.csv - Confidence levels per email

Usage:
    python scripts/generate_labeling_report.py \
        --labeled ~/Desktop/gds2_AI_LABELED.csv \
        --gds tests/golden_set/gds-2.0.csv \
        --output ~/Desktop/GDS_LABELING_REPORT
"""

import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path


def generate_report(labeled_path: Path, gds_path: Path, output_dir: Path):
    """Generate comprehensive labeling report"""

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"📂 Creating report in: {output_dir}\n")

    # Read AI labels
    print("📖 Reading AI-labeled data...")
    labels_by_message_id = {}
    with open(labeled_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            labels_by_message_id[row["message_id"]] = row

    # Read GDS-2.0
    print("📖 Reading GDS-2.0 dataset...")
    with open(gds_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        gds_rows = list(reader)
        fieldnames = reader.fieldnames

    # Apply labels and collect stats
    print("🏷️  Applying labels...\n")

    needs_review = []
    confidence_breakdown = []
    type_counts = Counter()
    importance_counts = Counter()
    confidence_counts = Counter()
    decider_counts = Counter()

    type_by_confidence = defaultdict(lambda: defaultdict(int))

    for row in gds_rows:
        message_id = row["message_id"]

        if message_id in labels_by_message_id:
            label = labels_by_message_id[message_id]

            # Skip hand-labeled data
            if row["decider"] == "manual":
                decider_counts["manual"] += 1
                type_counts[row["email_type"]] += 1
                importance_counts[row["importance"]] += 1
                continue

            # Apply AI labels
            row["email_type"] = label["YOUR_type"]
            row["importance"] = label["YOUR_importance"]
            row["decider"] = "ai_labeler"
            row["importance_reason"] = label["AI_reasoning"]

            confidence = label["AI_confidence"]
            email_type = label["YOUR_type"]

            # Track stats
            type_counts[email_type] += 1
            importance_counts[row["importance"]] += 1
            confidence_counts[confidence] += 1
            decider_counts["ai_labeler"] += 1
            type_by_confidence[email_type][confidence] += 1

            # Collect confidence info
            confidence_breakdown.append(
                {
                    "message_id": message_id,
                    "from": row["from_email"],
                    "subject": row["subject"],
                    "email_type": email_type,
                    "importance": row["importance"],
                    "confidence": confidence,
                    "reasoning": label["AI_reasoning"],
                }
            )

            # Flag medium/low confidence for review
            if confidence in ["medium", "low"]:
                needs_review.append(
                    {
                        "message_id": message_id,
                        "from": row["from_email"],
                        "subject": row["subject"],
                        "snippet": row["snippet"][:100],
                        "suggested_type": email_type,
                        "suggested_importance": row["importance"],
                        "confidence": confidence,
                        "reasoning": label["AI_reasoning"],
                    }
                )
        else:
            # Existing label
            decider_counts[row.get("decider", "unknown")] += 1
            type_counts[row.get("email_type", "unknown")] += 1
            importance_counts[row.get("importance", "unknown")] += 1

    # Write outputs
    print("💾 Writing report files...\n")

    # 1. Full labeled dataset
    labeled_csv = output_dir / "gds-2.0-labeled.csv"
    with open(labeled_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(gds_rows)
    print(f"   ✅ {labeled_csv.name} - All 500 emails with labels")

    # 2. Needs manual review
    if needs_review:
        review_csv = output_dir / "needs_manual_review.csv"
        with open(review_csv, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(needs_review[0].keys()))
            writer.writeheader()
            writer.writerows(needs_review)
        print(f"   ⚠️  {review_csv.name} - {len(needs_review)} emails for manual review")
    else:
        print("   ✅ No emails need manual review (all high confidence)")

    # 3. Confidence breakdown
    confidence_csv = output_dir / "confidence_breakdown.csv"
    with open(confidence_csv, "w", encoding="utf-8", newline="") as f:
        if confidence_breakdown:
            writer = csv.DictWriter(f, fieldnames=list(confidence_breakdown[0].keys()))
            writer.writeheader()
            writer.writerows(confidence_breakdown)
    print(f"   📊 {confidence_csv.name} - Detailed confidence analysis")

    # 4. Summary markdown
    summary_md = output_dir / "labeling_summary.md"
    with open(summary_md, "w", encoding="utf-8") as f:
        f.write("# GDS-2.0 AI Labeling Summary\n\n")
        f.write(f"**Generated:** {Path.cwd()}\n")
        f.write(f"**Total Emails:** {len(gds_rows)}\n\n")

        f.write("---\n\n")
        f.write("## Email Type Distribution\n\n")
        f.write("| Type | Count | Percentage |\n")
        f.write("|------|-------|------------|\n")
        for email_type, count in type_counts.most_common():
            pct = count / len(gds_rows) * 100
            f.write(f"| **{email_type}** | {count} | {pct:.1f}% |\n")

        f.write("\n---\n\n")
        f.write("## Importance Distribution\n\n")
        f.write("| Importance | Count | Percentage |\n")
        f.write("|------------|-------|------------|\n")
        for importance, count in importance_counts.most_common():
            pct = count / len(gds_rows) * 100
            f.write(f"| **{importance}** | {count} | {pct:.1f}% |\n")

        f.write("\n---\n\n")
        f.write("## Label Sources\n\n")
        f.write("| Source | Count | Percentage | Description |\n")
        f.write("|--------|-------|------------|-------------|\n")
        for decider, count in decider_counts.most_common():
            pct = count / len(gds_rows) * 100
            desc = {
                "ai_labeler": "AI-labeled using deterministic rules",
                "manual": "Hand-labeled by user",
                "manual_p0_pattern": "Pattern-based manual labels",
                "diversity_fetch": "Legacy classifier output",
            }.get(decider, "Unknown source")
            f.write(f"| {decider} | {count} | {pct:.1f}% | {desc} |\n")

        f.write("\n---\n\n")
        f.write("## Confidence Levels\n\n")
        f.write("| Confidence | Count | Percentage |\n")
        f.write("|------------|-------|------------|\n")
        for confidence, count in sorted(
            confidence_counts.items(), key=lambda x: {"high": 0, "medium": 1, "low": 2}.get(x[0], 3)
        ):
            pct = count / sum(confidence_counts.values()) * 100
            f.write(f"| **{confidence}** | {count} | {pct:.1f}% |\n")

        f.write("\n---\n\n")
        f.write("## Confidence by Email Type\n\n")
        f.write("Shows how confident the AI is for each email type:\n\n")
        f.write("| Type | High | Medium | Low |\n")
        f.write("|------|------|--------|-----|\n")
        for email_type in sorted(type_by_confidence.keys()):
            high = type_by_confidence[email_type]["high"]
            medium = type_by_confidence[email_type]["medium"]
            low = type_by_confidence[email_type]["low"]
            total = high + medium + low
            f.write(
                f"| {email_type} | {high}/{total} ({high / total * 100:.0f}%) | {medium}/{total} ({medium / total * 100:.0f}%) | {low}/{total} ({low / total * 100:.0f}%) |\n"
            )

        f.write("\n---\n\n")
        f.write("## Files in This Report\n\n")
        f.write("1. **gds-2.0-labeled.csv** - Complete labeled dataset (500 emails)\n")
        f.write("2. **needs_manual_review.csv** - Medium/low confidence emails for human review\n")
        f.write("3. **confidence_breakdown.csv** - Detailed confidence analysis per email\n")
        f.write("4. **labeling_summary.md** - This summary document\n\n")

        f.write("---\n\n")
        f.write("## Next Steps\n\n")
        if needs_review:
            f.write(
                f"1. **Review {len(needs_review)} medium-confidence emails** in `needs_manual_review.csv`\n"
            )
            f.write("2. Correct any incorrect labels in `gds-2.0-labeled.csv`\n")
            f.write("3. Change `decider` to `manual` for any corrected labels\n")
        else:
            f.write("1. All labels are high confidence - spot check a sample\n")
        f.write("4. Run quality tests: `pytest tests/test_importance_baseline.py -v`\n")
        f.write("5. Measure classifier accuracy against this ground truth\n")

    print(f"   📄 {summary_md.name} - Summary and statistics\n")

    # Print summary to console
    print("=" * 60)
    print("📊 LABELING SUMMARY")
    print("=" * 60)
    print(f"\n✅ Total emails labeled: {len(gds_rows)}")
    print(f"   • AI-labeled: {decider_counts.get('ai_labeler', 0)}")
    print(
        f"   • Hand-labeled: {decider_counts.get('manual', 0) + decider_counts.get('manual_p0_pattern', 0)}"
    )

    print("\n📧 Email Types:")
    for email_type, count in type_counts.most_common():
        pct = count / len(gds_rows) * 100
        print(f"   • {email_type:15} {count:3} ({pct:5.1f}%)")

    print("\n⚡ Importance:")
    for importance, count in importance_counts.most_common():
        pct = count / len(gds_rows) * 100
        print(f"   • {importance:15} {count:3} ({pct:5.1f}%)")

    print("\n🎯 Confidence:")
    for confidence, count in sorted(
        confidence_counts.items(), key=lambda x: {"high": 0, "medium": 1, "low": 2}.get(x[0], 3)
    ):
        pct = count / sum(confidence_counts.values()) * 100
        print(f"   • {confidence:15} {count:3} ({pct:5.1f}%)")

    if needs_review:
        print(f"\n⚠️  Manual review needed: {len(needs_review)} emails")
        print(f"   → See: {output_dir / 'needs_manual_review.csv'}")
    else:
        print("\n✅ No manual review needed - all high confidence!")

    print(f"\n📂 Report saved to: {output_dir}/")
    print("=" * 60)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Generate GDS-2.0 labeling report")
    parser.add_argument("--labeled", required=True, help="AI-labeled CSV")
    parser.add_argument("--gds", required=True, help="Original GDS-2.0 CSV")
    parser.add_argument("--output", required=True, help="Output directory for report")
    args = parser.parse_args()

    labeled_path = Path(args.labeled).expanduser()
    gds_path = Path(args.gds).expanduser()
    output_dir = Path(args.output).expanduser()

    if not labeled_path.exists():
        print(f"❌ Labeled file not found: {labeled_path}")
        sys.exit(1)

    if not gds_path.exists():
        print(f"❌ GDS file not found: {gds_path}")
        sys.exit(1)

    generate_report(labeled_path, gds_path, output_dir)


if __name__ == "__main__":
    main()
