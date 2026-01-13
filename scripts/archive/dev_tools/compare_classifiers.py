#!/usr/bin/env python3
"""
Compare three email classifiers: rule-based, Claude, and ChatGPT

Generates:
1. Disagreement report - where models differ
2. Prioritized review list - sorted by disagreement severity
3. Agreement statistics - inter-model agreement rates

Usage:
    python scripts/compare_classifiers.py \
        --sample ~/Desktop/GDS_MULTI_MODEL_SAMPLE.csv \
        --claude ~/Desktop/claude_labels.csv \
        --chatgpt ~/Desktop/chatgpt_labels.csv \
        --output ~/Desktop/GDS_MULTI_MODEL_COMPARISON
"""

import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path


def load_csv_as_dict(path: Path, key_field: str) -> dict:
    """Load CSV and index by key field"""
    result = {}
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            result[row[key_field]] = row
    return result


def calculate_agreement(row: dict) -> dict:
    """Calculate agreement between 3 classifiers"""

    rule_type = row.get("rule_based_type", "")
    claude_type = row.get("claude_type", "")
    chatgpt_type = row.get("chatgpt_type", "")

    rule_imp = row.get("rule_based_importance", "")
    claude_imp = row.get("claude_importance", "")
    chatgpt_imp = row.get("chatgpt_importance", "")

    # Count agreements for type
    type_votes = [t for t in [rule_type, claude_type, chatgpt_type] if t]
    type_counts = Counter(type_votes)
    type_majority = type_counts.most_common(1)[0] if type_counts else ("unknown", 0)
    type_agreement_count = type_majority[1]

    # Count agreements for importance
    imp_votes = [i for i in [rule_imp, claude_imp, chatgpt_imp] if i]
    imp_counts = Counter(imp_votes)
    imp_majority = imp_counts.most_common(1)[0] if imp_counts else ("unknown", 0)
    imp_agreement_count = imp_majority[1]

    # Overall agreement score (0 = all disagree, 3 = all agree on both)
    agreement_score = 0
    if type_agreement_count == 3:
        agreement_score += 1.5  # Full type agreement
    elif type_agreement_count == 2:
        agreement_score += 1.0  # Partial type agreement

    if imp_agreement_count == 3:
        agreement_score += 1.5  # Full importance agreement
    elif imp_agreement_count == 2:
        agreement_score += 1.0  # Partial importance agreement

    return {
        "type_agreement": type_agreement_count,
        "importance_agreement": imp_agreement_count,
        "agreement_score": agreement_score,
        "type_majority": type_majority[0],
        "importance_majority": imp_majority[0],
        "has_disagreement": type_agreement_count < 3 or imp_agreement_count < 3,
    }


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Compare email classifiers")
    parser.add_argument("--sample", required=True, help="Sample CSV with rule-based labels")
    parser.add_argument("--claude", required=True, help="Claude labels CSV")
    parser.add_argument("--chatgpt", required=True, help="ChatGPT labels CSV")
    parser.add_argument("--output", required=True, help="Output directory")
    args = parser.parse_args()

    sample_path = Path(args.sample).expanduser()
    claude_path = Path(args.claude).expanduser()
    chatgpt_path = Path(args.chatgpt).expanduser()
    output_dir = Path(args.output).expanduser()

    # Validate inputs
    for path in [sample_path, claude_path, chatgpt_path]:
        if not path.exists():
            print(f"❌ File not found: {path}")
            sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    print("📖 Loading classification data...\n")

    # Load all data
    sample_data = load_csv_as_dict(sample_path, "sample_id")
    claude_data = load_csv_as_dict(claude_path, "sample_id")
    chatgpt_data = load_csv_as_dict(chatgpt_path, "sample_id")

    print(f"   Sample emails: {len(sample_data)}")
    print(f"   Claude labels: {len(claude_data)}")
    print(f"   ChatGPT labels: {len(chatgpt_data)}\n")

    # Merge data
    print("🔀 Merging classifications...\n")

    merged = []
    disagreements = []

    for sample_id, sample_row in sample_data.items():
        claude_row = claude_data.get(sample_id, {})
        chatgpt_row = chatgpt_data.get(sample_id, {})

        # Combine all labels
        combined = {
            "sample_id": sample_id,
            "message_id": sample_row["message_id"],
            "from_email": sample_row["from_email"],
            "subject": sample_row["subject"],
            "snippet": sample_row["snippet"],
            "rule_based_type": sample_row.get("rule_based_type", ""),
            "rule_based_importance": sample_row.get("rule_based_importance", ""),
            "rule_based_reasoning": sample_row.get("rule_based_reasoning", ""),
            "claude_type": claude_row.get("claude_type", ""),
            "claude_importance": claude_row.get("claude_importance", ""),
            "claude_reasoning": claude_row.get("claude_reasoning", ""),
            "chatgpt_type": chatgpt_row.get("chatgpt_type", ""),
            "chatgpt_importance": chatgpt_row.get("chatgpt_importance", ""),
            "chatgpt_reasoning": chatgpt_row.get("chatgpt_reasoning", ""),
            "ground_truth_type": sample_row.get("ground_truth_type", ""),
            "ground_truth_importance": sample_row.get("ground_truth_importance", ""),
            "ground_truth_source": sample_row.get("ground_truth_source", ""),
        }

        # Calculate agreement
        agreement = calculate_agreement(combined)
        combined.update(agreement)

        merged.append(combined)

        if agreement["has_disagreement"]:
            disagreements.append(combined)

    # Sort by agreement score (lowest first = most disagreement)
    disagreements.sort(key=lambda x: x["agreement_score"])

    # Write outputs
    print("💾 Writing report files...\n")

    # 1. Disagreement report
    disagreement_csv = output_dir / "disagreement_report.csv"
    with open(disagreement_csv, "w", encoding="utf-8", newline="") as f:
        fieldnames = [
            "sample_id",
            "from_email",
            "subject",
            "rule_based_type",
            "claude_type",
            "chatgpt_type",
            "rule_based_importance",
            "claude_importance",
            "chatgpt_importance",
            "type_agreement",
            "importance_agreement",
            "agreement_score",
            "rule_based_reasoning",
            "claude_reasoning",
            "chatgpt_reasoning",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(disagreements)

    print(f"   ⚠️  {disagreement_csv.name} - {len(disagreements)} disagreements")

    # 2. Prioritized review list
    review_csv = output_dir / "final_review_prioritized.csv"
    with open(review_csv, "w", encoding="utf-8", newline="") as f:
        fieldnames = [
            "priority",
            "sample_id",
            "from_email",
            "subject",
            "snippet",
            "rule_based_type",
            "claude_type",
            "chatgpt_type",
            "ground_truth_type",
            "rule_based_importance",
            "claude_importance",
            "chatgpt_importance",
            "ground_truth_importance",
            "agreement_score",
            "type_majority",
            "importance_majority",
            "rule_based_reasoning",
            "claude_reasoning",
            "chatgpt_reasoning",
        ]

        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()

        for i, row in enumerate(disagreements, 1):
            # Assign priority
            if row["agreement_score"] == 0:
                priority = "🔴 HIGH - All disagree"
            elif row["agreement_score"] <= 1:
                priority = "🟠 MEDIUM - Major disagreement"
            else:
                priority = "🟡 LOW - Minor disagreement"

            row["priority"] = priority
            writer.writerow(row)

    print(f"   📋 {review_csv.name} - Prioritized for review")

    # 3. Agreement statistics
    stats_md = output_dir / "agreement_stats.md"
    with open(stats_md, "w", encoding="utf-8") as f:
        f.write("# Multi-Model Classification Agreement Report\n\n")
        f.write(f"**Total Emails Compared:** {len(merged)}\n\n")

        # Overall agreement
        perfect_agreement = sum(1 for r in merged if r["agreement_score"] == 3.0)
        partial_agreement = sum(1 for r in merged if 0 < r["agreement_score"] < 3.0)
        no_agreement = sum(1 for r in merged if r["agreement_score"] == 0)

        f.write("## Overall Agreement\n\n")
        f.write("| Agreement Level | Count | Percentage |\n")
        f.write("|-----------------|-------|------------|\n")
        f.write(
            f"| **Perfect (all 3 agree)** | {perfect_agreement} | {perfect_agreement / len(merged) * 100:.1f}% |\n"
        )
        f.write(
            f"| **Partial (2 agree)** | {partial_agreement} | {partial_agreement / len(merged) * 100:.1f}% |\n"
        )
        f.write(
            f"| **No agreement** | {no_agreement} | {no_agreement / len(merged) * 100:.1f}% |\n\n"
        )

        # Type agreement
        f.write("## Email Type Agreement\n\n")
        type_3_agree = sum(1 for r in merged if r["type_agreement"] == 3)
        type_2_agree = sum(1 for r in merged if r["type_agreement"] == 2)
        type_no_agree = sum(1 for r in merged if r["type_agreement"] < 2)

        f.write("| Agreement | Count | Percentage |\n")
        f.write("|-----------|-------|------------|\n")
        f.write(f"| All 3 agree | {type_3_agree} | {type_3_agree / len(merged) * 100:.1f}% |\n")
        f.write(f"| 2 agree | {type_2_agree} | {type_2_agree / len(merged) * 100:.1f}% |\n")
        f.write(
            f"| All disagree | {type_no_agree} | {type_no_agree / len(merged) * 100:.1f}% |\n\n"
        )

        # Importance agreement
        f.write("## Importance Agreement\n\n")
        imp_3_agree = sum(1 for r in merged if r["importance_agreement"] == 3)
        imp_2_agree = sum(1 for r in merged if r["importance_agreement"] == 2)
        imp_no_agree = sum(1 for r in merged if r["importance_agreement"] < 2)

        f.write("| Agreement | Count | Percentage |\n")
        f.write("|-----------|-------|------------|\n")
        f.write(f"| All 3 agree | {imp_3_agree} | {imp_3_agree / len(merged) * 100:.1f}% |\n")
        f.write(f"| 2 agree | {imp_2_agree} | {imp_2_agree / len(merged) * 100:.1f}% |\n")
        f.write(f"| All disagree | {imp_no_agree} | {imp_no_agree / len(merged) * 100:.1f}% |\n\n")

        # Confusion analysis
        f.write("## Common Disagreements\n\n")

        disagreement_patterns = defaultdict(int)
        for row in disagreements:
            rule_t = row["rule_based_type"]
            claude_t = row["claude_type"]
            chatgpt_t = row["chatgpt_type"]

            if rule_t != claude_t and rule_t != chatgpt_t:
                pattern = f"Rule: {rule_t}, Claude: {claude_t}, ChatGPT: {chatgpt_t}"
                disagreement_patterns[pattern] += 1

        f.write("Top disagreement patterns:\n\n")
        for pattern, count in sorted(disagreement_patterns.items(), key=lambda x: -x[1])[:10]:
            f.write(f"- {pattern}: {count} emails\n")

    print(f"   📊 {stats_md.name} - Agreement statistics\n")

    # Copy original files to output
    import shutil

    shutil.copy(sample_path, output_dir / "sample_75_emails.csv")
    shutil.copy(claude_path, output_dir / "claude_labels.csv")
    shutil.copy(chatgpt_path, output_dir / "chatgpt_labels.csv")

    # Summary
    print("=" * 60)
    print("📊 COMPARISON SUMMARY")
    print("=" * 60)
    print(f"\n✅ Compared {len(merged)} emails across 3 classifiers\n")
    print("Agreement rates:")
    print(
        f"   • Perfect agreement: {perfect_agreement}/{len(merged)} ({perfect_agreement / len(merged) * 100:.1f}%)"
    )
    print(
        f"   • Type agreement: {type_3_agree}/{len(merged)} ({type_3_agree / len(merged) * 100:.1f}%)"
    )
    print(f"   • Importance agreement: {imp_3_agree}/{len(merged) * 100:.1f}%)")
    print(f"\n⚠️  Disagreements: {len(disagreements)}")
    print(f"   • High priority (all disagree): {no_agreement}")
    print(f"   • Review list: {output_dir / 'final_review_prioritized.csv'}")
    print(f"\n📂 Full report: {output_dir}/")
    print("=" * 60)


if __name__ == "__main__":
    main()
