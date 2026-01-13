#!/usr/bin/env python3
"""
Evaluate baseline classification performance on gds-1.0 dataset.

This script:
1. Loads gds-1.0 regression suite (80 critical emails)
2. Runs current classification system (rules + LLM fallback)
3. Compares predictions vs ground truth
4. Reports precision/recall/F1 for importance and type
5. Identifies top misclassifications

Usage:
    PYTHONPATH=/Users/justinkoufopoulos/Projects/mailq-prototype \
        python3 scripts/eval_baseline_gds1.py

Output:
    - Console: Summary metrics
    - File: reports/gds1_baseline_evaluation_YYYY-MM-DD.json
"""

import csv
import json

# Add project root to path
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# Import directly to avoid full mailq package dependencies
import importlib.util

spec = importlib.util.spec_from_file_location(
    "importance_classifier", Path(__file__).parent.parent / "mailq" / "importance_classifier.py"
)
importance_classifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(importance_classifier)
ImportanceClassifier = importance_classifier.ImportanceClassifier

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
REGRESSION_SUITE = PROJECT_ROOT / "tests/golden_set/gds-1.0_regression.csv"
REPORTS_DIR = PROJECT_ROOT / "reports"
REPORTS_DIR.mkdir(exist_ok=True)


def load_regression_suite():
    """Load gds-1.0 regression suite."""
    print(f"Loading regression suite from {REGRESSION_SUITE}...")

    with open(REGRESSION_SUITE, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        emails = list(reader)

    print(f"Loaded {len(emails)} emails\n")
    return emails


def classify_email(email, classifier):
    """
    Classify a single email using current system.

    Returns:
        dict with predicted_importance, predicted_type, confidence
    """
    # Combine subject + snippet for classification
    text = f"{email.get('subject', '')} {email.get('snippet', '')}"
    email_type = email.get("email_type", "notification")
    attention = email.get("attention", "none")

    # Classify importance using pattern-based classifier
    predicted_importance = classifier.classify(
        text=text, email_type=email_type, attention=attention
    )

    # For now, we're only evaluating importance
    # Type classification would need domain/classify.py integration
    predicted_type = email_type  # Use ground truth type for now

    return {
        "predicted_importance": predicted_importance,
        "predicted_type": predicted_type,
        "confidence": 0.0,  # Pattern-based doesn't provide confidence
    }


def calculate_metrics(y_true, y_pred, labels):
    """Calculate precision, recall, F1 for each label."""
    metrics = {}

    for label in labels:
        tp = sum(
            1 for true, pred in zip(y_true, y_pred, strict=False) if true == label and pred == label
        )
        fp = sum(
            1 for true, pred in zip(y_true, y_pred, strict=False) if true != label and pred == label
        )
        fn = sum(
            1 for true, pred in zip(y_true, y_pred, strict=False) if true == label and pred != label
        )

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

        metrics[label] = {
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "f1": round(f1, 3),
            "support": sum(1 for t in y_true if t == label),
            "tp": tp,
            "fp": fp,
            "fn": fn,
        }

    return metrics


def analyze_misclassifications(emails, results):
    """Identify top misclassifications by category."""
    misclassifications = defaultdict(list)

    for email, result in zip(emails, results, strict=False):
        true_imp = email.get("importance", "routine")
        pred_imp = result["predicted_importance"]

        if true_imp != pred_imp:
            error_type = f"{true_imp} → {pred_imp}"
            misclassifications[error_type].append(
                {
                    "message_id": email.get("message_id", "unknown")[:16],
                    "subject": email.get("subject", "No subject")[:60],
                    "true": true_imp,
                    "predicted": pred_imp,
                    "p0_category": email.get("p0_category", ""),
                    "email_type": email.get("email_type", ""),
                }
            )

    return misclassifications


def print_confusion_matrix(y_true, y_pred, labels):
    """Print confusion matrix."""
    print("\nConfusion Matrix (Importance):")
    print(f"{'':15} " + " ".join(f"{label:15}" for label in labels))

    for true_label in labels:
        row = f"{true_label:15} "
        for pred_label in labels:
            count = sum(
                1
                for t, p in zip(y_true, y_pred, strict=False)
                if t == true_label and p == pred_label
            )
            row += f"{count:15} "
        print(row)


def main():
    print("=" * 80)
    print("gds-1.0 Baseline Evaluation")
    print("=" * 80)
    print()

    # Load regression suite
    emails = load_regression_suite()

    # Initialize classifier
    print("Initializing importance classifier...")
    classifier = ImportanceClassifier()
    print()

    # Classify all emails
    print("Classifying emails...")
    results = []
    for i, email in enumerate(emails, 1):
        if i % 10 == 0:
            print(f"  Processed {i}/{len(emails)} emails...")
        result = classify_email(email, classifier)
        results.append(result)
    print(f"  Completed {len(emails)} classifications\n")

    # Extract ground truth and predictions
    y_true_importance = [email.get("importance", "routine") for email in emails]
    y_pred_importance = [result["predicted_importance"] for result in results]

    importance_labels = ["critical", "time_sensitive", "routine"]

    # Calculate metrics
    print("=" * 80)
    print("IMPORTANCE CLASSIFICATION RESULTS")
    print("=" * 80)

    importance_metrics = calculate_metrics(y_true_importance, y_pred_importance, importance_labels)

    # Print per-class metrics
    header = f"\n{'Class':<20} {'Precision':>10} {'Recall':>10} {'F1':>10} "
    header += f"{'Support':>10}"
    print(header)
    print("-" * 70)
    for label in importance_labels:
        m = importance_metrics[label]
        line = f"{label:<20} {m['precision']:>10.3f} {m['recall']:>10.3f} "
        line += f"{m['f1']:>10.3f} {m['support']:>10}"
        print(line)

    # Calculate macro average
    macro_precision = sum(m["precision"] for m in importance_metrics.values()) / len(
        importance_metrics
    )
    macro_recall = sum(m["recall"] for m in importance_metrics.values()) / len(importance_metrics)
    macro_f1 = sum(m["f1"] for m in importance_metrics.values()) / len(importance_metrics)

    print("-" * 70)
    summary = f"{'Macro Average':<20} {macro_precision:>10.3f} "
    summary += f"{macro_recall:>10.3f} {macro_f1:>10.3f} {len(emails):>10}"
    print(summary)

    # Confusion matrix
    print_confusion_matrix(y_true_importance, y_pred_importance, importance_labels)

    # Analyze misclassifications
    print("\n" + "=" * 80)
    print("TOP MISCLASSIFICATIONS")
    print("=" * 80)

    misclassifications = analyze_misclassifications(emails, results)

    # Sort by frequency
    sorted_errors = sorted(misclassifications.items(), key=lambda x: len(x[1]), reverse=True)

    for error_type, cases in sorted_errors[:5]:  # Top 5 error types
        print(f"\n{error_type} ({len(cases)} cases):")
        for case in cases[:3]:  # Show first 3 examples
            print(f"  - [{case['message_id']}] {case['subject']}...")
            if case["p0_category"]:
                print(f"    P0: {case['p0_category']}")

    # Overall accuracy
    total_correct = sum(
        1 for t, p in zip(y_true_importance, y_pred_importance, strict=False) if t == p
    )
    accuracy = total_correct / len(emails)

    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total emails evaluated: {len(emails)}")
    print(f"Overall accuracy: {accuracy:.3f} ({total_correct}/{len(emails)})")
    print(f"Macro F1: {macro_f1:.3f}")
    print()

    # P0 test case performance
    p0_emails = [e for e in emails if e.get("p0_category")]
    [r for e, r in zip(emails, results, strict=False) if e.get("p0_category")]
    p0_correct = sum(
        1
        for e, r in zip(emails, results, strict=False)
        if e.get("p0_category") and e.get("importance") == r["predicted_importance"]
    )

    if p0_emails:
        p0_pct = p0_correct / len(p0_emails)
        print(f"P0 Test Cases: {p0_correct}/{len(p0_emails)} correct ({p0_pct:.1%})")

        # Breakdown by P0 category
        p0_by_cat = defaultdict(lambda: {"total": 0, "correct": 0})
        for e, r in zip(emails, results, strict=False):
            p0_cat = e.get("p0_category")
            if p0_cat:
                p0_by_cat[p0_cat]["total"] += 1
                if e.get("importance") == r["predicted_importance"]:
                    p0_by_cat[p0_cat]["correct"] += 1

        print("\nP0 Breakdown:")
        for cat, stats in sorted(p0_by_cat.items()):
            acc = stats["correct"] / stats["total"] if stats["total"] > 0 else 0
            print(f"  {cat}: {stats['correct']}/{stats['total']} ({acc:.1%})")

    # Save detailed results
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    report_path = REPORTS_DIR / f"gds1_baseline_evaluation_{timestamp}.json"

    report = {
        "evaluation_date": datetime.now().isoformat(),
        "dataset": "gds-1.0_regression",
        "total_emails": len(emails),
        "classifier": "ImportanceClassifier (pattern-based)",
        "metrics": {
            "importance": {
                "per_class": importance_metrics,
                "macro_precision": round(macro_precision, 3),
                "macro_recall": round(macro_recall, 3),
                "macro_f1": round(macro_f1, 3),
                "accuracy": round(accuracy, 3),
            }
        },
        "p0_performance": {
            "total": len(p0_emails),
            "correct": p0_correct,
            "accuracy": round(p0_correct / len(p0_emails), 3) if p0_emails else 0,
            "by_category": {cat: stats for cat, stats in p0_by_cat.items()},
        },
        "misclassifications": {
            error_type: [
                {
                    "message_id": case["message_id"],
                    "subject": case["subject"],
                    "true": case["true"],
                    "predicted": case["predicted"],
                    "p0_category": case["p0_category"],
                    "email_type": case["email_type"],
                }
                for case in cases
            ]
            for error_type, cases in sorted_errors
        },
    }

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(f"\n✅ Detailed report saved to: {report_path}")
    print()


if __name__ == "__main__":
    main()
