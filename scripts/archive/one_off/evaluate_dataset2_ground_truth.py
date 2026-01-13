"""
Evaluate V2 Pipeline Against Dataset 2 Ground Truth

Compares section assignments from the new pipeline (V2) against
human-annotated ground truth (T0, T1, T2 annotations).

Usage:
    python scripts/evaluate_dataset2_ground_truth.py [--time-horizon t0|t1|t2]

Metrics:
- Overall accuracy (predicted section matches ground truth)
- Per-section precision/recall
- Confusion matrix
- Detailed misclassification analysis
"""

import csv
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from mailq.digest.digest_pipeline import DigestPipeline
from mailq.digest.digest_stages import (
    BuildFeaturedItemsStage,
    DigestRenderingStage,
    EntityExtractionStage,
    IntrinsicSectionAssignmentStage,
    TemporalContextExtractionStage,
    TemporalDecayStage,
    TemporalEnrichmentStage,
)


def load_dataset2(csv_path: str) -> list[dict]:
    """Load Dataset 2 from CSV with ground truth annotations"""
    emails = []

    with open(csv_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            email = {
                "id": row["email_id"],
                "thread_id": row["email_id"],  # Use email_id as thread_id
                "subject": row["subject"],
                "from": row["from"],
                "snippet": row["snippet"],
                "date": row["received_date"],
                "type": row.get("predicted_type", ""),
                "importance": row.get("predicted_importance", "routine"),
                # Store ground truth annotations
                "_ground_truth": {
                    "t0": extract_ground_truth_section(row, "t0"),
                    "t1": extract_ground_truth_section(row, "t1"),
                    "t2": extract_ground_truth_section(row, "t2"),
                },
            }
            emails.append(email)

    return emails


def extract_ground_truth_section(row: dict, time_horizon: str) -> str:
    """Extract ground truth section from CSV row for given time horizon"""
    # Check which column has 'X' marker
    sections = ["critical", "today", "coming_up", "worth_knowing", "everything_else", "skip"]

    for section in sections:
        col_name = f"{time_horizon}_{section}"
        if row.get(col_name, "").strip().upper() == "X":
            # Map 'everything_else' to 'noise' for consistency
            return "noise" if section == "everything_else" else section

    # Default to noise if no annotation
    return "noise"


def run_pipeline_on_dataset2(emails: list[dict]) -> dict:
    """Run V2 pipeline on Dataset 2 emails"""
    # Create pipeline with T0/T1 separation
    # NOTE: Removed FilterExpiredEventsStage - temporal decay marks expired events as SKIP
    pipeline = DigestPipeline(
        [
            TemporalContextExtractionStage(),
            IntrinsicSectionAssignmentStage(),  # T0: intrinsic classification
            TemporalDecayStage(),  # T0 → T1: temporal adjustment
            EntityExtractionStage(),
            BuildFeaturedItemsStage(),
            TemporalEnrichmentStage(),
            DigestRenderingStage(),
        ]
    )

    # Digest time: Nov 10, 2025 at 6:20:07 PM EST
    # This matches the evaluation context in the original plan
    digest_time = datetime(2025, 11, 10, 18, 20, 7, tzinfo=UTC)

    # Run pipeline
    result = pipeline.run(
        emails=emails,
        now=digest_time,
        user_timezone="America/New_York",
    )

    return {
        "result": result,
        "section_assignments_t0": getattr(result.context, "section_assignments_t0", {}),
        "section_assignments": result.context.section_assignments,  # T1 sections
    }


def calculate_metrics(
    emails: list[dict],
    section_assignments: dict[str, str],
    time_horizon: str = "t0",
) -> dict:
    """Calculate accuracy metrics comparing predictions to ground truth"""

    # Metrics by section
    sections = ["critical", "today", "coming_up", "worth_knowing", "noise", "skip"]

    # Confusion matrix
    confusion = defaultdict(lambda: defaultdict(int))

    # Per-section stats
    stats = {section: {"tp": 0, "fp": 0, "fn": 0} for section in sections}

    # Overall stats
    total = 0
    correct = 0

    # Misclassifications for analysis
    misclassifications = []

    for email in emails:
        email_id = email["id"]
        predicted = section_assignments.get(email_id, "noise")
        ground_truth = email["_ground_truth"][time_horizon]

        total += 1

        # Overall accuracy
        if predicted == ground_truth:
            correct += 1
        else:
            misclassifications.append(
                {
                    "email_id": email_id,
                    "subject": email["subject"][:80],
                    "predicted": predicted,
                    "ground_truth": ground_truth,
                }
            )

        # Confusion matrix
        confusion[ground_truth][predicted] += 1

        # Per-section precision/recall
        for section in sections:
            if predicted == section and ground_truth == section:
                stats[section]["tp"] += 1
            elif predicted == section and ground_truth != section:
                stats[section]["fp"] += 1
            elif predicted != section and ground_truth == section:
                stats[section]["fn"] += 1

    # Calculate precision/recall per section
    metrics_by_section = {}
    for section in sections:
        tp = stats[section]["tp"]
        fp = stats[section]["fp"]
        fn = stats[section]["fn"]

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

        metrics_by_section[section] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": tp + fn,  # Total ground truth instances
        }

    # Overall metrics
    overall_accuracy = correct / total if total > 0 else 0.0

    return {
        "overall": {
            "accuracy": overall_accuracy,
            "total": total,
            "correct": correct,
            "incorrect": total - correct,
        },
        "by_section": metrics_by_section,
        "confusion_matrix": dict(confusion),
        "misclassifications": misclassifications,
    }


def print_report(metrics: dict, time_horizon: str):
    """Print detailed evaluation report"""
    print("\n" + "=" * 80)
    print(f"Dataset 2 Ground Truth Evaluation - Time Horizon: {time_horizon.upper()}")
    print("=" * 80)

    # Overall accuracy
    overall = metrics["overall"]
    print(f"\n📊 Overall Accuracy: {overall['accuracy']:.1%}")
    print(f"   Correct: {overall['correct']}/{overall['total']}")
    print(f"   Incorrect: {overall['incorrect']}/{overall['total']}")

    # Per-section metrics
    print("\n📈 Per-Section Metrics:")
    print(f"\n{'Section':<20} {'Precision':<12} {'Recall':<12} {'F1':<12} {'Support':<10}")
    print("-" * 80)

    sections = ["critical", "today", "coming_up", "worth_knowing", "noise", "skip"]
    for section in sections:
        m = metrics["by_section"][section]
        print(
            f"{section:<20} "
            f"{m['precision']:.1%}         "
            f"{m['recall']:.1%}       "
            f"{m['f1']:.1%}       "
            f"{m['support']}"
        )

    # Confusion matrix
    print("\n📋 Confusion Matrix (rows=ground truth, cols=predicted):")
    print(f"\n{'GT \\ Pred':<15}", end="")
    for section in sections:
        print(f"{section[:10]:<12}", end="")
    print()
    print("-" * 100)

    confusion = metrics["confusion_matrix"]
    for gt_section in sections:
        print(f"{gt_section:<15}", end="")
        for pred_section in sections:
            count = confusion.get(gt_section, {}).get(pred_section, 0)
            print(f"{count:<12}", end="")
        print()

    # Top misclassifications
    print("\n❌ Top Misclassifications (first 10):")
    print(f"\n{'Email ID':<15} {'Subject':<50} {'Predicted':<15} {'Ground Truth':<15}")
    print("-" * 110)

    for i, m in enumerate(metrics["misclassifications"][:10]):
        print(
            f"{m['email_id']:<15} {m['subject']:<50} {m['predicted']:<15} {m['ground_truth']:<15}"
        )

    # Analysis summary
    print("\n📝 Analysis:")

    # Check if targets met
    target_accuracy = 0.85
    if overall["accuracy"] >= target_accuracy:
        print(
            f"   ✅ Overall accuracy {overall['accuracy']:.1%} meets target (≥{target_accuracy:.0%})"
        )
    else:
        gap = target_accuracy - overall["accuracy"]
        print(
            f"   ⚠️  Overall accuracy {overall['accuracy']:.1%} below target (≥{target_accuracy:.0%})"
        )
        print(
            f"      Gap: {gap:.1%} ({int(gap * overall['total'])} more emails need correct classification)"
        )

    # Check critical section
    if "critical" in metrics["by_section"]:
        critical_recall = metrics["by_section"]["critical"]["recall"]
        if critical_recall == 1.0:
            print("   ✅ Critical section recall: 100%")
        else:
            print(f"   ⚠️  Critical section recall: {critical_recall:.1%} (target: 100%)")

    # Check today section
    if "today" in metrics["by_section"]:
        today_recall = metrics["by_section"]["today"]["recall"]
        today_support = metrics["by_section"]["today"]["support"]
        if today_recall >= 0.85:
            print(
                f"   ✅ Today section recall: {today_recall:.1%} ({int(today_recall * today_support)}/{today_support})"
            )
        else:
            print(f"   ⚠️  Today section recall: {today_recall:.1%} (target: ≥85%)")

    print("\n" + "=" * 80)


def main():
    """Run evaluation"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Evaluate V2 pipeline against Dataset 2 ground truth"
    )
    parser.add_argument(
        "--time-horizon",
        choices=["t0", "t1", "t2"],
        default="t0",
        help="Time horizon for ground truth (t0=immediate, t1=today, t2=this week)",
    )
    parser.add_argument(
        "--csv-path",
        default="reports/dataset2_nov2-9_70_emails.csv",
        help="Path to Dataset 2 CSV",
    )
    args = parser.parse_args()

    print(f"Loading Dataset 2 from {args.csv_path}...")
    emails = load_dataset2(args.csv_path)
    print(f"Loaded {len(emails)} emails")

    print("\nRunning V2 pipeline...")
    pipeline_result = run_pipeline_on_dataset2(emails)

    # Extract T0 and T1 section assignments
    section_assignments_t0 = pipeline_result["section_assignments_t0"]
    section_assignments_t1 = pipeline_result["section_assignments"]

    print("Pipeline complete.")
    print(f"  T0 (intrinsic) sections: {len(section_assignments_t0)}")
    print(f"  T1 (time-adjusted) sections: {len(section_assignments_t1)}")

    # Choose which sections to evaluate based on time horizon
    if args.time_horizon == "t0":
        section_assignments = section_assignments_t0
        print("\n📊 Evaluating T0 (intrinsic) sections against T0 ground truth...")
    elif args.time_horizon == "t1":
        section_assignments = section_assignments_t1
        print("\n📊 Evaluating T1 (time-adjusted) sections against T1 ground truth...")
    else:  # t2
        section_assignments = section_assignments_t1  # T2 not implemented yet, use T1
        print(
            "\n📊 Evaluating T1 sections against T2 ground truth (T2 decay not yet implemented)..."
        )

    print(f"\nCalculating metrics for time horizon: {args.time_horizon}...")
    metrics = calculate_metrics(emails, section_assignments, args.time_horizon)

    # Print report
    print_report(metrics, args.time_horizon)

    # Save detailed results to file
    output_path = f"reports/dataset2_evaluation_{args.time_horizon}.txt"
    print(f"\n💾 Saving detailed report to {output_path}...")

    with open(output_path, "w") as f:
        # Redirect stdout to file
        import io
        from contextlib import redirect_stdout

        f_stdout = io.StringIO()
        with redirect_stdout(f_stdout):
            print_report(metrics, args.time_horizon)

        f.write(f_stdout.getvalue())

    print("✅ Report saved!")

    # Return exit code based on accuracy
    if metrics["overall"]["accuracy"] >= 0.85:
        print(f"\n🎉 SUCCESS: Accuracy {metrics['overall']['accuracy']:.1%} meets target (≥85%)")
        return 0
    print(
        f"\n⚠️  NEEDS IMPROVEMENT: Accuracy {metrics['overall']['accuracy']:.1%} below target (≥85%)"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
