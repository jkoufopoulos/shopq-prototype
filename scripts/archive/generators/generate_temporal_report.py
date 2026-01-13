#!/usr/bin/env python3
"""
Generate comprehensive Markdown report for temporal decay evaluation.

Includes:
- Accuracy metrics by timepoint
- Confusion matrices with heatmaps
- Section transition analysis (T0 → T1 → T2)
- Pass/fail criteria against thresholds
- Edge case validation
"""

import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))


def load_results():
    """Load evaluation results CSV."""
    results_path = Path(__file__).parent.parent / "reports" / "temporal_evaluation_results.csv"

    if not results_path.exists():
        print(f"❌ Results not found: {results_path}")
        print("Run: python3 scripts/evaluate_temporal_decay.py")
        return None

    return pd.read_csv(results_path)


def generate_confusion_matrix_table(df, timepoint):
    """Generate markdown confusion matrix table."""
    sections = ["critical", "today", "coming_up", "worth_knowing", "everything_else", "skip"]

    # Build confusion matrix
    matrix = {}
    for user_sec in sections:
        for sys_sec in sections:
            count = len(df[(df["user_section"] == user_sec) & (df["system_section"] == sys_sec)])
            matrix[(user_sec, sys_sec)] = count

    # Generate markdown table
    lines = []
    lines.append(f"\n### Confusion Matrix - {timepoint.upper()}\n")
    lines.append("| User \\ System | " + " | ".join([s[:8] for s in sections]) + " |")
    lines.append("|" + "---|" * (len(sections) + 1))

    for user_sec in sections:
        row = [user_sec[:15].ljust(15)]
        for sys_sec in sections:
            count = matrix[(user_sec, sys_sec)]
            if count > 0:
                marker = "✅" if user_sec == sys_sec else "❌"
                cell = f"{marker}{count}"
            else:
                cell = "-"
            row.append(cell)
        lines.append("| " + " | ".join(row) + " |")

    return "\n".join(lines)


def analyze_transitions(df):
    """Analyze how emails transition between sections across timepoints."""
    transitions = []

    # Group by email_id
    email_groups = df.groupby("email_id")

    for email_id, group in email_groups:
        t0_row = group[group["timepoint"] == "t0"]
        t1_row = group[group["timepoint"] == "t1"]
        t2_row = group[group["timepoint"] == "t2"]

        if len(t0_row) == 0:
            continue

        t0_section = t0_row.iloc[0]["user_section"] if len(t0_row) > 0 else None
        t1_section = t1_row.iloc[0]["user_section"] if len(t1_row) > 0 else None
        t2_section = t2_row.iloc[0]["user_section"] if len(t2_row) > 0 else None

        # Check if section changed
        if t0_section and t1_section and t0_section != t1_section:
            transitions.append(
                {
                    "email_id": email_id,
                    "subject": t0_row.iloc[0]["subject"],
                    "t0": t0_section,
                    "t1": t1_section,
                    "t2": t2_section,
                    "transition": f"{t0_section} → {t1_section}",
                }
            )

    return transitions


def check_pass_fail_criteria(df):
    """Check evaluation against pass/fail thresholds."""
    criteria = []

    for timepoint in ["t0", "t1", "t2"]:
        tp_df = df[df["timepoint"] == timepoint]

        if len(tp_df) == 0:
            continue

        # Calculate metrics
        total = len(tp_df)
        correct = (tp_df["correct"]).sum()
        accuracy = (correct / total * 100) if total > 0 else 0

        # Critical precision (avoid showing stale urgencies)
        critical_tp = len(
            tp_df[(tp_df["user_section"] == "critical") & (tp_df["system_section"] == "critical")]
        )
        critical_predicted = len(tp_df[tp_df["system_section"] == "critical"])
        critical_precision = (
            (critical_tp / critical_predicted * 100) if critical_predicted > 0 else 100
        )

        # TODAY recall (catch everything happening today)
        today_tp = len(
            tp_df[(tp_df["user_section"] == "today") & (tp_df["system_section"] == "today")]
        )
        today_actual = len(tp_df[tp_df["user_section"] == "today"])
        today_recall = (today_tp / today_actual * 100) if today_actual > 0 else 100

        # Receipt stability (WORTH_KNOWING for receipts)
        receipts = tp_df[
            tp_df["subject"].str.contains("receipt|order|purchase", case=False, na=False)
        ]
        receipt_stable = len(receipts[receipts["user_section"] == "worth_knowing"])
        receipt_stability = (receipt_stable / len(receipts) * 100) if len(receipts) > 0 else 100

        criteria.append(
            {
                "timepoint": timepoint.upper(),
                "accuracy": accuracy,
                "accuracy_pass": accuracy >= 70,  # Threshold: 70%
                "critical_precision": critical_precision,
                "critical_precision_pass": critical_precision >= 80,  # Threshold: 80%
                "today_recall": today_recall,
                "today_recall_pass": today_recall >= 75,  # Threshold: 75%
                "receipt_stability": receipt_stability,
                "receipt_stability_pass": receipt_stability >= 90,  # Threshold: 90%
            }
        )

    return criteria


def generate_markdown_report(df):
    """Generate full markdown report."""
    lines = []

    # Header
    lines.append("# Temporal Decay Evaluation Report\n")
    lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    lines.append(f"**Total Emails Evaluated:** {df['email_id'].nunique()}\n")
    lines.append("---\n")

    # Executive Summary
    lines.append("## Executive Summary\n")

    criteria = check_pass_fail_criteria(df)

    for crit in criteria:
        tp = crit["timepoint"]
        acc = crit["accuracy"]
        acc_pass = "✅ PASS" if crit["accuracy_pass"] else "❌ FAIL"

        lines.append(f"### {tp} Performance: {acc:.1f}% {acc_pass}\n")
        lines.append(f"- **Overall Accuracy:** {acc:.1f}% (threshold: 70%)\n")
        lines.append(
            f"- **Critical Precision:** {crit['critical_precision']:.1f}% "
            f"({'✅ PASS' if crit['critical_precision_pass'] else '❌ FAIL'}, threshold: 80%)\n"
        )
        lines.append(
            f"- **TODAY Recall:** {crit['today_recall']:.1f}% "
            f"({'✅ PASS' if crit['today_recall_pass'] else '❌ FAIL'}, threshold: 75%)\n"
        )
        lines.append(
            f"- **Receipt Stability:** {crit['receipt_stability']:.1f}% "
            f"({'✅ PASS' if crit['receipt_stability_pass'] else '❌ FAIL'}, threshold: 90%)\n"
        )
        lines.append("\n")

    # Overall Pass/Fail
    all_pass = all(
        c["accuracy_pass"]
        and c["critical_precision_pass"]
        and c["today_recall_pass"]
        and c["receipt_stability_pass"]
        for c in criteria
    )

    if all_pass:
        lines.append("### 🎉 OVERALL: ✅ ALL CRITERIA PASSED\n")
    else:
        lines.append("### ⚠️  OVERALL: ❌ SOME CRITERIA FAILED - Review Required\n")

    lines.append("\n---\n")

    # Confusion Matrices
    lines.append("## Confusion Matrices\n")

    for timepoint in ["t0", "t1", "t2"]:
        tp_df = df[df["timepoint"] == timepoint]
        if len(tp_df) > 0:
            lines.append(generate_confusion_matrix_table(tp_df, timepoint))
            lines.append("\n")

    lines.append("---\n")

    # Section Transitions
    lines.append("## Temporal Section Transitions\n")
    lines.append("*How emails move between sections as time advances*\n\n")

    transitions = analyze_transitions(df)

    if transitions:
        lines.append("| Email | T0 | T1 | T2 | Transition Pattern |\n")
        lines.append("|-------|----|----|----|-----------------|\n")

        for trans in transitions[:20]:  # Show first 20
            subject = trans["subject"][:40]
            t0 = trans["t0"][:12]
            t1 = trans["t1"][:12]
            t2 = trans["t2"][:12] if trans["t2"] else "-"
            pattern = trans["transition"]

            lines.append(f"| {subject} | {t0} | {t1} | {t2} | {pattern} |\n")

        if len(transitions) > 20:
            lines.append(f"\n*... and {len(transitions) - 20} more transitions*\n")
    else:
        lines.append("*No section transitions detected across timepoints*\n")

    lines.append("\n---\n")

    # Top Misclassifications
    lines.append("## Top Misclassifications\n")

    for timepoint in ["t0", "t1", "t2"]:
        tp_df = df[df["timepoint"] == timepoint]
        misclassified = tp_df[~tp_df["correct"]]

        if len(misclassified) > 0:
            lines.append(f"\n### {timepoint.upper()} Errors ({len(misclassified)} total)\n")
            lines.append("| Subject | Expected | Predicted |\n")
            lines.append("|---------|----------|----------|\n")

            for _, row in misclassified.head(10).iterrows():
                subject = row["subject"][:50]
                expected = row["user_section"]
                predicted = row["system_section"]
                lines.append(f"| {subject} | {expected} | {predicted} |\n")

            if len(misclassified) > 10:
                lines.append(f"\n*... and {len(misclassified) - 10} more errors*\n")

    lines.append("\n---\n")

    # Recommendations
    lines.append("## Recommendations\n\n")

    # Analyze common error patterns
    all_errors = df[~df["correct"]]

    if len(all_errors) > 0:
        # Group errors by transition type
        error_patterns = (
            all_errors.groupby(["user_section", "system_section"])
            .size()
            .sort_values(ascending=False)
        )

        lines.append("### Most Common Error Patterns:\n\n")
        for (user_sec, sys_sec), count in error_patterns.head(5).items():
            lines.append(f"- **{user_sec} → {sys_sec}**: {count} occurrences\n")
            if user_sec == "coming_up" and sys_sec == "worth_knowing":
                lines.append(
                    "  - *Issue: Temporal keywords not detected or datetime extraction failed*\n"
                )
                lines.append(
                    "  - *Fix: Enhance temporal keyword database or improve entity extraction*\n"
                )
            elif user_sec == "critical" and sys_sec == "worth_knowing":
                lines.append("  - *Issue: Critical items not escalated properly*\n")
                lines.append("  - *Fix: Review guardrails and importance classifier thresholds*\n")
            elif user_sec == "today" and sys_sec == "coming_up":
                lines.append("  - *Issue: TODAY cutoff not applied correctly*\n")
                lines.append("  - *Fix: Review temporal decay windows (< 1 hour for TODAY)*\n")

    lines.append("\n---\n")

    # Footer
    lines.append("## Next Steps\n\n")
    lines.append("1. Review failed criteria and top misclassifications\n")
    lines.append("2. Adjust temporal decay windows or categorizer rules\n")
    lines.append("3. Re-run evaluation: `python3 scripts/evaluate_temporal_decay.py`\n")
    lines.append("4. Iterate until all criteria pass\n")

    return "\n".join(lines)


def main():
    print("=" * 80)
    print("TEMPORAL DECAY MARKDOWN REPORTER")
    print("=" * 80)
    print()

    # Load results
    df = load_results()
    if df is None:
        return 1

    print(f"✅ Loaded {len(df)} evaluation results")
    print()

    # Generate report
    report = generate_markdown_report(df)

    # Save to file
    output_path = Path(__file__).parent.parent / "reports" / "temporal_decay_evaluation.md"
    output_path.write_text(report)

    print("✅ Generated markdown report")
    print(f"📂 Location: {output_path}")
    print()

    # Also print summary to console
    criteria = check_pass_fail_criteria(df)

    print("SUMMARY:")
    print("-" * 80)
    for crit in criteria:
        status = (
            "✅ PASS"
            if (
                crit["accuracy_pass"]
                and crit["critical_precision_pass"]
                and crit["today_recall_pass"]
                and crit["receipt_stability_pass"]
            )
            else "❌ FAIL"
        )
        print(f"{crit['timepoint']}: {crit['accuracy']:.1f}% accuracy {status}")

    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
