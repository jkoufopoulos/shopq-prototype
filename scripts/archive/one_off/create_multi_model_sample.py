#!/usr/bin/env python3
"""
Create stratified random sample for multi-model comparison

Selects 75 emails from GDS-2.0 with:
- Proportional representation of each email type
- Mix of confidence levels
- Some hand-labeled emails as checkpoints

Usage:
    python scripts/create_multi_model_sample.py \
        --input ~/Desktop/GDS_LABELING_REPORT/gds-2.0-labeled.csv \
        --output ~/Desktop/GDS_MULTI_MODEL_SAMPLE.csv \
        --size 75
"""

import csv
import random
import sys
from collections import defaultdict
from pathlib import Path


def create_stratified_sample(input_path: Path, output_path: Path, sample_size: int = 75):
    """Create stratified random sample"""

    print(f"📖 Reading {input_path}...")

    with open(input_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        all_emails = list(reader)

    print(f"   Total emails: {len(all_emails)}")

    # Group by email type
    by_type = defaultdict(list)
    for email in all_emails:
        email_type = email.get("email_type", "unknown")
        by_type[email_type].append(email)

    print("\n📊 Distribution by type:")
    for email_type, emails in sorted(by_type.items(), key=lambda x: -len(x[1])):
        print(f"   {email_type:15} {len(emails):3} ({len(emails) / len(all_emails) * 100:.1f}%)")

    # Calculate proportional sample sizes
    sample_sizes = {}
    for email_type, emails in by_type.items():
        proportion = len(emails) / len(all_emails)
        target_count = max(1, int(sample_size * proportion))  # At least 1 per type
        sample_sizes[email_type] = min(target_count, len(emails))

    # Adjust to hit exact target
    total_sampled = sum(sample_sizes.values())
    if total_sampled < sample_size:
        # Add extras to largest categories
        diff = sample_size - total_sampled
        largest_types = sorted(by_type.keys(), key=lambda t: len(by_type[t]), reverse=True)
        for email_type in largest_types:
            if diff == 0:
                break
            if sample_sizes[email_type] < len(by_type[email_type]):
                sample_sizes[email_type] += 1
                diff -= 1

    print(f"\n🎯 Sampling plan (total={sum(sample_sizes.values())}):")
    for email_type, count in sorted(sample_sizes.items(), key=lambda x: -x[1]):
        print(f"   {email_type:15} {count:2}")

    # Sample from each type
    random.seed(42)  # Reproducible
    sample = []

    for email_type, target_count in sample_sizes.items():
        emails_of_type = by_type[email_type]

        # Prioritize including some hand-labeled emails as checkpoints
        hand_labeled = [
            e for e in emails_of_type if e.get("decider") in ["manual", "manual_p0_pattern"]
        ]
        ai_labeled = [e for e in emails_of_type if e.get("decider") == "ai_labeler"]

        # Sample: try to get 20% hand-labeled if available
        hand_count = min(len(hand_labeled), max(1, target_count // 5))
        ai_count = target_count - hand_count

        sampled_hand = random.sample(hand_labeled, hand_count) if hand_labeled else []
        sampled_ai = random.sample(ai_labeled, min(ai_count, len(ai_labeled))) if ai_labeled else []

        # If we need more, sample from remainder
        sampled = sampled_hand + sampled_ai
        if len(sampled) < target_count:
            remainder = [e for e in emails_of_type if e not in sampled]
            sampled.extend(
                random.sample(remainder, min(target_count - len(sampled), len(remainder)))
            )

        sample.extend(sampled)

    # Shuffle final sample
    random.shuffle(sample)

    print(f"\n💾 Writing sample to {output_path}...")

    # Write sample CSV with simplified columns for LLM classification
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        fieldnames = [
            "sample_id",
            "message_id",
            "from_email",
            "subject",
            "snippet",
            "rule_based_type",
            "rule_based_importance",
            "rule_based_confidence",
            "rule_based_reasoning",
            "ground_truth_type",
            "ground_truth_importance",
            "ground_truth_source",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for i, email in enumerate(sample, 1):
            writer.writerow(
                {
                    "sample_id": f"S{i:03d}",
                    "message_id": email["message_id"],
                    "from_email": email["from_email"],
                    "subject": email["subject"],
                    "snippet": email["snippet"][:200],  # Truncate long snippets
                    "rule_based_type": email.get("email_type", ""),
                    "rule_based_importance": email.get("importance", ""),
                    "rule_based_confidence": "",  # Will fill from confidence_breakdown if needed
                    "rule_based_reasoning": email.get("importance_reason", ""),
                    "ground_truth_type": email.get("email_type", "")
                    if email.get("decider") in ["manual", "manual_p0_pattern"]
                    else "",
                    "ground_truth_importance": email.get("importance", "")
                    if email.get("decider") in ["manual", "manual_p0_pattern"]
                    else "",
                    "ground_truth_source": email.get("decider", ""),
                }
            )

    print(f"\n✅ Sample created: {len(sample)} emails")

    # Stats
    hand_count = sum(1 for e in sample if e.get("decider") in ["manual", "manual_p0_pattern"])
    ai_count = sum(1 for e in sample if e.get("decider") == "ai_labeler")

    print("\n📋 Sample composition:")
    print(f"   Hand-labeled (ground truth): {hand_count} ({hand_count / len(sample) * 100:.1f}%)")
    print(f"   AI-labeled (to validate): {ai_count} ({ai_count / len(sample) * 100:.1f}%)")
    print(f"   Other: {len(sample) - hand_count - ai_count}")

    return output_path


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Create stratified sample for multi-model comparison"
    )
    parser.add_argument("--input", required=True, help="Input GDS-2.0 labeled CSV")
    parser.add_argument("--output", required=True, help="Output sample CSV")
    parser.add_argument("--size", type=int, default=75, help="Sample size (default: 75)")
    args = parser.parse_args()

    input_path = Path(args.input).expanduser()
    output_path = Path(args.output).expanduser()

    if not input_path.exists():
        print(f"❌ Input file not found: {input_path}")
        sys.exit(1)

    create_stratified_sample(input_path, output_path, args.size)


if __name__ == "__main__":
    main()
