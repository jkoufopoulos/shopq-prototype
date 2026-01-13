# ruff: noqa
#!/usr/bin/env python3
"""
Analyze GDS misclassifications to understand LLM slippage and design few-shot examples.

This script:
1. Runs the classifier on all GDS emails
2. Identifies misclassifications (predicted vs ground truth)
3. Categorizes errors (false positives, false negatives)
4. Suggests few-shot examples for LLM prompt
"""

import sys
from pathlib import Path

import pandas as pd

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shopq.classification.importance_mapping.guardrails import GuardrailMatcher
from shopq.classification.importance_mapping.mapper import BridgeImportanceMapper
from shopq.classification.pipeline_wrapper import RefactoredPipelineClassifier


def main():
    # Load GDS
    gds_path = Path(__file__).parent.parent / "tests" / "golden_set" / "gds-1.0.csv"
    if not gds_path.exists():
        print(f"❌ GDS not found at {gds_path}")
        sys.exit(1)

    gds = pd.read_csv(gds_path)
    print(f"\n✅ Loaded {len(gds)} emails from gds-1.0.csv")

    # Initialize classifier (same as test)
    classifier = RefactoredPipelineClassifier()
    guardrails = GuardrailMatcher()
    mapper = BridgeImportanceMapper(guardrail_matcher=guardrails)

    # Classify all emails
    results = []
    errors = 0

    print(f"\n🔄 Classifying {len(gds)} emails...")
    for idx, email in gds.iterrows():
        try:
            result = classifier.classify(
                subject=email["subject"], snippet=email["snippet"], from_field=email["from_email"]
            )
            result["subject"] = email["subject"]
            result["snippet"] = email["snippet"]

            # Map importance
            decision = mapper.map_email(result)

            results.append(
                {
                    "message_id": email["message_id"],
                    "subject": email["subject"],
                    "snippet": email["snippet"][:100],
                    "from_email": email["from_email"],
                    "predicted_importance": decision.importance or "routine",
                    "ground_truth_importance": email["importance"],
                    "predicted_type": result.get("type", "other"),
                    "ground_truth_type": email["email_type"],
                    "attention": result.get("attention", "none"),
                    "domains": ",".join(result.get("domains", [])),
                    "decider": decision.source,
                    "rule_name": decision.rule_name,
                    "guardrail": decision.guardrail,
                }
            )

        except Exception as e:
            errors += 1
            results.append(
                {
                    "message_id": email["message_id"],
                    "subject": email["subject"],
                    "snippet": email["snippet"][:100],
                    "from_email": email["from_email"],
                    "predicted_importance": "routine",
                    "ground_truth_importance": email["importance"],
                    "predicted_type": "other",
                    "ground_truth_type": email["email_type"],
                    "attention": "none",
                    "domains": "",
                    "decider": "error",
                    "error": str(e),
                }
            )

    df = pd.DataFrame(results)
    print(f"✅ Classified {len(df)} emails ({errors} errors)")

    # === ANALYSIS ===

    print("\n" + "=" * 80)
    print("CONFUSION MATRIX - IMPORTANCE")
    print("=" * 80)

    confusion = pd.crosstab(df["ground_truth_importance"], df["predicted_importance"], margins=True)
    print(confusion)

    # === CRITICAL FALSE NEGATIVES ===
    print("\n" + "=" * 80)
    print("CRITICAL FALSE NEGATIVES (missed critical emails)")
    print("=" * 80)

    critical_fn = df[
        (df["ground_truth_importance"] == "critical") & (df["predicted_importance"] != "critical")
    ]

    print(
        f"\nTotal: {len(critical_fn)} / {len(df[df['ground_truth_importance'] == 'critical'])} critical emails missed"
    )
    print(
        f"Impact: {len(critical_fn) / len(df[df['ground_truth_importance'] == 'critical']) * 100:.1f}% false negative rate\n"
    )

    if len(critical_fn) > 0:
        print("Subject | Predicted | Attention | Domains | Decider")
        print("-" * 120)
        for _, row in critical_fn.iterrows():
            subject_short = row["subject"][:60]
            print(
                f"{subject_short:<60} | {row['predicted_importance']:<13} | {row['attention']:<13} | {row['domains']:<15} | {row['decider']}/{row.get('rule_name', 'N/A')}"
            )

    # === CRITICAL FALSE POSITIVES ===
    print("\n" + "=" * 80)
    print("CRITICAL FALSE POSITIVES (wrongly marked critical)")
    print("=" * 80)

    critical_fp = df[
        (df["ground_truth_importance"] != "critical") & (df["predicted_importance"] == "critical")
    ]

    print(f"\nTotal: {len(critical_fp)} false positives")
    print(
        f"Precision: {len(df[(df['ground_truth_importance'] == 'critical') & (df['predicted_importance'] == 'critical')]) / max(len(df[df['predicted_importance'] == 'critical']), 1) * 100:.1f}%\n"
    )

    if len(critical_fp) > 0:
        print("Subject | Ground Truth | Attention | Domains | Decider")
        print("-" * 120)
        for _, row in critical_fp.head(10).iterrows():
            subject_short = row["subject"][:60]
            print(
                f"{subject_short:<60} | {row['ground_truth_importance']:<13} | {row['attention']:<13} | {row['domains']:<15} | {row['decider']}/{row.get('rule_name', 'N/A')}"
            )

    # === TIME_SENSITIVE FALSE NEGATIVES ===
    print("\n" + "=" * 80)
    print("TIME_SENSITIVE FALSE NEGATIVES (missed time-sensitive emails)")
    print("=" * 80)

    ts_fn = df[
        (df["ground_truth_importance"] == "time_sensitive")
        & (df["predicted_importance"] != "time_sensitive")
    ]

    print(
        f"\nTotal: {len(ts_fn)} / {len(df[df['ground_truth_importance'] == 'time_sensitive'])} time-sensitive emails missed\n"
    )

    if len(ts_fn) > 0:
        print("Subject | Predicted | Attention | Domains | Decider")
        print("-" * 120)
        for _, row in ts_fn.head(10).iterrows():
            subject_short = row["subject"][:60]
            print(
                f"{subject_short:<60} | {row['predicted_importance']:<13} | {row['attention']:<13} | {row['domains']:<15} | {row['decider']}/{row.get('rule_name', 'N/A')}"
            )

    # === ROUTINE FALSE POSITIVES ===
    print("\n" + "=" * 80)
    print("ROUTINE FALSE POSITIVES (should be routine but elevated)")
    print("=" * 80)

    routine_fp = df[
        (df["ground_truth_importance"] == "routine") & (df["predicted_importance"] != "routine")
    ]

    print(f"\nTotal: {len(routine_fp)} routine emails incorrectly elevated\n")

    if len(routine_fp) > 0:
        print("Subject | Predicted | Attention | Domains | Decider")
        print("-" * 120)
        for _, row in routine_fp.head(10).iterrows():
            subject_short = row["subject"][:60]
            print(
                f"{subject_short:<60} | {row['predicted_importance']:<13} | {row['attention']:<13} | {row['domains']:<15} | {row['decider']}/{row.get('rule_name', 'N/A')}"
            )

    # === DECIDER BREAKDOWN ===
    print("\n" + "=" * 80)
    print("DECIDER BREAKDOWN (where importance comes from)")
    print("=" * 80)

    decider_counts = df["decider"].value_counts()
    print("\nDecider | Count | Percentage")
    print("-" * 50)
    for decider, count in decider_counts.items():
        print(f"{decider:<15} | {count:>5} | {count / len(df) * 100:>5.1f}%")

    # === FEW-SHOT RECOMMENDATIONS ===
    print("\n" + "=" * 80)
    print("FEW-SHOT EXAMPLE RECOMMENDATIONS")
    print("=" * 80)

    print("\n📝 Suggested few-shot examples for LLM prompt:\n")

    # Critical examples (from false negatives)
    print("=== CRITICAL EXAMPLES ===")
    for _, row in critical_fn.head(5).iterrows():
        print(f'- Subject: "{row["subject"][:80]}"')
        print("  → importance: critical")
        print("  → reason: [TODO: analyze why this should be critical]")
        print()

    # Routine examples (from false positives to critical)
    print("\n=== ROUTINE EXAMPLES (to prevent false escalation) ===")
    for _, row in critical_fp.head(5).iterrows():
        print(f'- Subject: "{row["subject"][:80]}"')
        print("  → importance: routine (NOT critical)")
        print("  → reason: [TODO: analyze why this should be routine]")
        print()

    # === EXPORT DETAILED REPORT ===
    output_path = Path(__file__).parent.parent / "reports" / "gds_misclassification_analysis.csv"
    output_path.parent.mkdir(exist_ok=True)
    df.to_csv(output_path, index=False)
    print(f"\n✅ Detailed report saved to: {output_path}")

    print("\n" + "=" * 80)
    print("ANALYSIS COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
