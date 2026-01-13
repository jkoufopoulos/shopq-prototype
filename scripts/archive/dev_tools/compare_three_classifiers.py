#!/usr/bin/env python3
"""
Compare three classifiers: Rule-based vs Claude vs ChatGPT

Merges results from rule-based classification, Claude Sonnet 4.5, and GPT-4o
to create a comprehensive 3-way comparison.

Usage:
    python scripts/compare_three_classifiers.py \
        --sample ~/Desktop/GDS_MULTI_MODEL_SAMPLE.csv \
        --claude ~/Desktop/claude_labels.csv \
        --chatgpt ~/Desktop/chatgpt_labels.csv \
        --output ~/Desktop/GDS_FINAL/2_multi_model_sample.csv \
        --analysis ~/Desktop/GDS_FINAL/3_disagreements_summary.txt
"""

import csv
from collections import defaultdict
from pathlib import Path


def load_csv_by_id(path: Path, id_field: str = "sample_id") -> dict:
    """Load CSV and index by ID field"""
    data = {}
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            data[row[id_field]] = row
    return data


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Compare three classifiers")
    parser.add_argument("--sample", required=True, help="Original sample with rule-based labels")
    parser.add_argument("--claude", required=True, help="Claude classification results")
    parser.add_argument("--chatgpt", required=True, help="ChatGPT classification results")
    parser.add_argument("--output", required=True, help="Output comparison CSV")
    parser.add_argument("--analysis", required=True, help="Output analysis text file")
    args = parser.parse_args()

    sample_path = Path(args.sample).expanduser()
    claude_path = Path(args.claude).expanduser()
    chatgpt_path = Path(args.chatgpt).expanduser()
    output_path = Path(args.output).expanduser()
    analysis_path = Path(args.analysis).expanduser()

    print("📖 Loading data...")
    sample_data = load_csv_by_id(sample_path)
    claude_data = load_csv_by_id(claude_path)
    chatgpt_data = load_csv_by_id(chatgpt_path)

    print(f"   Sample: {len(sample_data)} emails")
    print(f"   Claude: {len(claude_data)} results")
    print(f"   ChatGPT: {len(chatgpt_data)} results")

    # Merge results
    results = []
    all_3_type_agree = 0
    all_3_importance_agree = 0
    llm_type_agree = 0
    llm_importance_agree = 0

    disagreements_by_pattern = defaultdict(list)

    for sample_id in sorted(sample_data.keys()):
        sample = sample_data[sample_id]
        claude = claude_data.get(sample_id, {})
        chatgpt = chatgpt_data.get(sample_id, {})

        rule_type = sample.get("rule_based_type", "")
        rule_importance = sample.get("rule_based_importance", "")
        claude_type = claude.get("claude_type", "")
        claude_importance = claude.get("claude_importance", "")
        chatgpt_type = chatgpt.get("chatgpt_type", "")
        chatgpt_importance = chatgpt.get("chatgpt_importance", "")

        # Agreement checks
        all_type_match = rule_type == claude_type == chatgpt_type
        all_importance_match = rule_importance == claude_importance == chatgpt_importance
        llm_type_match = claude_type == chatgpt_type
        llm_importance_match = claude_importance == chatgpt_importance

        if all_type_match:
            all_3_type_agree += 1
        if all_importance_match:
            all_3_importance_agree += 1
        if llm_type_match:
            llm_type_agree += 1
        if llm_importance_match:
            llm_importance_agree += 1

        # Track disagreement patterns
        if not all_type_match:
            pattern = f"{rule_type}|{claude_type}|{chatgpt_type}"
            disagreements_by_pattern[pattern].append(
                {
                    "id": sample_id,
                    "subject": sample.get("subject", "")[:50],
                    "from": sample.get("from_email", "")[:30],
                }
            )

        results.append(
            {
                "id": sample_id,
                "from": sample.get("from_email", "")[:40],
                "subject": sample.get("subject", "")[:40],
                "rule_type": rule_type,
                "rule_importance": rule_importance,
                "claude_type": claude_type,
                "claude_importance": claude_importance,
                "chatgpt_type": chatgpt_type,
                "chatgpt_importance": chatgpt_importance,
                "agree_all_type": "✓" if all_type_match else "✗",
                "agree_all_importance": "✓" if all_importance_match else "✗",
                "agree_llm_type": "✓" if llm_type_match else "✗",
                "agree_llm_importance": "✓" if llm_importance_match else "✗",
            }
        )

    # Write comparison CSV
    print(f"\n💾 Writing comparison to {output_path}...")
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        fieldnames = list(results[0].keys())
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    # Generate analysis
    total = len(results)
    print("\n📊 Generating analysis...")

    analysis = []
    analysis.append("3-WAY CLASSIFIER COMPARISON")
    analysis.append("=" * 60)
    analysis.append(f"\nTotal sample: {total} emails\n")

    analysis.append("AGREEMENT RATES")
    analysis.append("-" * 60)
    analysis.append(
        f"All 3 agree on TYPE:       {all_3_type_agree}/{total} ({all_3_type_agree / total * 100:.1f}%)"
    )
    analysis.append(
        f"All 3 agree on IMPORTANCE: {all_3_importance_agree}/{total} ({all_3_importance_agree / total * 100:.1f}%)"
    )
    analysis.append("")
    analysis.append(
        f"LLMs agree on TYPE:        {llm_type_agree}/{total} ({llm_type_agree / total * 100:.1f}%)"
    )
    analysis.append(
        f"LLMs agree on IMPORTANCE:  {llm_importance_agree}/{total} ({llm_importance_agree / total * 100:.1f}%)"
    )

    analysis.append("\n\nTOP TYPE DISAGREEMENT PATTERNS")
    analysis.append("-" * 60)
    analysis.append("Format: Rule | Claude | ChatGPT\n")

    sorted_patterns = sorted(disagreements_by_pattern.items(), key=lambda x: -len(x[1]))
    for pattern, examples in sorted_patterns[:10]:
        analysis.append(f"{pattern} ({len(examples)} emails)")
        for ex in examples[:3]:
            analysis.append(f"   {ex['id']}: {ex['subject']}")
        if len(examples) > 3:
            analysis.append(f"   ... and {len(examples) - 3} more")
        analysis.append("")

    # Key insights
    analysis.append("\nKEY INSIGHTS")
    analysis.append("-" * 60)

    if llm_type_agree / total > 0.7:
        analysis.append(
            f"✓ LLMs agree {llm_type_agree / total * 100:.1f}% on type - they have consistent understanding"
        )
    else:
        analysis.append(
            f"✗ LLMs only agree {llm_type_agree / total * 100:.1f}% on type - task may be ambiguous"
        )

    if all_3_type_agree / total < 0.5:
        analysis.append(
            f"✗ Only {all_3_type_agree / total * 100:.1f}% 3-way agreement - rules need significant tuning"
        )
    else:
        analysis.append(
            f"✓ {all_3_type_agree / total * 100:.1f}% 3-way agreement - rules are reasonably aligned"
        )

    # Write analysis
    print(f"💾 Writing analysis to {analysis_path}...")
    with open(analysis_path, "w", encoding="utf-8") as f:
        f.write("\n".join(analysis))

    print("\n✅ Comparison complete!")
    print(f"   Comparison CSV: {output_path}")
    print(f"   Analysis: {analysis_path}")
    print("\n📊 Quick stats:")
    print(
        f"   3-way type agreement: {all_3_type_agree}/{total} ({all_3_type_agree / total * 100:.1f}%)"
    )
    print(f"   LLM type agreement: {llm_type_agree}/{total} ({llm_type_agree / total * 100:.1f}%)")


if __name__ == "__main__":
    main()
